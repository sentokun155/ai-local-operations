"""Bounded, read-only Unity Editor connectivity probe for the Host process."""

from __future__ import annotations

import getpass
import json
import ntpath
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Callable, Mapping


PREFERRED_UNITY_CLI = Path(r"C:\Users\sennn\AppData\Local\Unity\bin\unity.exe")
T008_PROJECT_PATH = r"C:\Users\sennn\2D_RPG_Project6_git"
T008_EDITOR_VERSION = "6000.3.9f1"
COMMAND_TIMEOUT_SECONDS = 8
MAX_RETURNED_INSTANCES = 32
MAX_INSTANCE_COUNT = 1_000_000
MAX_STATUS_OUTPUT_CHARS = 256 * 1024
MAX_PROCESS_EXIT_CODE = 2**31 - 1

_VERSION_PATTERN = re.compile(r"\b\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.-]+)?\b")


def _bounded_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or any(ord(character) < 32 for character in value):
        return None
    return value[:limit]


def _host_user(environment: Mapping[str, str]) -> str | None:
    username = _bounded_text(environment.get("USERNAME"), 128)
    domain = _bounded_text(environment.get("USERDOMAIN"), 128)
    if username:
        return f"{domain}\\{username}" if domain else username
    try:
        return _bounded_text(getpass.getuser(), 128)
    except (OSError, KeyError):
        return None


def _safe_environment_path(environment: Mapping[str, str], key: str) -> str | None:
    return _bounded_text(environment.get(key), 2048)


def _resolve_cli(
    environment: Mapping[str, str],
    *,
    preferred_path: Path,
    exists: Callable[[Path], bool],
    which: Callable[..., str | None],
) -> str | None:
    if exists(preferred_path):
        return str(preferred_path)
    return which("unity", path=environment.get("PATH"))


def _run(
    command: list[str],
    *,
    runner: Callable[..., Any],
) -> Any:
    return runner(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
        shell=False,
    )


def _extract_version(output: Any) -> str | None:
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="replace")
    if not isinstance(output, str):
        return None
    match = _VERSION_PATTERN.search(output[:4096])
    return match.group(0) if match else None


def _safe_instance(value: Mapping[str, Any]) -> dict[str, Any]:
    instance: dict[str, Any] = {
        "state": _bounded_text(value.get("state"), 64),
        "projectPath": _bounded_text(value.get("projectPath"), 2048),
        "editorVersion": _bounded_text(value.get("editorVersion"), 128),
        "pid": None,
    }
    pid = value.get("pid")
    if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
        instance["pid"] = pid
    port = value.get("pipelinePort")
    if isinstance(port, int) and not isinstance(port, bool) and 0 < port <= 65535:
        instance["pipelinePort"] = port
    return instance


def _matching_t008_instance(instances: list[dict[str, Any]]) -> dict[str, Any] | None:
    expected_path = ntpath.normcase(ntpath.normpath(T008_PROJECT_PATH))
    return next(
        (
            instance
            for instance in instances
            if isinstance(instance.get("state"), str)
            and instance["state"].casefold() == "ready"
            and isinstance(instance.get("projectPath"), str)
            and ntpath.normcase(ntpath.normpath(instance["projectPath"])) == expected_path
            and instance.get("editorVersion") == T008_EDITOR_VERSION
        ),
        None,
    )


def _is_t008_match(instances: list[dict[str, Any]]) -> bool:
    return _matching_t008_instance(instances) is not None


def _result(
    *,
    environment: Mapping[str, str],
    unity_cli_path: str | None,
    verdict: str,
    unity_cli_version: str | None = None,
    unity_status_exit_code: int | None = None,
    success: bool = False,
    instance_count: int = 0,
    instances: list[dict[str, Any]] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "OK" if verdict == "DIRECT_MATCH" else "HOLD",
        "hostUser": _host_user(environment),
        "userProfile": _safe_environment_path(environment, "USERPROFILE"),
        "localAppData": _safe_environment_path(environment, "LOCALAPPDATA"),
        "appData": _safe_environment_path(environment, "APPDATA"),
        "unityCliPath": _bounded_text(unity_cli_path, 2048),
        "unityCliVersion": unity_cli_version,
        "unityStatusExitCode": unity_status_exit_code,
        "success": success,
        "instanceCount": instance_count,
        "instances": instances or [],
        "verdict": verdict,
    }
    if reason:
        result["reason"] = reason
    return result


def _probe_unity_host_connectivity(
    *,
    environment: Mapping[str, str],
    runner: Callable[..., Any],
    preferred_path: Path = PREFERRED_UNITY_CLI,
    exists: Callable[[Path], bool] | None = None,
    which: Callable[..., str | None] | None = None,
) -> dict[str, Any]:
    exists = exists or (lambda path: path.is_file())
    which = which or shutil.which
    unity_cli_path = _resolve_cli(
        environment,
        preferred_path=preferred_path,
        exists=exists,
        which=which,
    )
    if not unity_cli_path:
        return _result(
            environment=environment,
            unity_cli_path=None,
            verdict="CLI_UNAVAILABLE",
            reason="UNITY_CLI_NOT_FOUND",
        )

    try:
        version_result = _run([unity_cli_path, "--version"], runner=runner)
    except subprocess.TimeoutExpired:
        return _result(
            environment=environment,
            unity_cli_path=unity_cli_path,
            verdict="STATUS_FAILED",
            reason="UNITY_VERSION_TIMEOUT",
        )
    except OSError:
        return _result(
            environment=environment,
            unity_cli_path=unity_cli_path,
            verdict="CLI_UNAVAILABLE",
            reason="UNITY_CLI_LAUNCH_FAILED",
        )

    unity_cli_version = _extract_version(getattr(version_result, "stdout", None))
    if getattr(version_result, "returncode", 1) != 0 or not unity_cli_version:
        return _result(
            environment=environment,
            unity_cli_path=unity_cli_path,
            unity_cli_version=unity_cli_version,
            verdict="STATUS_FAILED",
            reason="UNITY_VERSION_FAILED",
        )

    try:
        status_result = _run(
            [
                unity_cli_path,
                "status",
                "--format",
                "json",
                "--no-banner",
                "--non-interactive",
            ],
            runner=runner,
        )
    except subprocess.TimeoutExpired:
        return _result(
            environment=environment,
            unity_cli_path=unity_cli_path,
            unity_cli_version=unity_cli_version,
            verdict="STATUS_FAILED",
            reason="UNITY_STATUS_TIMEOUT",
        )
    except OSError:
        return _result(
            environment=environment,
            unity_cli_path=unity_cli_path,
            unity_cli_version=unity_cli_version,
            verdict="CLI_UNAVAILABLE",
            reason="UNITY_CLI_LAUNCH_FAILED",
        )

    exit_code = getattr(status_result, "returncode", 1)
    exit_code = (
        exit_code
        if isinstance(exit_code, int)
        and not isinstance(exit_code, bool)
        and -MAX_PROCESS_EXIT_CODE <= exit_code <= MAX_PROCESS_EXIT_CODE
        else 1
    )
    if exit_code != 0:
        return _result(
            environment=environment,
            unity_cli_path=unity_cli_path,
            unity_cli_version=unity_cli_version,
            unity_status_exit_code=exit_code,
            verdict="STATUS_FAILED",
            reason="UNITY_STATUS_FAILED",
        )

    raw_output = getattr(status_result, "stdout", "")
    if isinstance(raw_output, bytes):
        raw_output = raw_output.decode("utf-8", errors="replace")
    if not isinstance(raw_output, str) or len(raw_output) > MAX_STATUS_OUTPUT_CHARS:
        raw_output = None
    try:
        payload = json.loads(raw_output) if isinstance(raw_output, str) else None
    except (json.JSONDecodeError, TypeError):
        payload = None
    if not isinstance(payload, dict) or not isinstance(payload.get("success"), bool):
        return _result(
            environment=environment,
            unity_cli_path=unity_cli_path,
            unity_cli_version=unity_cli_version,
            unity_status_exit_code=exit_code,
            verdict="STATUS_FAILED",
            reason="UNITY_STATUS_RESPONSE_INVALID",
        )

    raw_instances = payload.get("instances", [])
    if not isinstance(raw_instances, list):
        return _result(
            environment=environment,
            unity_cli_path=unity_cli_path,
            unity_cli_version=unity_cli_version,
            unity_status_exit_code=exit_code,
            success=payload["success"],
            verdict="STATUS_FAILED",
            reason="UNITY_STATUS_RESPONSE_INVALID",
        )

    instance_objects = [item for item in raw_instances if isinstance(item, dict)]
    parsed_instances = [_safe_instance(item) for item in instance_objects]
    matching_instance = _matching_t008_instance(parsed_instances)
    safe_instances = parsed_instances[:MAX_RETURNED_INSTANCES]
    if matching_instance is not None and not _is_t008_match(safe_instances):
        safe_instances[-1:] = [matching_instance]
    instance_count = min(len(instance_objects), MAX_INSTANCE_COUNT)

    if not payload["success"]:
        return _result(
            environment=environment,
            unity_cli_path=unity_cli_path,
            unity_cli_version=unity_cli_version,
            unity_status_exit_code=exit_code,
            success=False,
            instance_count=instance_count,
            instances=safe_instances,
            verdict="STATUS_FAILED",
            reason="UNITY_STATUS_REPORTED_FAILURE",
        )

    if matching_instance is not None:
        verdict = "DIRECT_MATCH"
        reason = None
    elif instance_count == 0:
        verdict = "NO_INSTANCE"
        reason = "NO_READY_INSTANCE"
    else:
        verdict = "IDENTITY_MISMATCH"
        reason = "NO_T008_PROJECT_EDITOR_MATCH"

    return _result(
        environment=environment,
        unity_cli_path=unity_cli_path,
        unity_cli_version=unity_cli_version,
        unity_status_exit_code=exit_code,
        success=True,
        instance_count=instance_count,
        instances=safe_instances,
        verdict=verdict,
        reason=reason,
    )


def probe_unity_host_connectivity() -> dict[str, Any]:
    """Read-only probe for the Unity Editor visible to this Host process."""
    return _probe_unity_host_connectivity(
        environment=os.environ,
        runner=subprocess.run,
    )
