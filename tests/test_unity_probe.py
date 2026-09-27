from __future__ import annotations

import asyncio
import json
import subprocess
import unittest
from unittest.mock import patch

from local_mcp.unity_probe import (
    PREFERRED_UNITY_CLI,
    T008_EDITOR_VERSION,
    T008_PROJECT_PATH,
    _is_t008_match,
    _probe_unity_host_connectivity,
)
from server import mcp


HOST_ENV = {
    "USERNAME": "sennn",
    "USERDOMAIN": "DESKTOP-U5FJ9NG",
    "USERPROFILE": r"C:\Users\sennn",
    "LOCALAPPDATA": r"C:\Users\sennn\AppData\Local",
    "APPDATA": r"C:\Users\sennn\AppData\Roaming",
    "PATH": r"C:\Windows\System32",
    "CONTROL_PLANE_API_KEY": "secret-environment-value",
}


class QueueRunner:
    def __init__(self, results):
        self.results = list(results)
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, command, **kwargs):
        self.calls.append((list(command), kwargs))
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def completed(command, *, code=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(command, code, stdout=stdout, stderr=stderr)


def probe(runner, *, exists=lambda _path: True, which=lambda *_args, **_kwargs: None):
    return _probe_unity_host_connectivity(
        environment=HOST_ENV,
        runner=runner,
        preferred_path=PREFERRED_UNITY_CLI,
        exists=exists,
        which=which,
    )


class UnityProbeTests(unittest.TestCase):
    def test_ready_t008_instance_is_a_direct_match_and_uses_only_read_only_commands(self):
        payload = {
            "success": True,
            "count": 1,
            "instances": [{
                "state": "ready",
                "projectPath": T008_PROJECT_PATH,
                "editorVersion": T008_EDITOR_VERSION,
                "pid": 5352,
                "pipelinePort": 7800,
                "extraCredential": "never-return-this-token",
            }],
        }
        runner = QueueRunner([
            completed([str(PREFERRED_UNITY_CLI), "--version"], stdout="1.0.0-beta.9\n"),
            completed([str(PREFERRED_UNITY_CLI), "status"], stdout=json.dumps(payload)),
        ])

        result = probe(runner)

        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["verdict"], "DIRECT_MATCH")
        self.assertEqual(result["unityCliVersion"], "1.0.0-beta.9")
        self.assertEqual(result["instanceCount"], 1)
        self.assertEqual(result["instances"], [{
            "state": "ready",
            "projectPath": T008_PROJECT_PATH,
            "editorVersion": T008_EDITOR_VERSION,
            "pid": 5352,
            "pipelinePort": 7800,
        }])
        self.assertEqual(runner.calls[0][0], [str(PREFERRED_UNITY_CLI), "--version"])
        self.assertEqual(runner.calls[1][0], [
            str(PREFERRED_UNITY_CLI), "status", "--format", "json", "--no-banner", "--non-interactive"
        ])
        self.assertTrue(all(call[1]["timeout"] == 8 for call in runner.calls))
        self.assertTrue(all(call[1]["shell"] is False for call in runner.calls))

    def test_zero_instances_is_a_hold_without_exposing_other_environment_values(self):
        payload = {"success": True, "count": 0, "instances": [], "accessToken": "secret-output-value"}
        runner = QueueRunner([
            completed([], stdout="1.0.0-beta.9"),
            completed([], stdout=json.dumps(payload)),
        ])

        result = probe(runner)

        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["verdict"], "NO_INSTANCE")
        self.assertEqual(result["success"], True)
        self.assertEqual(result["instanceCount"], 0)
        self.assertEqual(result["instances"], [])
        self.assertEqual(result["hostUser"], r"DESKTOP-U5FJ9NG\sennn")
        self.assertEqual(result["userProfile"], HOST_ENV["USERPROFILE"])
        self.assertEqual(result["localAppData"], HOST_ENV["LOCALAPPDATA"])
        self.assertEqual(result["appData"], HOST_ENV["APPDATA"])
        self.assertNotIn("PATH", result)
        self.assertNotIn("CONTROL_PLANE_API_KEY", result)
        self.assertNotIn("accessToken", json.dumps(result))
        self.assertNotIn("secret-environment-value", json.dumps(result))
        self.assertNotIn("secret-output-value", json.dumps(result))

    def test_cli_unavailable_uses_only_fixed_path_then_path_lookup(self):
        runner = QueueRunner([])
        lookups: list[tuple[str, str | None]] = []

        def which(name, *, path):
            lookups.append((name, path))
            return None

        result = probe(runner, exists=lambda _path: False, which=which)

        self.assertEqual(result["verdict"], "CLI_UNAVAILABLE")
        self.assertEqual(result["unityCliPath"], None)
        self.assertEqual(runner.calls, [])
        self.assertEqual(lookups, [("unity", HOST_ENV["PATH"])])

    def test_path_lookup_is_used_when_preferred_cli_is_missing(self):
        cli = r"D:\Tools\Unity\unity.exe"
        runner = QueueRunner([
            completed([], stdout="1.0.0-beta.9"),
            completed([], stdout=json.dumps({"success": True, "count": 0, "instances": []})),
        ])
        lookups: list[tuple[str, str | None]] = []

        def which(name, *, path):
            lookups.append((name, path))
            return cli

        result = probe(runner, exists=lambda _path: False, which=which)

        self.assertEqual(result["unityCliPath"], cli)
        self.assertEqual(lookups, [("unity", HOST_ENV["PATH"])])
        self.assertTrue(all(call[0][0] == cli for call in runner.calls))

    def test_nonzero_status_is_a_hold_without_returning_raw_stderr(self):
        runner = QueueRunner([
            completed([], stdout="1.0.0-beta.9"),
            completed([], code=6, stdout='{"success":false,"token":"secret"}', stderr="secret-error"),
        ])

        result = probe(runner)

        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["verdict"], "STATUS_FAILED")
        self.assertEqual(result["unityStatusExitCode"], 6)
        self.assertNotIn("secret", json.dumps(result))
        self.assertNotIn("stderr", result)

    def test_credential_like_fields_are_ignored_and_instance_fields_are_allowlisted(self):
        payload = {
            "success": True,
            "count": 1,
            "apiKey": "top-level-secret",
            "instances": [{
                "state": "ready",
                "projectPath": T008_PROJECT_PATH,
                "editorVersion": T008_EDITOR_VERSION,
                "pid": 5352,
                "pipelinePort": 7800,
                "accessToken": "instance-secret",
                "commandLine": "--token raw-secret",
            }],
        }
        runner = QueueRunner([
            completed([], stdout="Unity CLI version 1.0.0-beta.9"),
            completed([], stdout=json.dumps(payload)),
        ])

        result = probe(runner)

        self.assertEqual(set(result), {
            "status", "hostUser", "userProfile", "localAppData", "appData", "unityCliPath",
            "unityCliVersion", "unityStatusExitCode", "success", "instanceCount", "instances",
            "verdict",
        })
        self.assertEqual(set(result["instances"][0]), {
            "state", "projectPath", "editorVersion", "pid", "pipelinePort",
        })
        serialized = json.dumps(result)
        for secret in ("top-level-secret", "instance-secret", "raw-secret", "commandLine", "accessToken", "apiKey"):
            self.assertNotIn(secret, serialized)

    def test_nonmatching_project_editor_is_identity_mismatch(self):
        payload = {
            "success": True,
            "count": 1,
            "instances": [{
                "state": "ready",
                "projectPath": r"C:\Other\Project",
                "editorVersion": T008_EDITOR_VERSION,
                "pid": 12,
            }],
        }
        runner = QueueRunner([
            completed([], stdout="1.0.0-beta.9"),
            completed([], stdout=json.dumps(payload)),
        ])

        result = probe(runner)

        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["verdict"], "IDENTITY_MISMATCH")

    def test_cli_status_timeout_returns_hold(self):
        runner = QueueRunner([
            completed([], stdout="1.0.0-beta.9"),
            subprocess.TimeoutExpired("unity status", 8),
        ])

        result = probe(runner)

        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["verdict"], "STATUS_FAILED")
        self.assertEqual(result["reason"], "UNITY_STATUS_TIMEOUT")

    def test_t008_match_normalizes_windows_case_and_trailing_separator(self):
        self.assertTrue(_is_t008_match([{
            "state": "READY",
            "projectPath": T008_PROJECT_PATH.lower() + "\\",
            "editorVersion": T008_EDITOR_VERSION,
        }]))

    def test_t008_match_is_found_beyond_returned_instance_limit(self):
        other_instances = [{
            "state": "ready",
            "projectPath": rf"C:\Other\Project{index}",
            "editorVersion": T008_EDITOR_VERSION,
        } for index in range(32)]
        payload = {
            "success": True,
            "count": 33,
            "instances": other_instances + [{
                "state": "ready",
                "projectPath": T008_PROJECT_PATH,
                "editorVersion": T008_EDITOR_VERSION,
                "pid": 5352,
            }],
        }
        runner = QueueRunner([
            completed([], stdout="1.0.0-beta.9"),
            completed([], stdout=json.dumps(payload)),
        ])

        result = probe(runner)

        self.assertEqual(result["verdict"], "DIRECT_MATCH")
        self.assertEqual(result["instanceCount"], 33)
        self.assertEqual(len(result["instances"]), 32)
        self.assertTrue(any(row["projectPath"] == T008_PROJECT_PATH for row in result["instances"]))

    def test_registered_mcp_tool_has_no_arguments_and_delegates(self):
        expected = {"status": "HOLD", "verdict": "NO_INSTANCE"}
        with patch("server._probe_unity_host_connectivity", return_value=expected):
            response = asyncio.run(mcp.call_tool("probe_unity_host_connectivity", {}))

        self.assertEqual(response.structured_content, expected)


if __name__ == "__main__":
    unittest.main()
