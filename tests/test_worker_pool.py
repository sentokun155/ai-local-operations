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
from local_mcp.dispatch import AppServerTransportError
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
            return {"thread": {"turns": [{"id": "turn-fixture", "status": "completed"}]}}
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

    def test_safe_release_returns_worker_to_default_branch_and_reuses_it(self):
        lease = self.lease()
        self.pool.record_dispatch(lease["worker_id"], "GWI-0010-FIXTURE", "GWI-0010-T-fixture",
                                  thread_id="thread-fixture", turn_id="turn-fixture")
        result = self.pool.release_completed("worker-01", "GWI-0010-FIXTURE", "GWI-0010-T-fixture")
        self.assertEqual(result["state"], "FREE")
        self.assertEqual(git(Path(lease["repository_root"]), "branch", "--show-current"), "main")
        again = self.lease(task="GWI-0010-T-reuse")
        self.assertEqual(again["worker_id"], "worker-01")

    def test_release_quarantines_dirty_state_without_deleting_it(self):
        lease = self.lease()
        self.pool.record_dispatch(lease["worker_id"], "GWI-0010-FIXTURE", "GWI-0010-T-fixture",
                                  thread_id="thread-fixture", turn_id="turn-fixture")
        marker = Path(lease["repository_root"]) / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaises(WorkerPoolError):
            self.pool.release_completed("worker-01", "GWI-0010-FIXTURE", "GWI-0010-T-fixture")
        self.assertTrue(marker.exists())
        self.assertEqual(self.pool.status()[0]["state"], "QUARANTINED")

    def test_explicitly_rejected_thread_can_release_when_app_server_has_no_turn(self):
        lease = self.pool.lease(
            work_identity="GWI-0010-FIXTURE", task_key="GWI-0010-T-rejected",
            repository_identity="example/fixture", branch="main",
        )
        self.pool.record_dispatch(lease["worker_id"], "GWI-0010-FIXTURE", "GWI-0010-T-rejected",
                                  thread_id="thread-rejected", turn_id=None)
        connection = sqlite3.connect(self.state)
        try:
            connection.execute("CREATE TABLE dispatches(work_identity TEXT, task_key TEXT, state TEXT, thread_id TEXT, turn_id TEXT)")
            connection.execute("INSERT INTO dispatches VALUES(?, ?, 'THREAD_CREATED', ?, NULL)",
                               ("GWI-0010-FIXTURE", "GWI-0010-T-rejected", "thread-rejected"))
            connection.commit()
        finally:
            connection.close()

        class NoTurnClient(FakeClient):
            def request(self, method, params):
                if method == "thread/read":
                    return {"thread": {"turns": []}}
                return super().request(method, params)

        with patch.object(server.WorkerPoolConfig, "load", return_value=self.config), \
             patch.object(server, "default_state_path", return_value=self.state), \
             patch.object(server, "_get_default_client", return_value=NoTurnClient()):
            result = asyncio.run(server.mcp.call_tool("release_codex_worker", {
                "worker_id": "worker-01", "work_identity": "GWI-0010-FIXTURE",
                "task_key": "GWI-0010-T-rejected", "confirm_completed": True,
            })).structured_content
        self.assertEqual(result["status"], "RELEASED")
        self.assertEqual(self.pool.status()[0]["state"], "FREE")

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
