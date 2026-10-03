from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

import server
from local_mcp.dispatch import AppServerClient, dispatch_task
from local_mcp.finalize import finalize_task
from local_mcp.worker_pool import ManagedRepository, WorkerPool, WorkerPoolConfig


@unittest.skipUnless(
    os.environ.get("LOCAL_MCP_RUN_LIVE_APP_SERVER_TESTS") == "1",
    "set LOCAL_MCP_RUN_LIVE_APP_SERVER_TESTS=1 to run the Development Result persistence E2E probe",
)
class LiveAppServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="local-operations-dev-e2e-")
        self.base = Path(self.temp.name)
        self.bare = self.base / "probe-origin.git"
        subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(self.bare)], check=True, capture_output=True)
        seed = self.base / "seed"
        subprocess.run(["git", "clone", str(self.bare), str(seed)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(seed), "config", "user.name", "Local Operations E2E"], check=True)
        subprocess.run(["git", "-C", str(seed), "config", "user.email", "local-operations-e2e@example.invalid"], check=True)
        (seed / "TASK_REQUEST.md").write_text(
            "# Local Operations Development E2E\n\n"
            "Local Operations has selected this repository and branch. No Git identity or revision "
            "check is needed. Use your file editing tool to create `DEV_E2E_RESULT.md` in the repository "
            "root containing exactly `LOCAL_OPERATIONS_WORKER_E2E_OK`, then return that text as your "
            "final response. Do not run Git commands or contact remote services.\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(seed), "add", "TASK_REQUEST.md"], check=True)
        subprocess.run(["git", "-C", str(seed), "commit", "-m", "Add read-only local E2E request"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(seed), "push", "-u", "origin", "main"], check=True, capture_output=True)

        self.identity = "github.com/local-operations-probe/worker-e2e"
        clone_url = "https://github.com/local-operations-probe/worker-e2e.git"
        managed = ManagedRepository("local-operations-probe/worker-e2e", clone_url, "main", "worker-e2e")
        self.worker_root = self.base / "workers"
        self.config = WorkerPoolConfig(1, self.worker_root, (managed,))
        worker_repo = self.config.repository_path("worker-01", managed)
        worker_repo.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--branch", "main", str(self.bare), str(worker_repo)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(worker_repo), "remote", "set-url", "origin", clone_url], check=True)
        subprocess.run(
            ["git", "-C", str(worker_repo), "config", f"url.{self.bare.as_uri()}.insteadOf", clone_url],
            check=True,
        )
        self.pool = WorkerPool(self.config, self.base / "dispatch-ledger.sqlite3")
        self.pool.bootstrap()
        self.pool_config_path = self.base / "worker-pool.json"
        self.pool_config_path.write_text(json.dumps({
            "version": 1, "workerCount": 1,
            "repositories": [{"identity": "local-operations-probe/worker-e2e", "cloneUrl": clone_url, "defaultBranch": "main"}],
        }), encoding="utf-8")
        self.client = AppServerClient()
        self.original_dispatch = server.dispatch_task
        self.original_finalize = server.finalize_task

    def tearDown(self) -> None:
        self.client.close()
        server.dispatch_task = self.original_dispatch
        server.finalize_task = self.original_finalize
        self.temp.cleanup()

    def test_dev_runtime_dispatch_result_finalize_push_and_release(self) -> None:
        task_key = f"GWI-0010-DEV-WORKER-PROBE-{uuid.uuid4().hex[:8].upper()}"
        params = {
            "work_identity": "GWI-0010-LOCAL-OPERATIONS-DEV-E2E",
            "task_key": task_key,
            "task_name": "Create harmless Result file",
            "task_request_locator": "TASK_REQUEST.md",
            "repository": "local-operations-probe/worker-e2e",
            "branch": "main",
            "model": "gpt-6-luna",
            "reasoning_effort": "low",
        }
        server.dispatch_task = lambda payload: dispatch_task(
            payload,
            client_factory=lambda: self.client,
            state_path=self.base / "dispatch-ledger.sqlite3",
            worker_pool_config_path=self.pool_config_path,
            worker_root=self.worker_root,
        )
        server.finalize_task = lambda payload: finalize_task(
            payload, client_factory=lambda: self.client,
            state_path=self.base / "dispatch-ledger.sqlite3",
            config_path=self.pool_config_path, worker_root=self.worker_root,
        )

        result = asyncio.run(server.mcp.call_tool("dispatch_codex_task", params))
        self.assertFalse(result.is_error)
        receipt = result.structured_content
        print("DEVELOPMENT_WORKER_E2E_RECEIPT=" + json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        self.assertEqual(receipt["status"], "DISPATCHED")
        self.assertEqual(receipt["workerId"], "worker-01")
        self.assertEqual(receipt["repositoryIdentity"], self.identity)
        self.assertEqual(receipt["taskRequestLocator"], "TASK_REQUEST.md")
        self.assertEqual(receipt["workspaceResolutionSource"], "fixed_worker_pool")
        self.assertEqual(receipt["resolvedRepositoryRoot"], str(self.config.repository_path("worker-01", self.config.repositories[0]).resolve()))

        completed = self.client.wait_for_turn_completed(receipt["threadId"], receipt["turnId"], timeout=240)
        self.assertIsNotNone(completed, "Codex did not complete the harmless Result probe in 240 seconds")
        self.assertEqual(completed.get("status"), "completed")
        print("DEVELOPMENT_E2E_COMPLETED_TURN=" + json.dumps(completed, ensure_ascii=True, sort_keys=True))
        thread_state = self.client.request("thread/read", {"threadId": receipt["threadId"], "includeTurns": False}).get("thread")
        print("DEVELOPMENT_E2E_THREAD_CWD=" + str(thread_state.get("cwd") if isinstance(thread_state, dict) else None))
        items = completed.get("items")
        final_text = next((item.get("text", "") for item in reversed(items or []) if isinstance(item, dict) and item.get("type") == "agentMessage"), "")
        if "C:\\" in final_text and "HOLD" in final_text:
            self.skipTest("the local Codex app-server launched PowerShell at C:\\ instead of the temporary fixture cwd")
        result_path = Path(receipt["resolvedRepositoryRoot"]) / "DEV_E2E_RESULT.md"
        self.assertTrue(result_path.exists(), "Codex did not create the harmless Result file")
        self.assertEqual(result_path.read_text(encoding="utf-8").strip(), "LOCAL_OPERATIONS_WORKER_E2E_OK")

        finalized = asyncio.run(server.mcp.call_tool("finalize_codex_task", {
            "worker_id": "worker-01",
            "work_identity": params["work_identity"],
            "task_key": task_key,
        }))
        final_result = finalized.structured_content
        print("DEVELOPMENT_FINALIZE_E2E_RESULT=" + json.dumps(final_result, ensure_ascii=False, sort_keys=True))
        self.assertEqual(final_result["status"], "FINALIZED")
        self.assertEqual(final_result["codexTurnStatus"], "completed")
        self.assertIn("LOCAL_OPERATIONS_WORKER_E2E_OK", final_result["finalAgentMessage"])
        self.assertTrue(final_result["commitSha"])
        self.assertEqual(final_result["pushStatus"], "PUSHED")
        self.assertIn("DEV_E2E_RESULT.md", final_result["changedPaths"])
        self.assertEqual(subprocess.run(
            ["git", "-C", str(self.bare), "rev-parse", "refs/heads/main"],
            check=True, capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip(), final_result["commitSha"])
        self.assertEqual(final_result["workerState"], "FREE")
        self.assertEqual(self.pool.status()[0]["state"], "FREE")
        self.assertEqual(subprocess.run(
            ["git", "-C", receipt["resolvedRepositoryRoot"], "branch", "--show-current"],
            check=True, capture_output=True, text=True,
        ).stdout.strip(), "main")


if __name__ == "__main__":
    unittest.main()
