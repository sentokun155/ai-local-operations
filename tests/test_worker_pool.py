from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import sqlite3
from unittest.mock import patch

import server
from local_mcp.dispatch import AppServerTransportError, dispatch_task
from local_mcp.finalize import recover_worker
from local_mcp.worker_pool import (
    ManagedRepository,
    WorkerPool,
    WorkerPoolConfig,
    WorkerPoolError,
)


def git(path: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if check and result.returncode:
        raise AssertionError(f"git {args[0]} failed: {result.stderr}")
    return result.stdout.strip()


class FakeClient:
    def __init__(self):
        self.requests: list[tuple[str, dict]] = []

    def ensure_ready(self):
        return None

    def request(self, method, params):
        self.requests.append((method, params))
        if method == "config/read":
            return {"config": {"model": "gpt-6-luna", "model_reasoning_effort": "low"}}
        if method == "model/list":
            return {"data": [{"id": "gpt-6-luna", "model": "gpt-6-luna", "isDefault": True,
                              "supportedReasoningEfforts": [{"reasoningEffort": "low"}]}], "nextCursor": None}
        if method == "thread/start":
            return {"thread": {"id": "thread-fixture"}, "model": "gpt-6-luna", "reasoningEffort": "low"}
        if method == "turn/start":
            return {"turn": {"id": "turn-fixture"}}
        if method == "thread/read":
            return {"thread": {"turns": [{
                "id": "turn-fixture", "status": "completed",
                "items": [{"type": "agentMessage", "text": "Fixture Result is ready."}],
            }]}}
        if method == "thread/name/set":
            return {}
        raise AssertionError(f"unexpected method {method}")

    def wait_for_turn_started(self, thread_id, turn_id, timeout):
        return True


class WorkerPoolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="local-operations-worker-tests-")
        self.root = Path(self.temp.name)
        self.bare = self.root / "fixture-origin.git"
        subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(self.bare)], check=True, capture_output=True)
        seed = self.root / "seed"
        subprocess.run(["git", "clone", str(self.bare), str(seed)], check=True, capture_output=True)
        git(seed, "config", "user.name", "Worker Pool Fixture")
        git(seed, "config", "user.email", "worker-fixture@example.invalid")
        (seed / "TASK_REQUEST.md").write_text(
            "# Fixture Task\n\nRead this file. Do not edit files.\n", encoding="utf-8"
        )
        git(seed, "add", "TASK_REQUEST.md")
        git(seed, "commit", "-m", "Add fixture Task Request")
        git(seed, "push", "-u", "origin", "main")
        git(seed, "checkout", "-b", "feature")
        git(seed, "push", "-u", "origin", "feature")

        self.identity = "github.com/example/fixture"
        self.clone_url = "https://github.com/example/fixture.git"
        self.repo = ManagedRepository("example/fixture", self.clone_url, "main", "fixture")
        self.config = WorkerPoolConfig(2, self.root / "workers", (self.repo,))
        self.state = self.root / "state.sqlite3"
        for worker_id in self.config.worker_ids():
            path = self.config.repository_path(worker_id, self.repo)
            path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "--branch", "main", str(self.bare), str(path)], check=True, capture_output=True)
            git(path, "remote", "set-url", "origin", self.clone_url)
            git(path, "config", f"url.{self.bare.as_uri()}.insteadOf", self.clone_url)
        self.pool = WorkerPool(self.config, self.state)

    def tearDown(self):
        self.temp.cleanup()

    def lease(self, worker_pool=None, task="GWI-0010-T-fixture", branch="feature"):
        return (worker_pool or self.pool).lease(
            work_identity="GWI-0010-FIXTURE", task_key=task,
            repository_identity="example/fixture", branch=branch,
        )

    def test_free_to_leased_and_same_slot_cannot_be_leased_twice(self):
        first = self.lease()
        second = self.lease(task="GWI-0010-T-second")
        self.assertEqual(first["worker_id"], "worker-01")
        self.assertEqual(second["worker_id"], "worker-02")
        self.assertEqual(first["repository_root"], str(self.config.repository_path("worker-01", self.repo).resolve()))
        self.assertEqual(git(Path(first["repository_root"]), "branch", "--show-current"), "feature")
        with self.assertRaises(WorkerPoolError) as context:
            self.lease(task="GWI-0010-T-third")
        self.assertEqual(context.exception.reason, "NO_FREE_WORKER")

    def test_dirty_untracked_state_is_preserved_and_quarantined(self):
        path = self.config.repository_path("worker-01", self.repo)
        marker = path / "unexpected-local-file.txt"
        marker.write_text("keep me", encoding="utf-8")
        with self.assertRaises(WorkerPoolError) as context:
            self.pool.bootstrap()
        self.assertEqual(context.exception.reason, "WORKER_BOOTSTRAP_UNEXPECTED_STATE")
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep me")
        self.assertEqual(self.pool.status()[0]["state"], "QUARANTINED")

    def test_wrong_remote_is_held_and_quarantined(self):
        path = self.config.repository_path("worker-01", self.repo)
        git(path, "remote", "set-url", "origin", "https://github.com/wrong/repository.git")
        with self.assertRaises(WorkerPoolError):
            self.pool.bootstrap()
        self.assertEqual(self.pool.status()[0]["state"], "QUARANTINED")

    def test_config_rejects_worker_root_inside_runtime_checkout(self):
        path = self.root / "worker-config.json"
        path.write_text(json.dumps({
            "version": 1, "workerCount": 1,
            "repositories": [{"identity": "example/fixture", "cloneUrl": self.clone_url, "defaultBranch": "main"}],
        }), encoding="utf-8")
        with self.assertRaises(WorkerPoolError) as context:
            WorkerPoolConfig.load(config_path=path, worker_root=Path("C:/Dev/DevEnv/workers"))
        self.assertEqual(context.exception.reason, "WORKER_POOL_CONFIG_INVALID")

    def test_unknown_branch_holds_without_discarding_worktree(self):
        with self.assertRaises(WorkerPoolError) as context:
            self.lease(branch="missing-branch")
        self.assertEqual(context.exception.reason, "WORKER_REPOSITORY_PREFLIGHT_FAILED")
        self.assertEqual(self.pool.status()[0]["state"], "QUARANTINED")
        self.assertEqual(git(self.config.repository_path("worker-01", self.repo), "branch", "--show-current"), "main")

    def test_local_only_commit_is_quarantined_and_retained(self):
        path = self.config.repository_path("worker-01", self.repo)
        git(path, "config", "user.name", "Worker Pool Fixture")
        git(path, "config", "user.email", "worker-fixture@example.invalid")
        (path / "local-only.txt").write_text("retain", encoding="utf-8")
        git(path, "add", "local-only.txt")
        git(path, "commit", "-m", "local-only")
        local_commit = git(path, "rev-parse", "HEAD")
        with self.assertRaises(WorkerPoolError):
            self.lease(branch="main")
        self.assertEqual(git(path, "rev-parse", "HEAD"), local_commit)
        self.assertTrue((path / "local-only.txt").exists())
        self.assertEqual(self.pool.status()[0]["state"], "QUARANTINED")

    def test_release_keeps_task_branch_and_next_task_can_switch_branch(self):
        lease = self.lease()
        self.pool.record_dispatch(lease["worker_id"], "GWI-0010-FIXTURE", "GWI-0010-T-fixture",
                                  thread_id="thread-fixture", turn_id="turn-fixture")
        result = self.pool.release_task("worker-01", "GWI-0010-FIXTURE", "GWI-0010-T-fixture")
        self.assertEqual(result["state"], "FREE")
        self.assertEqual(git(Path(lease["repository_root"]), "branch", "--show-current"), "feature")
        again = self.lease(task="GWI-0010-T-reuse", branch="main")
        self.assertEqual(again["worker_id"], "worker-01")
        self.assertEqual(git(Path(again["repository_root"]), "branch", "--show-current"), "main")

    def test_release_keeps_dirty_worker_leased_without_deleting_it(self):
        lease = self.lease()
        self.pool.record_dispatch(lease["worker_id"], "GWI-0010-FIXTURE", "GWI-0010-T-fixture",
                                  thread_id="thread-fixture", turn_id="turn-fixture")
        marker = Path(lease["repository_root"]) / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaises(WorkerPoolError):
            self.pool.release_task("worker-01", "GWI-0010-FIXTURE", "GWI-0010-T-fixture")
        self.assertTrue(marker.exists())
        self.assertEqual(self.pool.status()[0]["state"], "LEASED")

    def _dispatch_fixture(self, task_key: str, client: FakeClient, branch: str = "feature"):
        pool_config_path = self.root / "pool.json"
        pool_config_path.write_text(json.dumps({
            "version": 1, "workerCount": 2,
            "repositories": [{"identity": "example/fixture", "cloneUrl": self.clone_url, "defaultBranch": "main"}],
        }), encoding="utf-8")
        params = {
            "work_identity": "GWI-0010-FIXTURE", "task_key": task_key,
            "task_name": "Persistence fixture", "task_request_locator": "TASK_REQUEST.md",
            "repository": "example/fixture", "branch": branch,
            "model": None, "reasoning_effort": None,
        }
        with patch.object(server, "dispatch_task", side_effect=lambda payload: dispatch_task(
            payload, client_factory=lambda: client, state_path=self.state,
            worker_pool_config_path=pool_config_path, worker_root=self.config.worker_root,
        )):
            result = asyncio.run(server.mcp.call_tool("dispatch_codex_task", params)).structured_content
        self.assertEqual(result["status"], "DISPATCHED", result)
        return params, result

    def _finalize_fixture(self, params, client):
        with patch.object(server.WorkerPoolConfig, "load", return_value=self.config), \
             patch("local_mcp.finalize.default_state_path", return_value=self.state), \
             patch("local_mcp.finalize._get_default_client", return_value=client):
            return asyncio.run(server.mcp.call_tool("finalize_codex_task", {
                "worker_id": "worker-01", "work_identity": params["work_identity"],
                "task_key": params["task_key"],
            })).structured_content

    def _recover_fixture(self, client, worker_id="worker-01"):
        with patch.object(WorkerPoolConfig, "load", return_value=self.config):
            return recover_worker(worker_id, client_factory=lambda: client, state_path=self.state)

    def test_recovery_releases_quarantined_clean_worker(self):
        client = FakeClient()
        params, _ = self._dispatch_fixture("GWI-0010-T-recover-clean", client)
        self.pool._quarantine("worker-01", "RECOVERY_FIXTURE")

        result = self._recover_fixture(client)
        self.assertEqual(result["status"], "RECOVERED", result)
        self.assertEqual(result["workerState"], "FREE")
        self.assertEqual(result["pushStatus"], "NOT_NEEDED")
        self.assertEqual(result["taskKey"], params["task_key"])
        self.assertEqual(self.pool.status()[0]["state"], "FREE")

    def test_recovery_commits_and_pushes_completed_task_before_freeing_worker(self):
        client = FakeClient()
        params, receipt = self._dispatch_fixture("GWI-0010-T-recover-result", client)
        root = Path(receipt["resolvedRepositoryRoot"])
        result_file = root / "work/gwi-0010/probes/GWI-0010-T-recover-result_RESULT.md"
        result_file.parent.mkdir(parents=True)
        result_file.write_text("Preserved probe Result.\n", encoding="utf-8")
        self.pool._quarantine("worker-01", "RECOVERY_FIXTURE")

        result = self._recover_fixture(client)
        self.assertEqual(result["status"], "RECOVERED", result)
        self.assertEqual(result["codexTurnStatus"], "completed")
        self.assertEqual(result["finalAgentMessage"], "Fixture Result is ready.")
        self.assertEqual(result["pushStatus"], "PUSHED")
        self.assertTrue(result["commitSha"])
        self.assertEqual(result["resultLocators"], ["work/gwi-0010/probes/GWI-0010-T-recover-result_RESULT.md"])
        self.assertEqual(git(self.bare, "rev-parse", "refs/heads/feature"), result["commitSha"])
        self.assertEqual(self.pool.status()[0]["state"], "FREE")

    def test_recovery_push_failure_keeps_quarantine_and_local_commit(self):
        client = FakeClient()
        _, receipt = self._dispatch_fixture("GWI-0010-T-recover-push-failure", client)
        root = Path(receipt["resolvedRepositoryRoot"])
        result_file = root / "local-result.md"
        result_file.write_text("Keep this completed Result.\n", encoding="utf-8")
        other = self.root / "recovery-remote-writer"
        subprocess.run(["git", "clone", "--branch", "feature", str(self.bare), str(other)], check=True, capture_output=True)
        git(other, "config", "user.name", "Other Writer")
        git(other, "config", "user.email", "other@example.invalid")
        (other / "remote-advance.txt").write_text("remote advances first\n", encoding="utf-8")
        git(other, "add", "remote-advance.txt")
        git(other, "commit", "-m", "advance remote")
        git(other, "push", "origin", "feature")
        self.pool._quarantine("worker-01", "RECOVERY_FIXTURE")

        result = self._recover_fixture(client)
        self.assertEqual(result["status"], "HOLD", result)
        self.assertEqual(result["reason"], "GIT_PUSH_FAILED")
        self.assertEqual(result["pushStatus"], "FAILED")
        self.assertEqual(result["workerState"], "QUARANTINED")
        self.assertEqual(self.pool.status()[0]["state"], "QUARANTINED")
        self.assertTrue(result["commitSha"])
        self.assertEqual(git(root, "rev-parse", "HEAD"), result["commitSha"])
        self.assertEqual(result_file.read_text(encoding="utf-8"), "Keep this completed Result.\n")

    def test_recovery_reports_non_quarantined_and_unknown_workers(self):
        with patch.object(WorkerPoolConfig, "load", return_value=self.config):
            free = recover_worker("worker-02", state_path=self.state)
            missing = recover_worker("worker-03", state_path=self.state)
        self.assertEqual(free["status"], "UNCHANGED")
        self.assertEqual(free["workerState"], "FREE")
        self.assertEqual(missing["reason"], "WORKER_NOT_FOUND")

    def test_finalize_commits_pushes_intakes_result_and_releases_worker(self):
        client = FakeClient()
        params, receipt = self._dispatch_fixture("GWI-0010-T-persist", client)
        root = Path(receipt["resolvedRepositoryRoot"])
        (root / "work/gwi-0010/probes").mkdir(parents=True)
        result_file = root / "work/gwi-0010/probes/GWI-0010-T-persist_RESULT.md"
        result_file.write_text("Fixture Result\n", encoding="utf-8")
        result = self._finalize_fixture(params, client)
        self.assertEqual(result["status"], "FINALIZED", result)
        self.assertEqual(result["codexTurnStatus"], "completed")
        self.assertEqual(result["finalAgentMessage"], "Fixture Result is ready.")
        self.assertEqual(result["pushStatus"], "PUSHED")
        self.assertTrue(result["commitSha"])
        self.assertEqual(result["resultLocators"], ["work/gwi-0010/probes/GWI-0010-T-persist_RESULT.md"])
        self.assertEqual(self.pool.status()[0]["state"], "FREE")
        self.assertEqual(git(self.bare, "rev-parse", "refs/heads/feature"), result["commitSha"])
        again = self._finalize_fixture(params, client)
        self.assertEqual(again["status"], "ALREADY_FINALIZED")

    def test_no_change_task_returns_result_without_commit_and_releases(self):
        client = FakeClient()
        params, _ = self._dispatch_fixture("GWI-0010-T-readonly", client)
        result = self._finalize_fixture(params, client)
        self.assertEqual(result["status"], "FINALIZED")
        self.assertIsNone(result["commitSha"])
        self.assertEqual(result["pushStatus"], "NOT_NEEDED")
        self.assertEqual(result["finalAgentMessage"], "Fixture Result is ready.")
        self.assertEqual(self.pool.status()[0]["state"], "FREE")

    def test_push_rejection_keeps_local_commit_and_worker_lease(self):
        client = FakeClient()
        params, receipt = self._dispatch_fixture("GWI-0010-T-push-reject", client, branch="main")
        root = Path(receipt["resolvedRepositoryRoot"])
        (root / "local-result.md").write_text("keep this result", encoding="utf-8")
        other = self.root / "other-writer"
        subprocess.run(["git", "clone", str(self.bare), str(other)], check=True, capture_output=True)
        git(other, "config", "user.name", "Other Writer")
        git(other, "config", "user.email", "other@example.invalid")
        (other / "remote-update.txt").write_text("advance remote", encoding="utf-8")
        git(other, "add", "remote-update.txt")
        git(other, "commit", "-m", "advance remote")
        git(other, "push", "origin", "main")
        result = self._finalize_fixture(params, client)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "GIT_PUSH_FAILED", result)
        self.assertEqual(result["pushStatus"], "FAILED")
        self.assertTrue(result["commitSha"])
        self.assertEqual(git(root, "rev-parse", "HEAD"), result["commitSha"])
        self.assertEqual(git(root, "status", "--short"), "")
        self.assertEqual(self.pool.status()[0]["state"], "LEASED")
        self.assertIn("keep this result", (root / "local-result.md").read_text(encoding="utf-8"))

    def test_explicitly_staged_secret_is_not_committed(self):
        client = FakeClient()
        params, receipt = self._dispatch_fixture("GWI-0010-T-secret", client)
        root = Path(receipt["resolvedRepositoryRoot"])
        secret = root / ".env"
        secret.write_text("OPENAI_API_KEY=sk-" + "x" * 30, encoding="utf-8")
        git(root, "add", "-f", ".env")
        result = self._finalize_fixture(params, client)
        self.assertEqual(result["reason"], "SECRET_CONTENT_NOT_COMMITTED")
        self.assertTrue(secret.exists())
        self.assertNotEqual(git(root, "log", "-1", "--format=%s"), "Local Operations: GWI-0010-FIXTURE/GWI-0010-T-secret")
        self.assertEqual(self.pool.status()[0]["state"], "LEASED")

    def test_logical_mcp_dispatch_uses_selected_worker_root_and_receipt(self):
        client = FakeClient()
        params = {
            "work_identity": "GWI-0010-FIXTURE",
            "task_key": "GWI-0010-T-dispatch",
            "task_name": "Worker dispatch fixture",
            "task_request_locator": "TASK_REQUEST.md",
            "repository": "example/fixture",
            "branch": "main",
            "model": None,
            "reasoning_effort": None,
        }
        original = server.dispatch_task
        server.dispatch_task = lambda payload: original(
            payload, client_factory=lambda: client, state_path=self.state,
            worker_pool_config_path=self.root / "pool.json", worker_root=self.config.worker_root,
        )
        config_document = {
            "version": 1, "workerCount": 2,
            "repositories": [{"identity": "example/fixture", "cloneUrl": self.clone_url, "defaultBranch": "main"}],
        }
        (self.root / "pool.json").write_text(json.dumps(config_document), encoding="utf-8")
        try:
            result = asyncio.run(server.mcp.call_tool("dispatch_codex_task", params))
            receipt = result.structured_content
            self.assertEqual(receipt["status"], "DISPATCHED", receipt)
            self.assertEqual(receipt["workerId"], "worker-01")
            self.assertEqual(receipt["workspaceResolutionSource"], "fixed_worker_pool")
            self.assertEqual(receipt["resolvedRepositoryRoot"], str(self.config.repository_path("worker-01", self.repo).resolve()))
            thread_start = next(p for method, p in client.requests if method == "thread/start")
            self.assertEqual(thread_start["cwd"], receipt["resolvedRepositoryRoot"])
            calls = len(client.requests)
            duplicate = asyncio.run(server.mcp.call_tool("dispatch_codex_task", params)).structured_content
            self.assertEqual(duplicate["status"], "ALREADY_DISPATCHED")
            self.assertEqual(len(client.requests), calls)
            self.assertEqual(self.pool.status()[0]["state"], "LEASED")
        finally:
            server.dispatch_task = original


if __name__ == "__main__":
    unittest.main()
