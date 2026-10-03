"""Open the Unity project bound to an active Worker Pool lease."""

from __future__ import annotations

import getpass
import json
import ntpath
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time
from typing import Any, Callable, Mapping

from .worker_pool import WorkerPool, WorkerPoolConfig, WorkerPoolError, default_state_path


COMMAND_TIMEOUT_SECONDS = 10
READINESS_TIMEOUT_SECONDS = 120
READINESS_POLL_INTERVAL_SECONDS = 2
MAX_CLI_OUTPUT_CHARS = 256 * 1024
MAX_VERSION_FILE_BYTES = 4096
MAX_RETURNED_TEXT = 2048

_UNITY_VERSION_PATTERN = re.compile(r"\d{4}\.\d+\.\d+[abfp]\d+(?:c\d+)?\Z")
_PROJECT_VERSION_LINE = re.compile(
    r"^m_EditorVersion:\s*(\d{4}\.\d+\.\d+[abfp]\d+(?:c\d+)?)\s*$",
    re.MULTILINE,
)


def _bounded_text(value: Any, limit: int = MAX_RETURNED_TEXT) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > limit or any(ord(char) < 32 for char in value):
        return None
    return value


def _host_user(environment: Mapping[str, str]) -> str | None:
    username = _bounded_text(environment.get("USERNAME"), 128)
    domain = _bounded_text(environment.get("USERDOMAIN"), 128)
    if username:
        return f"{domain}\\{username}" if domain else username
    try:
        return _bounded_text(getpass.getuser(), 128)
    except (OSError, KeyError):
        return None


def _resolve_unity_cli(
    environment: Mapping[str, str],
    *,
    exists: Callable[[Path], bool],
    which: Callable[..., str | None],
) -> str | None:
    local_app_data = environment.get("LOCALAPPDATA")
    if isinstance(local_app_data, str) and local_app_data:
        candidate = Path(local_app_data) / "Unity" / "bin" / "unity.exe"
        if candidate.is_absolute() and exists(candidate):
            return str(candidate)
    return which("unity", path=environment.get("PATH"))


def _child_environment(environment: Mapping[str, str]) -> dict[str, str]:
    child = dict(environment)
    # This credential belongs to the Local Operations control plane and is not
    # needed by Unity CLI.
    child.pop("CONTROL_PLANE_API_KEY", None)
    return child


def _run_cli(
    unity_cli: str,
    arguments: list[str],
    *,
    environment: Mapping[str, str],
    runner: Callable[..., Any],
) -> Any:
    return runner(
        [unity_cli, *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
        shell=False,
        env=_child_environment(environment),
    )


def _output_text(value: Any) -> str | None:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not isinstance(value, str) or len(value) > MAX_CLI_OUTPUT_CHARS:
        return None
    return value


def _json_payload(value: Any) -> Mapping[str, Any] | None:
    output = _output_text(value)
    if output is None:
        return None
    try:
        payload = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _installed_editor_versions(result: Any) -> set[str] | None:
    if getattr(result, "returncode", 1) != 0:
        return None
    payload = _json_payload(getattr(result, "stdout", None))
    if not payload or payload.get("success") is not True:
        return None
    rows = payload.get("data")
    if not isinstance(rows, list):
        return None
    versions: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        version = row.get("version")
        if isinstance(version, str) and _UNITY_VERSION_PATTERN.fullmatch(version):
            versions.add(version)
    return versions


def _project_editor_version(project_root: Path) -> tuple[str | None, str | None]:
    if not project_root.is_dir() or not (project_root / "Assets").is_dir():
        return None, "NOT_UNITY_PROJECT"
    settings = project_root / "ProjectSettings"
    version_file = settings / "ProjectVersion.txt"
    if not settings.is_dir() or not version_file.is_file():
        return None, "PROJECT_VERSION_UNAVAILABLE"
    try:
        with version_file.open("rb") as stream:
            raw = stream.read(MAX_VERSION_FILE_BYTES + 1)
        if len(raw) > MAX_VERSION_FILE_BYTES:
            return None, "PROJECT_VERSION_UNAVAILABLE"
        contents = raw.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None, "PROJECT_VERSION_UNAVAILABLE"
    versions = _PROJECT_VERSION_LINE.findall(contents)
    if len(versions) != 1 or not _UNITY_VERSION_PATTERN.fullmatch(versions[0]):
        return None, "PROJECT_VERSION_UNAVAILABLE"
    return versions[0], None


def _is_descendant(path: Path, parent: Path) -> bool:
    try:
        relative = path.relative_to(parent)
    except ValueError:
        return False
    return bool(relative.parts)


def _resolve_leased_project(
    pool: WorkerPool,
    worker_id: str,
    work_identity: str,
    task_key: str,
) -> tuple[Mapping[str, Any] | None, Any | None, Path | None, str | None]:
    try:
        lease = pool.get_lease(worker_id, work_identity, task_key)
        if not lease:
            return None, None, None, "WORKER_LEASE_NOT_FOUND"
        lease_repository = lease.get("repository_identity")
        if not isinstance(lease_repository, str) or not _bounded_text(lease_repository, 256):
            return lease, None, None, "MANAGED_REPOSITORY_INVALID"
        repo = pool.config.repository(lease_repository)
        if not _bounded_text(repo.identity, 256):
            return lease, None, None, "MANAGED_REPOSITORY_INVALID"
        configured_worker_root = pool.config.worker_root.resolve(strict=True)
        worker_slot_root = (configured_worker_root / worker_id).resolve(strict=True)
        if not _is_descendant(worker_slot_root, configured_worker_root):
            return lease, repo, None, "LEASED_PROJECT_PATH_INVALID"
        project_root = pool.config.repository_path(worker_id, repo).resolve(strict=True)
        if not _is_descendant(project_root, worker_slot_root):
            return lease, repo, None, "LEASED_PROJECT_PATH_INVALID"
        if not project_root.is_dir():
            return lease, repo, None, "LEASED_PROJECT_UNAVAILABLE"
        git_marker = project_root / ".git"
        if not (git_marker.is_dir() or git_marker.is_file()):
            return lease, repo, None, "LEASED_PROJECT_UNAVAILABLE"
        return lease, repo, project_root, None
    except WorkerPoolError as exc:
        return None, None, None, exc.reason
    except (AttributeError, OSError, RuntimeError, ValueError, sqlite3.Error):
        return None, None, None, "LEASED_PROJECT_UNAVAILABLE"


def _same_path(left: Any, right: str) -> bool:
    if not isinstance(left, str) or not left or len(left) > MAX_RETURNED_TEXT:
        return False
    if any(ord(char) < 32 for char in left):
        return False
    return ntpath.normcase(ntpath.normpath(left)) == ntpath.normcase(ntpath.normpath(right))


def _safe_status_instance(value: Mapping[str, Any]) -> dict[str, Any] | None:
    project_path = _bounded_text(value.get("projectPath", value.get("project")))
    state = _bounded_text(value.get("state"), 64)
    version = _bounded_text(value.get("editorVersion", value.get("version")), 64)
    if not project_path or not state:
        return None
    pid = value.get("pid")
    if isinstance(pid, str) and pid.isdigit():
        pid = int(pid)
    if not isinstance(pid, int) or isinstance(pid, bool) or not 1 <= pid <= 2**31 - 1:
        pid = None
    port = value.get("pipelinePort", value.get("port"))
    if isinstance(port, str) and port.isdigit():
        port = int(port)
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        port = None
    return {
        "projectPath": project_path,
        "state": state,
        "editorVersion": version,
        "pid": pid,
        "pipelinePort": port,
    }


def _status_rows(result: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
    output = _output_text(getattr(result, "stdout", None))
    if output is None:
        return None, "UNITY_STATUS_UNAVAILABLE"
    try:
        payload = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return None, "UNITY_STATUS_UNAVAILABLE"
    if not isinstance(payload, Mapping):
        return None, "UNITY_STATUS_UNAVAILABLE"
    data = payload.get("data", payload)
    rows = data.get("instances") if isinstance(data, Mapping) else None
    if payload.get("success") is False:
        errors = payload.get("errors")
        no_instances = isinstance(errors, list) and any(
            isinstance(error, Mapping) and error.get("code") == "STATUS_NO_INSTANCES"
            for error in errors
        )
        if no_instances:
            return [], None
        return None, "UNITY_STATUS_UNAVAILABLE"
    if getattr(result, "returncode", 1) != 0 or not isinstance(rows, list):
        return None, "UNITY_STATUS_UNAVAILABLE"
    safe_rows = [
        safe for row in rows if isinstance(row, Mapping)
        if (safe := _safe_status_instance(row)) is not None
    ]
    return safe_rows, None


def _query_project_status(
    unity_cli: str,
    project_path: str,
    *,
    environment: Mapping[str, str],
    runner: Callable[..., Any],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    try:
        result = _run_cli(
            unity_cli,
            [
                "status", "--project-path", project_path,
                "--format", "json", "--no-banner", "--non-interactive",
            ],
            environment=environment,
            runner=runner,
        )
    except subprocess.TimeoutExpired:
        return None, "UNITY_STATUS_TIMEOUT"
    except OSError:
        return None, "UNITY_STATUS_UNAVAILABLE"
    return _status_rows(result)


def _project_matches(rows: list[dict[str, Any]], project_path: str) -> list[dict[str, Any]]:
    return [row for row in rows if _same_path(row.get("projectPath"), project_path)]


def _is_ready_for_version(instance: Mapping[str, Any], declared_version: str) -> bool:
    return (
        isinstance(instance.get("state"), str)
        and instance["state"].casefold() == "ready"
        and instance.get("editorVersion") == declared_version
    )


def _result_base(
    *,
    status: str,
    verdict: str,
    reason: str | None,
    worker_id: str,
    repository_identity: str | None,
    project_path: str | None,
    declared_version: str | None,
    host_user: str | None,
    open_request_sent: bool = False,
    opened: bool | None = None,
    instance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    instance = instance or {}
    return {
        "status": status,
        "verdict": verdict,
        "reason": _bounded_text(reason, 128),
        "workerId": _bounded_text(worker_id, 64) or "",
        "repository": _bounded_text(repository_identity, 256),
        "projectPath": _bounded_text(project_path),
        "projectEditorVersion": _bounded_text(declared_version, 64),
        "hostUser": host_user,
        "editorState": instance.get("state"),
        "observedEditorVersion": instance.get("editorVersion"),
        "pid": instance.get("pid"),
        "pipelinePort": instance.get("pipelinePort"),
        "projectReadyUniquely": status == "OK",
        "openRequestSent": open_request_sent,
        "opened": opened,
    }


def _hold(
    reason: str,
    *,
    worker_id: str,
    repository_identity: str | None = None,
    project_path: str | None = None,
    declared_version: str | None = None,
    host_user: str | None = None,
    open_request_sent: bool = False,
    opened: bool | None = False,
    instance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _result_base(
        status="HOLD",
        verdict="HOLD",
        reason=reason,
        worker_id=worker_id,
        repository_identity=repository_identity,
        project_path=project_path,
        declared_version=declared_version,
        host_user=host_user,
        open_request_sent=open_request_sent,
        opened=opened,
        instance=instance,
    )


def _success(
    instance: Mapping[str, Any],
    *,
    already_ready: bool,
    worker_id: str,
    repository_identity: str,
    project_path: str,
    declared_version: str,
    host_user: str | None,
    open_request_sent: bool,
) -> dict[str, Any]:
    return _result_base(
        status="OK",
        verdict="ALREADY_READY" if already_ready else "OPENED_READY",
        reason=None,
        worker_id=worker_id,
        repository_identity=repository_identity,
        project_path=project_path,
        declared_version=declared_version,
        host_user=host_user,
        open_request_sent=open_request_sent,
        opened=not already_ready,
        instance=instance,
    )


def _lease_still_matches(
    pool: WorkerPool,
    worker_id: str,
    work_identity: str,
    task_key: str,
    repository_identity: str,
) -> bool:
    try:
        lease = pool.get_lease(worker_id, work_identity, task_key)
    except (WorkerPoolError, OSError, sqlite3.Error):
        return False
    return bool(lease and lease.get("repository_identity") == repository_identity)


def _wait_for_ready(
    unity_cli: str,
    project_path: str,
    declared_version: str,
    *,
    environment: Mapping[str, str],
    runner: Callable[..., Any],
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    timeout_seconds: float,
    allow_missing: bool,
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None]:
    deadline = clock() + max(0.0, timeout_seconds)
    last_instance: dict[str, Any] | None = None
    while True:
        rows, status_error = _query_project_status(
            unity_cli,
            project_path,
            environment=environment,
            runner=runner,
        )
        if status_error or rows is None:
            return None, status_error or "UNITY_STATUS_UNAVAILABLE", last_instance
        matches = _project_matches(rows, project_path)
        if len(matches) > 1:
            return None, "TARGET_PROJECT_AMBIGUOUS", None
        if matches:
            last_instance = matches[0]
            if _is_ready_for_version(last_instance, declared_version):
                return last_instance, None, None
            if (
                isinstance(last_instance.get("state"), str)
                and last_instance["state"].casefold() == "ready"
            ):
                return None, "UNITY_EDITOR_VERSION_MISMATCH", last_instance
        elif not allow_missing:
            return None, "TARGET_EDITOR_DISAPPEARED", last_instance

        remaining = deadline - clock()
        if remaining <= 0:
            return None, "UNITY_EDITOR_NOT_READY", last_instance
        sleep(min(READINESS_POLL_INTERVAL_SECONDS, remaining))


def open_leased_unity_project(
    worker_id: str,
    work_identity: str,
    task_key: str,
    *,
    worker_pool: WorkerPool | None = None,
    environment: Mapping[str, str] | None = None,
    runner: Callable[..., Any] | None = None,
    exists: Callable[[Path], bool] | None = None,
    which: Callable[..., str | None] | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    readiness_timeout_seconds: float = READINESS_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Open and re-identify the Unity project for one exact active Worker lease."""
    environment = environment if environment is not None else os.environ
    runner = runner or subprocess.run
    exists = exists or Path.is_file
    which = which or shutil.which
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    host_user = _host_user(environment)

    for value, limit in ((worker_id, 64), (work_identity, 128), (task_key, 128)):
        if not isinstance(value, str) or not value or len(value) > limit or any(ord(char) < 32 for char in value):
            return _hold("INVALID_LEASE_IDENTITY", worker_id=_bounded_text(worker_id, 64) or "", host_user=host_user)

    try:
        if worker_pool is None:
            worker_pool = WorkerPool(WorkerPoolConfig.load(), state_path=default_state_path())
    except WorkerPoolError as exc:
        return _hold(exc.reason, worker_id=worker_id, host_user=host_user)
    except (OSError, sqlite3.Error):
        return _hold("WORKER_POOL_UNAVAILABLE", worker_id=worker_id, host_user=host_user)

    lease, repository, project_root, lease_error = _resolve_leased_project(
        worker_pool, worker_id, work_identity, task_key
    )
    if lease_error:
        return _hold(lease_error, worker_id=worker_id, host_user=host_user)
    repository_identity = repository.identity
    project_path = str(project_root)
    if not _bounded_text(project_path):
        return _hold(
            "LEASED_PROJECT_PATH_INVALID", worker_id=worker_id,
            repository_identity=repository_identity, host_user=host_user,
        )

    declared_version, project_error = _project_editor_version(project_root)
    if project_error:
        return _hold(
            project_error, worker_id=worker_id, repository_identity=repository_identity,
            project_path=project_path, host_user=host_user,
        )

    unity_cli = _resolve_unity_cli(
        environment,
        exists=exists,
        which=which,
    )
    if not unity_cli:
        return _hold(
            "UNITY_OPEN_ROUTE_UNAVAILABLE", worker_id=worker_id,
            repository_identity=repository_identity, project_path=project_path,
            declared_version=declared_version, host_user=host_user,
        )

    try:
        installed_result = _run_cli(
            unity_cli,
            ["editors", "--installed", "--format", "json", "--no-banner", "--non-interactive"],
            environment=environment,
            runner=runner,
        )
    except (subprocess.TimeoutExpired, OSError):
        installed_versions = None
    else:
        installed_versions = _installed_editor_versions(installed_result)
    if installed_versions is None:
        return _hold(
            "UNITY_EDITOR_CATALOG_UNAVAILABLE", worker_id=worker_id,
            repository_identity=repository_identity, project_path=project_path,
            declared_version=declared_version, host_user=host_user,
        )
    if declared_version not in installed_versions:
        return _hold(
            "UNITY_EDITOR_UNAVAILABLE", worker_id=worker_id,
            repository_identity=repository_identity, project_path=project_path,
            declared_version=declared_version, host_user=host_user,
        )

    initial_rows, status_error = _query_project_status(
        unity_cli,
        project_path,
        environment=environment,
        runner=runner,
    )
    if status_error or initial_rows is None:
        return _hold(
            status_error or "UNITY_STATUS_UNAVAILABLE", worker_id=worker_id,
            repository_identity=repository_identity, project_path=project_path,
            declared_version=declared_version, host_user=host_user,
        )
    initial_matches = _project_matches(initial_rows, project_path)
    if len(initial_matches) > 1:
        return _hold(
            "TARGET_PROJECT_AMBIGUOUS", worker_id=worker_id,
            repository_identity=repository_identity, project_path=project_path,
            declared_version=declared_version, host_user=host_user,
        )

    if initial_matches:
        existing = initial_matches[0]
        if _is_ready_for_version(existing, declared_version):
            if not _lease_still_matches(
                worker_pool, worker_id, work_identity, task_key, repository.identity
            ):
                return _hold(
                    "WORKER_LEASE_NOT_FOUND", worker_id=worker_id,
                    repository_identity=repository_identity, project_path=project_path,
                    declared_version=declared_version, host_user=host_user,
                    instance=existing,
                )
            return _success(
                existing, already_ready=True, worker_id=worker_id,
                repository_identity=repository_identity, project_path=project_path,
                declared_version=declared_version, host_user=host_user,
                open_request_sent=False,
            )
        if isinstance(existing.get("state"), str) and existing["state"].casefold() == "ready":
            return _hold(
                "UNITY_EDITOR_VERSION_MISMATCH", worker_id=worker_id,
                repository_identity=repository_identity, project_path=project_path,
                declared_version=declared_version, host_user=host_user, instance=existing,
            )
        ready_instance, wait_error, last_instance = _wait_for_ready(
            unity_cli,
            project_path,
            declared_version,
            environment=environment,
            runner=runner,
            clock=clock,
            sleep=sleep,
            timeout_seconds=readiness_timeout_seconds,
            allow_missing=False,
        )
        if wait_error or not ready_instance:
            return _hold(
                wait_error or "UNITY_EDITOR_NOT_READY", worker_id=worker_id,
                repository_identity=repository_identity, project_path=project_path,
                declared_version=declared_version, host_user=host_user,
                instance=last_instance,
            )
        if not _lease_still_matches(
            worker_pool, worker_id, work_identity, task_key, repository.identity
        ):
            return _hold(
                "WORKER_LEASE_NOT_FOUND", worker_id=worker_id,
                repository_identity=repository_identity, project_path=project_path,
                declared_version=declared_version, host_user=host_user,
                instance=ready_instance,
            )
        return _success(
            ready_instance, already_ready=True, worker_id=worker_id,
            repository_identity=repository_identity, project_path=project_path,
            declared_version=declared_version, host_user=host_user,
            open_request_sent=False,
        )

    if not _lease_still_matches(
        worker_pool, worker_id, work_identity, task_key, repository.identity
    ):
        return _hold(
            "WORKER_LEASE_NOT_FOUND", worker_id=worker_id,
            repository_identity=repository_identity, project_path=project_path,
            declared_version=declared_version, host_user=host_user,
        )

    try:
        open_result = _run_cli(
            unity_cli,
            [
                "open", project_path, "--editor-version", declared_version,
                "--format", "json", "--no-banner", "--non-interactive",
            ],
            environment=environment,
            runner=runner,
        )
    except subprocess.TimeoutExpired:
        return _hold(
            "UNITY_OPEN_TIMEOUT", worker_id=worker_id,
            repository_identity=repository_identity, project_path=project_path,
            declared_version=declared_version, host_user=host_user,
            open_request_sent=True, opened=None,
        )
    except OSError:
        return _hold(
            "UNITY_OPEN_ROUTE_UNAVAILABLE", worker_id=worker_id,
            repository_identity=repository_identity, project_path=project_path,
            declared_version=declared_version, host_user=host_user,
            open_request_sent=True, opened=None,
        )
    if getattr(open_result, "returncode", 1) != 0:
        return _hold(
            "UNITY_OPEN_FAILED", worker_id=worker_id,
            repository_identity=repository_identity, project_path=project_path,
            declared_version=declared_version, host_user=host_user,
            open_request_sent=True, opened=None,
        )

    ready_instance, wait_error, last_instance = _wait_for_ready(
        unity_cli,
        project_path,
        declared_version,
        environment=environment,
        runner=runner,
        clock=clock,
        sleep=sleep,
        timeout_seconds=readiness_timeout_seconds,
        allow_missing=True,
    )
    if wait_error or not ready_instance:
        return _hold(
            wait_error or "UNITY_EDITOR_NOT_READY", worker_id=worker_id,
            repository_identity=repository_identity, project_path=project_path,
            declared_version=declared_version, host_user=host_user,
            open_request_sent=True, opened=None, instance=last_instance,
        )
    if not _lease_still_matches(
        worker_pool, worker_id, work_identity, task_key, repository.identity
    ):
        return _hold(
            "WORKER_LEASE_NOT_FOUND", worker_id=worker_id,
            repository_identity=repository_identity, project_path=project_path,
            declared_version=declared_version, host_user=host_user,
            open_request_sent=True, opened=None, instance=ready_instance,
        )
    return _success(
        ready_instance, already_ready=False, worker_id=worker_id,
        repository_identity=repository_identity, project_path=project_path,
        declared_version=declared_version, host_user=host_user,
        open_request_sent=True,
    )
