from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import server
from local_mcp.unity_project_open import open_leased_unity_project
from local_mcp.worker_pool import ManagedRepository, WorkerPoolConfig


UNITY_VERSION = "6000.3.9f1"
WORKER_ID = "worker-01"
WORK_IDENTITY = "GWI-0010"
TASK_KEY = "GWI-0010-T012"
HOST_ENV = {
    "USERNAME": "sennn",
    "USERDOMAIN": "DESKTOP-U5FJ9NG",
    "LOCALAPPDATA": r"C:\Users\sennn\AppData\Local",
    "PATH": r"C:\Windows\System32",
    "CONTROL_PLANE_API_KEY": "local-operations-secret",
}


def completed(command, *, code=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(command, code, stdout=stdout, stderr=stderr)


def status_payload(instances):
    return json.dumps({
        "success": True,
        "command": "status",
        "data": {"count": len(instances), "instances": instances},
        "errors": [],
    })


def editor_instance(path, *, state="ready", version=UNITY_VERSION, pid=2416, port=7800, **extra):
    return {
        "state": state,
        "projectPath": path,
        "editorVersion": version,
        "pid": pid,
        "pipelinePort": port,
        **extra,
    }


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class FakeRunner:
    def __init__(self, project_statuses, *, editor_versions=None, open_error=None):
        self.project_statuses = list(project_statuses)
        self.editor_versions = list(editor_versions or [UNITY_VERSION])
        self.open_error = open_error
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((list(command), kwargs))
        if command[1] == "editors":
            data = [{"version": version, "location": r"C:\Unity\Editor"} for version in self.editor_versions]
            return completed(command, stdout=json.dumps({"success": True, "data": data}))
        if command[1] == "open":
            if self.open_error is not None:
                raise self.open_error
            return completed(command, stdout=json.dumps({"success": True, "command": "open"}))
        if command[1] == "status":
            if self.project_statuses:
                value = self.project_statuses.pop(0)
                if isinstance(value, BaseException):
                    raise value
                return completed(command, stdout=value)
            if self.project_statuses:
                return completed(command, stdout=self.project_statuses[-1])
            return completed(command, stdout=status_payload([]))
        raise AssertionError(f"unexpected Unity CLI command: {command[1]}")


class FakeWorkerPool:
    def __init__(self, worker_root: Path):
        self.repository = ManagedRepository(
            "example/unity-game", "https://github.com/example/unity-game.git", "main", "unity-game"
        )
        self.config = WorkerPoolConfig(1, worker_root, (self.repository,))
        self.active = True
        self.lease = {
            "worker_id": WORKER_ID,
            "state": "LEASED",
            "work_identity": WORK_IDENTITY,
            "task_key": TASK_KEY,
            "repository_identity": self.repository.identity,
        }

    def get_lease(self, worker_id, work_identity, task_key):
        if not self.active:
            return None
        if (worker_id, work_identity, task_key) != (WORKER_ID, WORK_IDENTITY, TASK_KEY):
            return None
        return dict(self.lease)


class UnityProjectOpenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="local-operations-unity-open-")
        self.root = Path(self.temp.name)
        self.worker_root = self.root / "workers"
        self.pool = FakeWorkerPool(self.worker_root)
        self.project = self.pool.config.repository_path(WORKER_ID, self.pool.repository)
        self.project.mkdir(parents=True)
        (self.project / ".git").mkdir()
        (self.project / "Assets").mkdir()
        settings = self.project / "ProjectSettings"
        settings.mkdir()
        (settings / "ProjectVersion.txt").write_text(
            f"m_EditorVersion: {UNITY_VERSION}\nm_EditorVersionWithRevision: abcdef\n",
            encoding="utf-8",
        )
        self.project_path = str(self.project.resolve())

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, runner, **kwargs):
        options = {
            "worker_pool": self.pool,
            "environment": HOST_ENV,
            "runner": runner,
            "exists": lambda _path: True,
            "which": lambda *_args, **_kwargs: None,
            "readiness_timeout_seconds": 4,
            **kwargs,
        }
        return open_leased_unity_project(WORKER_ID, WORK_IDENTITY, TASK_KEY, **options)

    def test_active_lease_resolves_managed_project_and_opens_declared_version(self):
        runner = FakeRunner([
            status_payload([]),
            status_payload([editor_instance(self.project_path, accessToken="pipeline-secret")]),
        ])

        result = self.invoke(runner)

        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["verdict"], "OPENED_READY")
        self.assertEqual(result["projectPath"], self.project_path)
        self.assertEqual(result["projectEditorVersion"], UNITY_VERSION)
        self.assertEqual(result["observedEditorVersion"], UNITY_VERSION)
        self.assertEqual(result["hostUser"], r"DESKTOP-U5FJ9NG\sennn")
        self.assertTrue(result["projectReadyUniquely"])
        self.assertTrue(result["openRequestSent"])
        self.assertTrue(result["opened"])

        open_call = next(call for call, _ in runner.calls if call[1] == "open")
        self.assertEqual(open_call[2], self.project_path)
        self.assertEqual(open_call[open_call.index("--editor-version") + 1], UNITY_VERSION)
        self.assertNotIn("--allow-install", open_call)
        self.assertTrue(all(call_kwargs["shell"] is False for _, call_kwargs in runner.calls))
        self.assertNotIn("CONTROL_PLANE_API_KEY", runner.calls[0][1]["env"])

    def test_worker_work_and_task_mismatches_are_rejected_before_cli(self):
        runner = FakeRunner([])
        for worker_id, work_identity, task_key in (
            ("worker-02", WORK_IDENTITY, TASK_KEY),
            (WORKER_ID, "GWI-OTHER", TASK_KEY),
            (WORKER_ID, WORK_IDENTITY, "GWI-0010-T999"),
        ):
            with self.subTest(worker_id=worker_id, work_identity=work_identity, task_key=task_key):
                result = open_leased_unity_project(
                    worker_id, work_identity, task_key,
                    worker_pool=self.pool,
                    environment=HOST_ENV,
                    runner=runner,
                    exists=lambda _path: True,
                )
                self.assertEqual(result["status"], "HOLD")
                self.assertEqual(result["reason"], "WORKER_LEASE_NOT_FOUND")
        self.assertEqual(runner.calls, [])

    def test_non_unity_managed_repository_is_rejected(self):
        (self.project / "Assets").rmdir()
        runner = FakeRunner([])

        result = self.invoke(runner)

        self.assertEqual(result["reason"], "NOT_UNITY_PROJECT")
        self.assertEqual(runner.calls, [])

    def test_missing_or_invalid_project_version_is_held(self):
        (self.project / "ProjectSettings" / "ProjectVersion.txt").write_text(
            "m_EditorVersion: latest\n", encoding="utf-8"
        )
        runner = FakeRunner([])

        result = self.invoke(runner)

        self.assertEqual(result["reason"], "PROJECT_VERSION_UNAVAILABLE")
        self.assertEqual(runner.calls, [])

    def test_required_editor_not_installed_is_held_without_open(self):
        runner = FakeRunner([status_payload([])], editor_versions=["2021.3.16f1"])

        result = self.invoke(runner)

        self.assertEqual(result["reason"], "UNITY_EDITOR_UNAVAILABLE")
        self.assertEqual([call[1] for call, _ in runner.calls], ["editors"])

    def test_exactly_ready_target_returns_idempotent_success(self):
        runner = FakeRunner([status_payload([editor_instance(self.project_path)])])

        result = self.invoke(runner)

        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["verdict"], "ALREADY_READY")
        self.assertFalse(result["openRequestSent"])
        self.assertFalse(result["opened"])
        self.assertEqual([call[1] for call, _ in runner.calls], ["editors", "status"])

    def test_duplicate_target_instances_are_held(self):
        runner = FakeRunner([status_payload([
            editor_instance(self.project_path, pid=1001),
            editor_instance(self.project_path, pid=1002),
        ])])

        result = self.invoke(runner)

        self.assertEqual(result["reason"], "TARGET_PROJECT_AMBIGUOUS")
        self.assertFalse(result["openRequestSent"])
        self.assertNotIn("open", [call[1] for call, _ in runner.calls])

    def test_similar_other_project_is_not_mistaken_for_target(self):
        other_path = self.project_path + "-old"
        runner = FakeRunner([
            status_payload([editor_instance(other_path, pid=1001)]),
            status_payload([
                editor_instance(other_path, pid=1001),
                editor_instance(self.project_path, pid=1002),
            ]),
        ])

        result = self.invoke(runner)

        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["verdict"], "OPENED_READY")
        self.assertEqual(result["projectPath"], self.project_path)
        self.assertEqual(result["pid"], 1002)

    def test_descriptor_token_and_raw_cli_output_are_not_returned(self):
        runner = FakeRunner([status_payload([
            editor_instance(
                self.project_path,
                accessToken="pipeline-bearer-secret",
                descriptorPath=r"C:\private\.unity-pipeline-port",
                rawJson="unfiltered-output",
            )
        ])])

        result = self.invoke(runner)
        encoded = json.dumps(result)

        self.assertEqual(result["verdict"], "ALREADY_READY")
        for secret in ("pipeline-bearer-secret", ".unity-pipeline-port", "unfiltered-output", "local-operations-secret"):
            self.assertNotIn(secret, encoded)
        self.assertFalse(any("token" in key.casefold() or "descriptor" in key.casefold() for key in result))

    def test_readiness_timeout_returns_hold_without_editor_termination(self):
        runner = FakeRunner([status_payload([])])
        clock = FakeClock()

        result = self.invoke(
            runner,
            clock=clock,
            sleep=clock.sleep,
            readiness_timeout_seconds=3,
        )

        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "UNITY_EDITOR_NOT_READY")
        self.assertTrue(result["openRequestSent"])
        self.assertIsNone(result["opened"])
        self.assertEqual([call[1] for call, _ in runner.calls].count("open"), 1)
        self.assertNotIn("close", [call[1] for call, _ in runner.calls])
        self.assertFalse(any(call[0].endswith(("taskkill", "kill", "terminate")) for call, _ in runner.calls))

    def test_open_timeout_is_reported_as_unverified_without_close(self):
        runner = FakeRunner([status_payload([])], open_error=subprocess.TimeoutExpired(["unity", "open"], 10))

        result = self.invoke(runner)

        self.assertEqual(result["reason"], "UNITY_OPEN_TIMEOUT")
        self.assertTrue(result["openRequestSent"])
        self.assertIsNone(result["opened"])
        self.assertNotIn("close", [call[1] for call, _ in runner.calls])

    def test_mcp_tool_exposes_lease_identity_only(self):
        tools = asyncio.run(server.mcp.list_tools())
        tool = next(item for item in tools if item.name == "open_leased_unity_project")
        properties = set(tool.model_dump()["input_schema"]["properties"])

        self.assertEqual(properties, {"worker_id", "work_identity", "task_key"})
        self.assertNotIn("project_path", properties)
        self.assertNotIn("command", properties)

        expected = {"status": "HOLD", "reason": "FIXTURE"}
        with patch("server._open_leased_unity_project", return_value=expected):
            response = asyncio.run(server.mcp.call_tool("open_leased_unity_project", {
                "worker_id": WORKER_ID,
                "work_identity": WORK_IDENTITY,
                "task_key": TASK_KEY,
            }))
        self.assertEqual(response.structured_content, expected)


if __name__ == "__main__":
    unittest.main()
