from __future__ import annotations

import json
import asyncio
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from local_mcp.dispatch import AppServerTransportError, AppServerUnavailable, DispatchLedger, _validate, dispatch_task
from server import mcp, ping, ping2


class FakeClient:
    def __init__(self, *, unavailable: bool = False, uncertain_turn: bool = False):
        self.unavailable = unavailable
        self.uncertain_turn = uncertain_turn
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.ready_calls = 0

    def ensure_ready(self) -> None:
        self.ready_calls += 1
        if self.unavailable:
            raise AppServerUnavailable("test unavailable")

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.requests.append((method, params))
        if method == "config/read":
            return {"config": {"model": "gpt-6-luna", "model_reasoning_effort": "high"}}
        if method == "model/list":
            return {
                "data": [{
                    "id": "gpt-6-luna",
                    "model": "gpt-6-luna",
                    "isDefault": True,
                    "supportedReasoningEfforts": [
                        {"reasoningEffort": "low"},
                        {"reasoningEffort": "high"},
                    ],
                }],
                "nextCursor": None,
            }
        if method == "thread/start":
            return {"thread": {"id": "thread-123"}, "model": "gpt-6-luna", "reasoningEffort": "high"}
        if method == "turn/start":
            if self.uncertain_turn:
                raise AppServerTransportError("lost acknowledgement", request_sent=True)
            return {"turn": {"id": "turn-456"}}
        if method == "thread/read":
            return {"thread": {"model": "gpt-6-luna", "reasoningEffort": "low"}}
        if method == "thread/name/set":
            return {}
        raise AssertionError(f"unexpected app-server method: {method}")

    def wait_for_turn_started(self, thread_id: str, turn_id: str, timeout: float) -> bool:
        return True


class DispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temp.name)
        self.root = self.temp_root / "repo"
        self.root.mkdir()
        subprocess.run(["git", "init", "-b", "main", str(self.root)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Local MCP Tests"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "local-mcp-tests@example.invalid"], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "remote", "add", "origin", "https://github.com/example/repo.git"],
            check=True,
        )
        request_file = self.root / "TASK_REQUEST.md"
        request_file.write_text(
            "# Task Request\n\nImplement only the requested change.\n", encoding="utf-8"
        )
        subprocess.run(["git", "-C", str(self.root), "add", "TASK_REQUEST.md"], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-m", "Add Task Request fixture"],
            check=True,
            capture_output=True,
        )
        self.state = self.temp_root / "state" / "dispatches.sqlite3"
        self.state.parent.mkdir()
        self.registry = self.temp_root / "repositories.json"
        self.params: dict[str, Any] = {
            "work_identity": "GWI-0010",
            "task_key": "GWI-0010-T001",
            "task_name": "Dispatch probe",
            "task_request_locator": "TASK_REQUEST.md",
            "repository": "example/repo",
            "repository_path": str(self.root),
            "branch": "main",
            "model": None,
            "reasoning_effort": "high",
        }
        self.client = FakeClient()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_registry(self, roots: list[Path] | None = None, *, identity: str = "github.com/example/repo") -> None:
        document = {
            "version": 1,
            "repositories": {identity: [str(path) for path in (roots or [self.root])]},
        }
        self.registry.write_text(json.dumps(document), encoding="utf-8")

    def dispatch(self) -> dict[str, Any]:
        return dispatch_task(
            self.params,
            client_factory=lambda: self.client,
            state_path=self.state,
            registry_path=self.registry,
        )

    def test_ping_and_ping2_keep_existing_responses(self) -> None:
        self.assertEqual(ping(), "LOCAL_MCP_OK")
        self.assertEqual(ping2(), "LOCAL_MCP_OK2")
        ping_result = asyncio.run(mcp.call_tool("ping", {}))
        ping2_result = asyncio.run(mcp.call_tool("ping2", {}))
        self.assertEqual(ping_result.structured_content, {"result": "LOCAL_MCP_OK"})
        self.assertEqual(ping2_result.structured_content, {"result": "LOCAL_MCP_OK2"})

    def test_mcp_catalog_exposes_optional_local_path_override(self) -> None:
        tools = asyncio.run(mcp.list_tools())
        dispatch_tool = next(tool for tool in tools if tool.name == "dispatch_codex_task")
        schema = dispatch_tool.input_schema
        self.assertNotIn("repository_path", schema["required"])
        self.assertIn("repository_path", schema["properties"])
        self.assertIn("repository", schema["required"])
        self.assertIn("task_request_locator", schema["required"])
        self.assertIn("branch", schema["required"])

    def test_explicit_path_override_resolves_and_verifies_logical_identity(self) -> None:
        result = self.dispatch()
        self.assertEqual(result["status"], "DISPATCHED")
        self.assertEqual(result["repositoryIdentity"], "github.com/example/repo")
        self.assertEqual(result["workspaceResolutionSource"], "explicit_repository_path")
        thread_start = next(params for method, params in self.client.requests if method == "thread/start")
        self.assertEqual(thread_start["cwd"], str(self.root))

    def test_legacy_repository_absolute_path_input_remains_supported(self) -> None:
        self.params["repository"] = str(self.root)
        self.params["repository_path"] = None
        result = self.dispatch()
        self.assertEqual(result["status"], "DISPATCHED")
        self.assertEqual(result["repositoryIdentity"], "github.com/example/repo")

    def test_legacy_absolute_task_request_path_remains_supported(self) -> None:
        self.params["repository"] = None
        self.params["repository_path"] = None
        self.params["task_request_locator"] = str(self.root / "TASK_REQUEST.md")
        result = self.dispatch()
        self.assertEqual(result["status"], "DISPATCHED")
        self.assertEqual(result["workspaceResolutionSource"], "legacy_absolute_task_request_path")

    def test_logical_identity_resolves_repository_without_any_local_path_input(self) -> None:
        self.params["repository_path"] = None
        self.write_registry()
        result = self.dispatch()
        self.assertEqual(result["status"], "DISPATCHED")
        self.assertEqual(result["repository"], str(self.root))
        self.assertEqual(result["repositoryIdentity"], "github.com/example/repo")
        self.assertEqual(result["workspaceResolutionSource"], "local_registry")
        thread_start = next(params for method, params in self.client.requests if method == "thread/start")
        self.assertEqual(thread_start["cwd"], str(self.root))

    def test_registry_root_enumerates_linked_worktree_for_requested_branch(self) -> None:
        self.params["repository_path"] = None
        self.params["branch"] = "feature"
        feature_root = self.temp_root / "feature-worktree"
        subprocess.run(
            ["git", "-C", str(self.root), "worktree", "add", "-b", "feature", str(feature_root)],
            check=True,
            capture_output=True,
        )
        self.write_registry()
        result = self.dispatch()
        self.assertEqual(result["status"], "DISPATCHED")
        self.assertEqual(result["repository"], str(feature_root))
        self.assertEqual(result["workspaceResolutionSource"], "local_registry_git_worktree")

    def test_workspace_not_found_returns_recovery_diagnostic(self) -> None:
        self.params["repository_path"] = None
        result = self.dispatch()
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "WORKSPACE_NOT_FOUND")
        self.assertEqual(result["diagnostic"]["failureClass"], "WORKSPACE_NOT_FOUND")
        self.assertEqual(result["diagnostic"]["ambiguous"], False)
        self.assertIn("repositories.json", result["diagnostic"]["recoveryAction"])
        self.assertEqual(self.client.ready_calls, 0)

    def test_same_task_key_can_dispatch_after_pre_dispatch_workspace_hold(self) -> None:
        self.params["repository_path"] = None
        first = self.dispatch()
        self.assertEqual(first["reason"], "WORKSPACE_NOT_FOUND")
        self.write_registry()
        second = self.dispatch()
        self.assertEqual(second["status"], "DISPATCHED")

    def test_ambiguous_registered_workspaces_hold_without_selecting_one(self) -> None:
        self.params["repository_path"] = None
        second_root = self.temp_root / "second-clone"
        subprocess.run(["git", "clone", str(self.root), str(second_root)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(second_root), "remote", "set-url", "origin", "https://github.com/example/repo.git"],
            check=True,
        )
        self.write_registry([self.root, second_root])
        result = self.dispatch()
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "WORKSPACE_AMBIGUOUS")
        self.assertTrue(result["diagnostic"]["ambiguous"])
        self.assertEqual(self.client.ready_calls, 0)

    def test_wrong_repository_identity_holds(self) -> None:
        self.params["repository_path"] = str(self.root)
        self.params["repository"] = "wrong/repo"
        result = self.dispatch()
        self.assertEqual(result["reason"], "WRONG_REPOSITORY")
        self.assertEqual(self.client.ready_calls, 0)

    def test_wrong_branch_holds_before_codex(self) -> None:
        self.params["repository_path"] = None
        self.params["branch"] = "other-branch"
        self.write_registry()
        result = self.dispatch()
        self.assertEqual(result["reason"], "BRANCH_MISMATCH")
        self.assertEqual(self.client.ready_calls, 0)
        self.assertEqual(self.client.requests, [])

    def test_untracked_task_request_holds(self) -> None:
        (self.root / "UNTRACKED_REQUEST.md").write_text("# not tracked\n", encoding="utf-8")
        self.params["task_request_locator"] = "UNTRACKED_REQUEST.md"
        result = self.dispatch()
        self.assertEqual(result["reason"], "TASK_REQUEST_UNTRACKED")
        self.assertEqual(self.client.ready_calls, 0)

    def test_committed_blob_mismatch_holds(self) -> None:
        (self.root / "TASK_REQUEST.md").write_text("# changed after commit\n", encoding="utf-8")
        result = self.dispatch()
        self.assertEqual(result["reason"], "TASK_REQUEST_BLOB_MISMATCH")
        self.assertEqual(self.client.ready_calls, 0)

    def test_repository_without_remote_identity_holds(self) -> None:
        subprocess.run(["git", "-C", str(self.root), "remote", "remove", "origin"], check=True)
        result = self.dispatch()
        self.assertEqual(result["reason"], "REPOSITORY_IDENTITY_UNVERIFIABLE")
        self.assertIn("Git remote", result["message"])

    def test_success_returns_receipt_and_sets_human_readable_name(self) -> None:
        result = self.dispatch()
        self.assertEqual(result["status"], "DISPATCHED")
        self.assertEqual(result["threadId"], "thread-123")
        self.assertEqual(result["turnId"], "turn-456")
        self.assertEqual(result["reasoningEffortReported"], "low")
        self.assertEqual(result["threadName"], "GWI-0010-T001 Dispatch probe")
        self.assertTrue(result["threadNameConfirmed"])
        self.assertEqual(
            [method for method, _ in self.client.requests],
            ["config/read", "model/list", "thread/start", "turn/start", "thread/read", "thread/name/set"],
        )
        thread_params = self.client.requests[2][1]
        self.assertEqual(thread_params["sandbox"], "workspace-write")
        self.assertEqual(thread_params["approvalPolicy"], "never")

    def test_unsupported_model_effort_is_held_before_thread_creation(self) -> None:
        self.params["reasoning_effort"] = "ultra"
        result = self.dispatch()
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "MODEL_CONFIGURATION_ERROR")
        self.assertNotIn("thread/start", [method for method, _ in self.client.requests])
        self.params["reasoning_effort"] = "high"
        retried = self.dispatch()
        self.assertEqual(retried["status"], "DISPATCHED")

    def test_codex_unavailable_holds_without_starting(self) -> None:
        self.client.unavailable = True
        result = self.dispatch()
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "CODEX_UNAVAILABLE")
        self.assertEqual(self.client.requests, [])

    def test_accepted_duplicate_returns_receipt_without_second_turn(self) -> None:
        first = self.dispatch()
        calls_after_first = len(self.client.requests)
        second = self.dispatch()
        self.assertEqual(first["status"], "DISPATCHED")
        self.assertEqual(second["status"], "ALREADY_DISPATCHED")
        self.assertEqual(len(self.client.requests), calls_after_first)

    def test_preexisting_v0_ledger_receipt_survives_schema_migration(self) -> None:
        data = _validate(self.params, registry_path=self.registry)
        old_request_hash = DispatchLedger._request_hash(data)
        connection = sqlite3.connect(self.state)
        try:
            connection.execute(
                """CREATE TABLE dispatches (
                    work_identity TEXT NOT NULL,
                    task_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    task_request_locator TEXT NOT NULL,
                    repository TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    repository_commit TEXT NOT NULL,
                    task_request_blob_id TEXT NOT NULL,
                    thread_name TEXT NOT NULL,
                    model_requested TEXT,
                    reasoning_effort_requested TEXT,
                    state TEXT NOT NULL,
                    thread_id TEXT,
                    turn_id TEXT,
                    model_reported TEXT,
                    reasoning_effort_reported TEXT,
                    dispatched_at TEXT,
                    thread_name_confirmed INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (work_identity, task_key)
                )"""
            )
            connection.execute(
                """INSERT INTO dispatches (
                    work_identity, task_key, request_hash, task_name, task_request_locator,
                    repository, branch, repository_commit, task_request_blob_id, thread_name,
                    model_requested, reasoning_effort_requested, state, thread_id, turn_id,
                    dispatched_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACCEPTED', ?, ?, ?, ?)""",
                (
                    data["work_identity"], data["task_key"], old_request_hash, data["task_name"],
                    data["task_request_locator"], data["repository"], data["branch"],
                    data["repository_commit"], data["task_request_blob_id"], data["thread_name"],
                    data["model"], data["reasoning_effort"], "legacy-thread", "legacy-turn",
                    "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z",
                ),
            )
            connection.commit()
        finally:
            connection.close()
        result = self.dispatch()
        self.assertEqual(result["status"], "ALREADY_DISPATCHED")
        self.assertEqual(result["threadId"], "legacy-thread")
        self.assertIsNone(result["repositoryIdentity"])
        self.assertEqual(self.client.requests, [])

    def test_unknown_turn_outcome_blocks_duplicate_retry(self) -> None:
        self.client.uncertain_turn = True
        first = self.dispatch()
        self.assertEqual(first["reason"], "DISPATCH_OUTCOME_UNKNOWN")
        calls_after_first = len(self.client.requests)
        second = self.dispatch()
        self.assertEqual(second["reason"], "DISPATCH_OUTCOME_UNKNOWN")
        self.assertEqual(len(self.client.requests), calls_after_first)

    def test_changed_payload_with_same_identity_key_is_held(self) -> None:
        self.dispatch()
        self.params["task_name"] = "Different task name"
        result = self.dispatch()
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "IDEMPOTENCY_KEY_CONFLICT")


if __name__ == "__main__":
    unittest.main()
