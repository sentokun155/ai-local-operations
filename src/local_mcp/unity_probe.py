"""Bounded, read-only Unity Editor connectivity probe for the Host process."""

from __future__ import annotations

import ctypes
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
MAX_PIPELINE_OUTPUT_CHARS = 256 * 1024
MAX_RETURNED_EDITOR_PIDS = 8
MAX_PROCESSES_TO_SCAN = 4096
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


def _observe_unity_editor_processes() -> dict[str, Any]:
    """Use Tool Help to observe Unity.exe PIDs without reading command lines."""
    if os.name != "nt":
        return {"present": None, "pids": [], "complete": False}

    try:
        from ctypes import wintypes

        class ProcessEntry32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_snapshot = kernel32.CreateToolhelp32Snapshot
        create_snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        create_snapshot.restype = wintypes.HANDLE
        first_process = kernel32.Process32FirstW
        first_process.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
        first_process.restype = wintypes.BOOL
        next_process = kernel32.Process32NextW
        next_process.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
        next_process.restype = wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        snapshot = create_snapshot(0x00000002, 0)
        invalid_handle = ctypes.c_void_p(-1).value
        if not snapshot or getattr(snapshot, "value", snapshot) == invalid_handle:
            return {"present": None, "pids": [], "complete": False}

        pids: list[int] = []
        inspected = 0
        complete = False
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(ProcessEntry32W)
        try:
            found = bool(first_process(snapshot, ctypes.byref(entry)))
            if not found:
                complete = ctypes.get_last_error() == 18  # ERROR_NO_MORE_FILES
            while found and inspected < MAX_PROCESSES_TO_SCAN:
                inspected += 1
                if entry.szExeFile.casefold() == "unity.exe":
                    pid = int(entry.th32ProcessID)
                    if pid > 0 and len(pids) < MAX_RETURNED_EDITOR_PIDS:
                        pids.append(pid)
                entry.dwSize = ctypes.sizeof(ProcessEntry32W)
                found = bool(next_process(snapshot, ctypes.byref(entry)))
                if not found:
                    complete = ctypes.get_last_error() == 18  # ERROR_NO_MORE_FILES
            if found and inspected >= MAX_PROCESSES_TO_SCAN:
                complete = False
        finally:
            close_handle(snapshot)

        present = True if pids else (False if complete else None)
        return {"present": present, "pids": pids, "complete": complete}
    except Exception:
        return {"present": None, "pids": [], "complete": False}


def _safe_process_observation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"present": None, "pids": [], "complete": False}
    complete = value.get("complete") is True
    present = value.get("present")
    if not isinstance(present, bool):
        present = None
    pids: list[int] = []
    raw_pids = value.get("pids")
    if isinstance(raw_pids, (list, tuple)):
        for pid in raw_pids:
            if (
                isinstance(pid, int)
                and not isinstance(pid, bool)
                and 0 < pid <= 0xFFFFFFFF
                and pid not in pids
            ):
                pids.append(pid)
                if len(pids) >= MAX_RETURNED_EDITOR_PIDS:
                    break
    if pids:
        present = True
    elif present is False and not complete:
        present = None
    return {"present": present, "pids": pids, "complete": complete}


def _pipeline_rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        containers = [payload]
    elif isinstance(payload, dict):
        containers = [payload]
        for key in ("data", "result"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                containers.append(nested)
            elif isinstance(nested, list):
                containers.append({"pipelines": nested})
    else:
        return []

    rows: list[Mapping[str, Any]] = []
    collection_keys = ("pipelines", "pipelineCandidates", "candidates", "connections", "instances", "editors")
    for container in containers:
        if isinstance(container, list):
            candidates = container
        else:
            candidates = []
            for key in collection_keys:
                collection = container.get(key)
                if isinstance(collection, list):
                    candidates.extend(collection[:MAX_RETURNED_INSTANCES])
                elif isinstance(collection, dict):
                    candidates.append(collection)
        rows.extend(item for item in candidates[:MAX_RETURNED_INSTANCES] if isinstance(item, Mapping))
        if len(rows) >= MAX_RETURNED_INSTANCES:
            break
    return rows[:MAX_RETURNED_INSTANCES]


def _safe_pipeline_diagnostic(
    output: Any,
    *,
    command_succeeded: bool,
    error: str | None = None,
) -> dict[str, Any]:
    diagnostic: dict[str, Any] = {
        "available": False,
        "candidateCount": 0,
        "safeMode": None,
        "compiling": None,
        "pipelineUnavailable": None,
    }
    if error:
        diagnostic["error"] = error
        return diagnostic
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="replace")
    if not isinstance(output, str) or len(output) > MAX_PIPELINE_OUTPUT_CHARS:
        diagnostic["error"] = "UNITY_PIPELINE_RESPONSE_INVALID"
        return diagnostic
    try:
        payload = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        diagnostic["error"] = "UNITY_PIPELINE_RESPONSE_INVALID"
        return diagnostic
    rows = _pipeline_rows(payload)
    diagnostic["candidateCount"] = min(len(rows), MAX_INSTANCE_COUNT)
    diagnostic["available"] = command_succeeded and (
        not isinstance(payload, dict)
        or "success" not in payload
        or payload.get("success") is True
    )

    diagnostic_rows = list(rows)
    if isinstance(payload, dict):
        diagnostic_rows.append(payload)
        for key in ("data", "result"):
            nested = payload.get(key)
            if isinstance(nested, Mapping):
                diagnostic_rows.append(nested)

    safe_mode_values: list[bool] = []
    compiling_values: list[bool] = []
    unavailable_values: list[bool] = []
    for row in diagnostic_rows:
        for key in ("safeMode", "isSafeMode"):
            value = row.get(key)
            if isinstance(value, bool):
                safe_mode_values.append(value)
        for key in ("compiling", "isCompiling"):
            value = row.get(key)
            if isinstance(value, bool):
                compiling_values.append(value)
        for key in ("pipelineAvailable", "pipelineReady", "connected", "ready"):
            value = row.get(key)
            if isinstance(value, bool):
                unavailable_values.append(not value)
        for key in ("state", "status", "mode"):
            value = row.get(key)
            if not isinstance(value, str):
                continue
            normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
            if normalized in {"safe_mode", "safemode"}:
                safe_mode_values.append(True)
            elif normalized in {"compiling", "compile_error", "compilation_error", "compilation_failed"}:
                compiling_values.append(True)
            elif normalized in {"unavailable", "not_ready", "disconnected"}:
                unavailable_values.append(True)

    diagnostic["safeMode"] = True if True in safe_mode_values else (False if safe_mode_values else None)
    diagnostic["compiling"] = True if True in compiling_values else (False if compiling_values else None)
    diagnostic["pipelineUnavailable"] = (
        True if True in unavailable_values else (False if unavailable_values else None)
    )
    if not command_succeeded:
        diagnostic["available"] = False
        diagnostic["error"] = "UNITY_PIPELINE_FAILED"
    return diagnostic


def _diagnosis(
    process_observation: Mapping[str, Any],
    pipeline_diagnostic: Mapping[str, Any],
    *,
    status_success: bool = False,
    instance_count: int = 0,
    direct_match: bool = False,
) -> str:
    if direct_match:
        return "DIRECT_MATCH"
    if any(
        pipeline_diagnostic.get(key) is True
        for key in ("safeMode", "compiling", "pipelineUnavailable")
    ):
        return "SAFE_MODE_OR_PIPELINE_UNAVAILABLE"
    if not pipeline_diagnostic.get("available"):
        return "DIAGNOSTIC_UNRESOLVED"
    candidate_count = pipeline_diagnostic.get("candidateCount", 0)
    if status_success and instance_count == 0 and isinstance(candidate_count, int) and candidate_count > 0:
        return "PIPELINE_VISIBLE_STATUS_EMPTY"
    if isinstance(candidate_count, int) and candidate_count == 0:
        if process_observation.get("present") is False:
            return "EDITOR_PROCESS_ABSENT"
        if process_observation.get("present") is True:
            return "EDITOR_PRESENT_PIPELINE_NOT_VISIBLE"
    return "DIAGNOSTIC_UNRESOLVED"


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
    diagnosis: str = "DIAGNOSTIC_UNRESOLVED",
    process_observation: Mapping[str, Any] | None = None,
    pipeline_diagnostic: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    process_observation = process_observation or {"present": None, "pids": [], "complete": False}
    pipeline_diagnostic = pipeline_diagnostic or {
        "available": False,
        "candidateCount": 0,
        "safeMode": None,
        "compiling": None,
        "pipelineUnavailable": None,
    }
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
        "diagnosis": diagnosis,
        "editorProcessPresent": process_observation.get("present"),
        "editorProcessIds": process_observation.get("pids", []),
        "pipelineDiagnostic": dict(pipeline_diagnostic),
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
    process_observer: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    exists = exists or (lambda path: path.is_file())
    which = which or shutil.which
    process_observer = process_observer or _observe_unity_editor_processes
    try:
        process_observation = _safe_process_observation(process_observer())
    except Exception:
        process_observation = _safe_process_observation(None)
    pipeline_diagnostic = {
        "available": False,
        "candidateCount": 0,
        "safeMode": None,
        "compiling": None,
        "pipelineUnavailable": None,
    }
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
            process_observation=process_observation,
            pipeline_diagnostic=pipeline_diagnostic,
        )

    try:
        version_result = _run([unity_cli_path, "--version"], runner=runner)
    except subprocess.TimeoutExpired:
        return _result(
            environment=environment,
            unity_cli_path=unity_cli_path,
            verdict="STATUS_FAILED",
            reason="UNITY_VERSION_TIMEOUT",
            process_observation=process_observation,
            pipeline_diagnostic=pipeline_diagnostic,
        )
    except OSError:
        return _result(
            environment=environment,
            unity_cli_path=unity_cli_path,
            verdict="CLI_UNAVAILABLE",
            reason="UNITY_CLI_LAUNCH_FAILED",
            process_observation=process_observation,
            pipeline_diagnostic=pipeline_diagnostic,
        )

    unity_cli_version = _extract_version(getattr(version_result, "stdout", None))
    if getattr(version_result, "returncode", 1) != 0 or not unity_cli_version:
        return _result(
            environment=environment,
            unity_cli_path=unity_cli_path,
            unity_cli_version=unity_cli_version,
            verdict="STATUS_FAILED",
            reason="UNITY_VERSION_FAILED",
            process_observation=process_observation,
            pipeline_diagnostic=pipeline_diagnostic,
        )

    pipeline_error = None
    pipeline_result = None
    try:
        pipeline_result = _run(
            [
                unity_cli_path,
                "pipeline",
                "list",
                "--format",
                "json",
                "--no-banner",
                "--non-interactive",
            ],
            runner=runner,
        )
    except subprocess.TimeoutExpired:
        pipeline_error = "UNITY_PIPELINE_TIMEOUT"
    except OSError:
        pipeline_error = "UNITY_CLI_LAUNCH_FAILED"
    if pipeline_result is not None:
        pipeline_exit_code = getattr(pipeline_result, "returncode", 1)
        pipeline_succeeded = isinstance(pipeline_exit_code, int) and not isinstance(pipeline_exit_code, bool) and pipeline_exit_code == 0
        pipeline_diagnostic = _safe_pipeline_diagnostic(
            getattr(pipeline_result, "stdout", ""),
            command_succeeded=pipeline_succeeded,
        )
    else:
        pipeline_diagnostic = _safe_pipeline_diagnostic(
            None,
            command_succeeded=False,
            error=pipeline_error or "UNITY_PIPELINE_FAILED",
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
            diagnosis=_diagnosis(process_observation, pipeline_diagnostic),
            process_observation=process_observation,
            pipeline_diagnostic=pipeline_diagnostic,
        )
    except OSError:
        return _result(
            environment=environment,
            unity_cli_path=unity_cli_path,
            unity_cli_version=unity_cli_version,
            verdict="CLI_UNAVAILABLE",
            reason="UNITY_CLI_LAUNCH_FAILED",
            diagnosis=_diagnosis(process_observation, pipeline_diagnostic),
            process_observation=process_observation,
            pipeline_diagnostic=pipeline_diagnostic,
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
            diagnosis=_diagnosis(process_observation, pipeline_diagnostic),
            process_observation=process_observation,
            pipeline_diagnostic=pipeline_diagnostic,
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
            diagnosis=_diagnosis(process_observation, pipeline_diagnostic),
            process_observation=process_observation,
            pipeline_diagnostic=pipeline_diagnostic,
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
            diagnosis=_diagnosis(process_observation, pipeline_diagnostic),
            process_observation=process_observation,
            pipeline_diagnostic=pipeline_diagnostic,
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
            diagnosis=_diagnosis(process_observation, pipeline_diagnostic),
            process_observation=process_observation,
            pipeline_diagnostic=pipeline_diagnostic,
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
        diagnosis=_diagnosis(
            process_observation,
            pipeline_diagnostic,
            status_success=True,
            instance_count=instance_count,
            direct_match=matching_instance is not None,
        ),
        process_observation=process_observation,
        pipeline_diagnostic=pipeline_diagnostic,
    )


def probe_unity_host_connectivity() -> dict[str, Any]:
    """Read-only probe for the Unity Editor visible to this Host process."""
    return _probe_unity_host_connectivity(
        environment=os.environ,
        runner=subprocess.run,
    )
