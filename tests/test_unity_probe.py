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
    def __init__(self, results, *, pipeline_results=None, handshake_results=None):
        self.results = list(results)
        self.pipeline_results = list(pipeline_results or [
            completed([], stdout=json.dumps({"success": True, "pipelines": []}))
        ])
        self.handshake_results = list(handshake_results or [
            completed([], code=1, stdout=json.dumps({
                "success": False,
                "errors": [{"code": "NO_CONNECTED_EDITOR", "message": "not returned"}],
            }))
        ])
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, command, **kwargs):
        self.calls.append((list(command), kwargs))
        if len(command) > 1 and command[1] == "pipeline":
            result = self.pipeline_results.pop(0)
        elif len(command) > 1 and command[1] == "list":
            result = self.handshake_results.pop(0)
        else:
            result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def completed(command, *, code=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(command, code, stdout=stdout, stderr=stderr)


def probe(
    runner,
    *,
    exists=lambda _path: True,
    which=lambda *_args, **_kwargs: None,
    process_observer=lambda: {"present": False, "pids": [], "complete": True},
):
    return _probe_unity_host_connectivity(
        environment=HOST_ENV,
        runner=runner,
        preferred_path=PREFERRED_UNITY_CLI,
        exists=exists,
        which=which,
        process_observer=process_observer,
    )


class UnityProbeTests(unittest.TestCase):
    def test_installed_cli_status_envelope_matches_target_editor(self):
        runner = QueueRunner([
            completed([], stdout="1.0.0-beta.9"),
            completed([], stdout=json.dumps({
                "success": True,
                "command": "status",
                "data": {"count": 1, "instances": [{
                    "state": "ready",
                    "project": T008_PROJECT_PATH,
                    "version": T008_EDITOR_VERSION,
                    "pid": 5352,
                    "port": 7800,
                    "accessToken": "never-return-this-token",
                }]},
                "errors": [],
            })),
        ])

        result = probe(runner)

        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["verdict"], "DIRECT_MATCH")
        self.assertEqual(result["instanceCount"], 1)
        self.assertEqual(result["instances"], [{
            "state": "ready",
            "projectPath": T008_PROJECT_PATH,
            "editorVersion": T008_EDITOR_VERSION,
            "pid": 5352,
            "pipelinePort": 7800,
        }])
        self.assertNotIn("never-return-this-token", json.dumps(result))

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
        self.assertEqual(result["diagnosis"], "DIRECT_MATCH")
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
            str(PREFERRED_UNITY_CLI), "pipeline", "list", "--format", "json", "--no-banner", "--non-interactive"
        ])
        self.assertEqual(runner.calls[2][0], [
            str(PREFERRED_UNITY_CLI), "list", "--project-path", T008_PROJECT_PATH,
            "--format", "json", "--no-banner", "--non-interactive"
        ])
        self.assertEqual(runner.calls[3][0], [
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
        self.assertEqual(result["diagnosis"], "EDITOR_PROCESS_ABSENT")
        self.assertFalse(result["pipelineDiagnostic"]["candidateCount"])

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
            "verdict", "diagnosis", "editorProcessPresent", "editorProcessIds", "pipelineDiagnostic",
            "pipelineHandshake",
        })
        self.assertEqual(set(result["instances"][0]), {
            "state", "projectPath", "editorVersion", "pid", "pipelinePort",
        })
        serialized = json.dumps(result)
        for secret in ("top-level-secret", "instance-secret", "raw-secret", "commandLine", "accessToken", "apiKey"):
            self.assertNotIn(secret, serialized)

    def test_editor_process_present_with_empty_status_reports_pipeline_not_visible(self):
        runner = QueueRunner([
            completed([], stdout="1.0.0-beta.9"),
            completed([], stdout=json.dumps({"success": True, "instances": []})),
        ])

        result = probe(
            runner,
            process_observer=lambda: {"present": True, "pids": [1234], "complete": True},
        )

        self.assertEqual(result["diagnosis"], "EDITOR_PRESENT_PIPELINE_NOT_VISIBLE")
        self.assertEqual(result["editorProcessPresent"], True)
        self.assertEqual(result["editorProcessIds"], [1234])
        self.assertTrue(result["pipelineDiagnostic"]["available"])
        self.assertEqual(result["pipelineDiagnostic"]["candidateCount"], 0)

    def test_pipeline_candidate_with_empty_status_is_reported_without_raw_fields(self):
        runner = QueueRunner(
            [
                completed([], stdout="1.0.0-beta.9"),
                completed([], stdout=json.dumps({"success": True, "instances": []})),
            ],
            pipeline_results=[completed([], stdout=json.dumps({
                "success": True,
                "pipelines": [{
                    "pid": 4321,
                    "state": "ready",
                    "safeMode": False,
                    "apiKey": "pipeline-secret",
                    "commandLine": "--token pipeline-command-line",
                }],
            }))],
        )

        result = probe(
            runner,
            process_observer=lambda: {"present": True, "pids": [4321], "complete": True},
        )

        self.assertEqual(result["diagnosis"], "PIPELINE_VISIBLE_STATUS_EMPTY")
        self.assertEqual(result["pipelineDiagnostic"]["candidateCount"], 1)
        serialized = json.dumps(result)
        for secret in ("pipeline-secret", "pipeline-command-line", "apiKey", "commandLine"):
            self.assertNotIn(secret, serialized)

    def test_safe_mode_and_compiling_state_are_bounded_diagnostics(self):
        runner = QueueRunner(
            [
                completed([], stdout="1.0.0-beta.9"),
                completed([], stdout=json.dumps({"success": True, "instances": []})),
            ],
            pipeline_results=[completed([], stdout=json.dumps({
                "pipelines": [{"state": "safe_mode", "isCompiling": True}],
                "environment": "never-return-this",
            }))],
        )

        result = probe(runner)

        self.assertEqual(result["diagnosis"], "SAFE_MODE_OR_PIPELINE_UNAVAILABLE")
        self.assertTrue(result["pipelineDiagnostic"]["safeMode"])
        self.assertTrue(result["pipelineDiagnostic"]["compiling"])
        self.assertNotIn("never-return-this", json.dumps(result))

    def test_documented_pipeline_summary_safe_mode_shape_is_parsed(self):
        runner = QueueRunner(
            [
                completed([], stdout="1.0.0-beta.9"),
                completed([], stdout=json.dumps({"success": True, "instances": []})),
            ],
            pipeline_results=[completed([], stdout=json.dumps({
                "success": True,
                "data": {
                    "summary": {"instancesInSafeMode": 2},
                    "instances": [{
                        "projectPath": T008_PROJECT_PATH,
                        "pid": 5352,
                        "pipelineStatus": "connected",
                        "packageStatus": "ready",
                    }],
                },
            }))],
        )

        result = probe(runner)

        self.assertEqual(result["pipelineDiagnostic"]["candidateCount"], 1)
        self.assertEqual(result["pipelineDiagnostic"]["instancesInSafeMode"], 2)
        self.assertTrue(result["pipelineDiagnostic"]["safeMode"])
        self.assertEqual(result["pipelineDiagnostic"]["targetVisible"], True)
        self.assertEqual(result["pipelineDiagnostic"]["instances"], [{
            "projectPath": T008_PROJECT_PATH,
            "pid": 5352,
            "pipelineStatus": "connected",
            "packageStatus": "ready",
        }])

    def test_documented_per_instance_safe_mode_shape_is_parsed(self):
        runner = QueueRunner(
            [
                completed([], stdout="1.0.0-beta.9"),
                completed([], stdout=json.dumps({"success": True, "instances": []})),
            ],
            pipeline_results=[completed([], stdout=json.dumps({
                "success": True,
                "data": {
                    "summary": {"instancesInSafeMode": 0},
                    "instances": [{
                        "project": T008_PROJECT_PATH,
                        "safeMode": {"detected": True},
                    }],
                },
            }))],
        )

        result = probe(runner)

        self.assertTrue(result["pipelineDiagnostic"]["safeMode"])
        self.assertEqual(result["pipelineDiagnostic"]["instances"], [{
            "projectPath": T008_PROJECT_PATH,
            "safeModeDetected": True,
        }])

    def test_list_catalog_handshake_connects_when_status_is_empty_without_exposing_catalog(self):
        runner = QueueRunner(
            [
                completed([], stdout="1.0.0-beta.9"),
                completed([], stdout=json.dumps({"success": True, "instances": []})),
            ],
            handshake_results=[completed([], stdout=json.dumps({
                "success": True,
                "data": {
                    "projectPath": T008_PROJECT_PATH,
                    "tools": [{
                        "name": "secret-command-name",
                        "description": "secret tool description",
                        "inputSchema": {"type": "object", "properties": {"secret": {"type": "string"}}},
                        "accessToken": "secret-catalog-token",
                    }],
                },
            }))],
        )

        result = probe(runner)

        self.assertEqual(result["verdict"], "NO_INSTANCE")
        self.assertEqual(result["pipelineHandshake"], {
            "state": "CONNECTED",
            "exitCode": 0,
            "success": True,
            "catalogValid": True,
            "toolCount": 1,
            "projectPath": T008_PROJECT_PATH,
            "errorCodes": [],
        })
        self.assertEqual(result["diagnosis"], "HOST_PIPELINE_CONNECTED")
        serialized = json.dumps(result)
        for secret in ("secret-command-name", "secret tool description", "inputSchema", "secret-catalog-token"):
            self.assertNotIn(secret, serialized)

    def test_list_failure_with_safe_mode_is_classified_as_safe_mode(self):
        runner = QueueRunner(
            [
                completed([], stdout="1.0.0-beta.9"),
                completed([], stdout=json.dumps({"success": True, "instances": []})),
            ],
            pipeline_results=[completed([], stdout=json.dumps({
                "success": True,
                "data": {
                    "summary": {"instancesInSafeMode": 1},
                    "instances": [{"safeMode": {"detected": True}}],
                },
            }))],
            handshake_results=[completed([], code=5, stdout=json.dumps({
                "success": False,
                "errors": [{"code": "PIPELINE_SAFE_MODE", "message": "never returned"}],
            }))],
        )

        result = probe(runner)

        self.assertEqual(result["pipelineHandshake"]["state"], "SAFE_MODE")
        self.assertEqual(result["pipelineHandshake"]["errorCodes"], ["PIPELINE_SAFE_MODE"])
        self.assertEqual(result["diagnosis"], "SAFE_MODE_OR_PIPELINE_UNAVAILABLE")
        self.assertNotIn("never returned", json.dumps(result))

    def test_list_failure_with_visible_target_and_editor_is_handshake_failure(self):
        runner = QueueRunner(
            [
                completed([], stdout="1.0.0-beta.9"),
                completed([], stdout=json.dumps({"success": True, "instances": []})),
            ],
            pipeline_results=[completed([], stdout=json.dumps({
                "success": True,
                "data": {"instances": [{"projectPath": T008_PROJECT_PATH, "pid": 5352, "state": "ready"}]},
            }))],
            handshake_results=[completed([], code=7, stdout=json.dumps({
                "success": False,
                "errors": [{"code": "PIPELINE_UNAVAILABLE"}],
            }))],
        )

        result = probe(
            runner,
            process_observer=lambda: {"present": True, "pids": [5352], "complete": True},
        )

        self.assertEqual(result["pipelineHandshake"]["state"], "NOT_CONNECTED")
        self.assertEqual(result["diagnosis"], "PIPELINE_VISIBLE_HANDSHAKE_FAILED")

    def test_direct_match_verdict_remains_while_failed_pipeline_handshake_is_diagnosed(self):
        runner = QueueRunner(
            [
                completed([], stdout="1.0.0-beta.9"),
                completed([], stdout=json.dumps({"success": True, "instances": [{
                    "state": "ready",
                    "projectPath": T008_PROJECT_PATH,
                    "editorVersion": T008_EDITOR_VERSION,
                    "pid": 5352,
                }]})),
            ],
            pipeline_results=[completed([], stdout=json.dumps({
                "success": True,
                "data": {"instances": [{"projectPath": T008_PROJECT_PATH, "pid": 5352}]},
            }))],
        )

        result = probe(
            runner,
            process_observer=lambda: {"present": True, "pids": [5352], "complete": True},
        )

        self.assertEqual(result["verdict"], "DIRECT_MATCH")
        self.assertEqual(result["pipelineHandshake"]["state"], "NOT_CONNECTED")
        self.assertEqual(result["diagnosis"], "PIPELINE_VISIBLE_HANDSHAKE_FAILED")

    def test_list_timeout_is_bounded_and_does_not_return_cli_payload(self):
        runner = QueueRunner(
            [
                completed([], stdout="1.0.0-beta.9"),
                completed([], stdout=json.dumps({"success": True, "instances": []})),
            ],
            handshake_results=[subprocess.TimeoutExpired("unity list", 8)],
        )

        result = probe(runner)

        self.assertEqual(result["pipelineHandshake"]["state"], "UNRESOLVED")
        self.assertEqual(result["pipelineHandshake"]["error"], "UNITY_LIST_TIMEOUT")
        self.assertEqual(result["diagnosis"], "EDITOR_PROCESS_ABSENT")
        self.assertNotIn("TimeoutExpired", json.dumps(result))

    def test_process_observation_allowlists_pids_and_never_returns_command_lines(self):
        runner = QueueRunner([
            completed([], stdout="1.0.0-beta.9"),
            completed([], stdout=json.dumps({"success": True, "instances": []})),
        ])

        result = probe(
            runner,
            process_observer=lambda: {
                "present": True,
                "pids": list(range(1, 20)),
                "complete": True,
                "commandLine": "--project C:\\Private --token process-secret",
                "environment": {"CONTROL_PLANE_API_KEY": "environment-secret"},
            },
        )

        self.assertEqual(result["editorProcessIds"], list(range(1, 9)))
        self.assertNotIn("commandLine", json.dumps(result))
        self.assertNotIn("Private", json.dumps(result))
        self.assertNotIn("process-secret", json.dumps(result))
        self.assertNotIn("environment-secret", json.dumps(result))

    def test_pipeline_timeout_is_bounded_and_status_probe_still_runs(self):
        runner = QueueRunner(
            [
                completed([], stdout="1.0.0-beta.9"),
                completed([], stdout=json.dumps({"success": True, "instances": []})),
            ],
            pipeline_results=[subprocess.TimeoutExpired("unity pipeline list", 8)],
        )

        result = probe(runner)

        self.assertEqual(result["diagnosis"], "DIAGNOSTIC_UNRESOLVED")
        self.assertEqual(result["pipelineDiagnostic"]["error"], "UNITY_PIPELINE_TIMEOUT")
        self.assertEqual(len(runner.calls), 4)
        self.assertEqual(runner.calls[3][0][1], "status")
        self.assertTrue(all(call[1]["timeout"] == 8 for call in runner.calls))
        self.assertTrue(all(call[1]["shell"] is False for call in runner.calls))

    def test_pipeline_failure_does_not_return_raw_output_or_stderr(self):
        runner = QueueRunner(
            [
                completed([], stdout="1.0.0-beta.9"),
                completed([], stdout=json.dumps({"success": True, "instances": []})),
            ],
            pipeline_results=[completed(
                [],
                code=4,
                stdout='{"apiKey":"pipeline-secret"}',
                stderr="pipeline-stderr-secret",
            )],
        )

        result = probe(runner)

        self.assertEqual(result["pipelineDiagnostic"]["error"], "UNITY_PIPELINE_FAILED")
        serialized = json.dumps(result)
        self.assertNotIn("pipeline-secret", serialized)
        self.assertNotIn("pipeline-stderr-secret", serialized)
        self.assertNotIn("stderr", result)

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
