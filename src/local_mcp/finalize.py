"""Persist a completed Worker task and return its Result to the caller."""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any

from .dispatch import AppServerUnavailable, DispatchLedger, _get_default_client, _text
from .worker_pool import (
    WorkerPool,
    WorkerPoolConfig,
    WorkerPoolError,
    _identity_matches,
    _status,
    default_state_path,
)


_SECRET_PATH_PARTS = {".codex", "worker-state", "runtime", "workers", "workspaces", "clones"}
_SECRET_TEXT = re.compile(
    r"(?i)(?:CONTROL_PLANE_API_KEY|GITHUB_TOKEN|GH_TOKEN|CODEX_API_KEY|OPENAI_API_KEY)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"
    r"|\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})\b"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)


class _GitFailure(RuntimeError):
    def __init__(self, operation: str):
        super().__init__(operation)
        self.operation = operation


def _git(repository: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *args], check=True, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=120,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # Git diagnostics can contain remote URLs or credential-helper details.
        raise _GitFailure(args[0] if args else "git") from exc
    return result.stdout.strip()


def _commit(repository: Path, work_identity: str, task_key: str) -> None:
    try:
        name = _git(repository, "config", "--get", "user.name")
    except _GitFailure:
        name = os.environ.get("GIT_AUTHOR_NAME") or "Local Operations"
    try:
        email = _git(repository, "config", "--get", "user.email")
    except _GitFailure:
        email = os.environ.get("GIT_AUTHOR_EMAIL") or "local-operations@users.noreply.github.com"
    _git(
        repository, "-c", f"user.name={name}", "-c", f"user.email={email}",
        "commit", "-m", f"Local Operations: {work_identity}/{task_key}",
    )


def _turn_final_message(turn: dict[str, Any]) -> str | None:
    messages: list[str] = []
    items = turn.get("items")
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        root = item.get("root") if isinstance(item.get("root"), dict) else item
        if root.get("type") != "agentMessage":
            continue
        text = root.get("text")
        if isinstance(text, str):
            messages.append(text)
        elif isinstance(root.get("content"), list):
            chunks = [part.get("text") for part in root["content"] if isinstance(part, dict) and isinstance(part.get("text"), str)]
            if chunks:
                messages.append("".join(chunks))
    return messages[-1] if messages else None


def _secret_paths(paths: list[str]) -> list[str]:
    blocked: list[str] = []
    for path in paths:
        value = PurePosixPath(path)
        name = value.name.casefold()
        parts = {part.casefold() for part in value.parts}
        if (
            any(part in _SECRET_PATH_PARTS for part in parts)
            or (name.startswith(".env") and name != ".env.example")
            or value.suffix.casefold() in {".pem", ".key", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db"}
        ):
            blocked.append(path)
    return blocked


def _changed_paths(repository: Path, *, committed: bool = False) -> list[str]:
    if committed:
        output = _git(repository, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD", "-z")
    else:
        output = _git(repository, "diff", "--cached", "--name-only", "-z")
    return [path for path in output.split("\x00") if path]


def _task_commit(repository: Path, work_identity: str, task_key: str) -> str | None:
    subject = _git(repository, "log", "-1", "--format=%s")
    if subject != f"Local Operations: {work_identity}/{task_key}":
        return None
    return _git(repository, "rev-parse", "HEAD")


def _base_result(
    *, work_identity: str, task_key: str, worker_id: str,
    turn_status: str | None = None, final_message: str | None = None,
) -> dict[str, Any]:
    return {
        "status": "HOLD",
        "workIdentity": work_identity,
        "taskKey": task_key,
        "workerId": worker_id,
        "codexTurnStatus": turn_status,
        "finalAgentMessage": final_message,
        "changedPaths": [],
        "changedPathCount": 0,
        "resultLocators": [],
        "commitSha": None,
        "pushStatus": "NOT_ATTEMPTED",
        "error": None,
        "recoveryHint": None,
    }


def finalize_task(
    params: dict[str, Any],
    *,
    client_factory: Any | None = None,
    config_path: Path | None = None,
    worker_root: Path | None = None,
    state_path: Path | None = None,
) -> dict[str, Any]:
    """Commit/push one completed Codex task and release its clean Worker."""
    try:
        worker_id = _text(params.get("worker_id"), "worker_id")
        work_identity = _text(params.get("work_identity"), "work_identity")
        task_key = _text(params.get("task_key"), "task_key")
        assert worker_id and work_identity and task_key
        config = WorkerPoolConfig.load(config_path=config_path, worker_root=worker_root)
        pool = WorkerPool(config, state_path=state_path or default_state_path())
        ledger = DispatchLedger(state_path or default_state_path())
    except (WorkerPoolError, ValueError, OSError) as exc:
        return _base_result(work_identity=str(params.get("work_identity", "")), task_key=str(params.get("task_key", "")), worker_id=str(params.get("worker_id", ""))) | {
            "reason": getattr(exc, "reason", "INPUT_VALIDATION_ERROR"), "error": str(exc),
        }

    saved = ledger.finalized_result(work_identity, task_key)
    if saved:
        if saved.get("workerId") != worker_id:
            return _base_result(work_identity=work_identity, task_key=task_key, worker_id=worker_id) | {
                "reason": "WORKER_TASK_MISMATCH", "error": "This task was finalized by a different Worker.",
            }
        lease = pool.get_lease(worker_id, work_identity, task_key)
        if lease:
            try:
                released = pool.release_task(worker_id, work_identity, task_key)
            except WorkerPoolError as exc:
                return saved | {
                    "status": "HOLD", "workerState": "LEASED", "reason": exc.reason, "error": str(exc),
                    "recoveryHint": "Resolve the remaining local changes in this Worker, then call finalize_codex_task again.",
                }
            return saved | {"status": "FINALIZED", "workerState": released["state"]}
        current_state = next((row["state"] for row in pool.status() if row["worker_id"] == worker_id), "UNKNOWN")
        return saved | {"status": "ALREADY_FINALIZED", "workerState": current_state}

    result = _base_result(work_identity=work_identity, task_key=task_key, worker_id=worker_id)
    try:
        lease = pool.get_lease(worker_id, work_identity, task_key)
        if not lease:
            raise WorkerPoolError("WORKER_LEASE_NOT_FOUND", "No matching active Worker lease exists.", worker_id=worker_id)
        dispatch = ledger.find(work_identity, task_key)
        if not dispatch or dispatch.get("state") != "ACCEPTED" or not dispatch.get("thread_id") or not dispatch.get("turn_id"):
            raise WorkerPoolError("CODEX_DISPATCH_UNVERIFIED", "The Worker has no acknowledged Codex turn to finalize.", worker_id=worker_id)
        if dispatch.get("worker_id") != worker_id or dispatch.get("branch") != lease.get("branch"):
            raise WorkerPoolError("WORKER_TASK_MISMATCH", "The active Worker lease does not match this dispatch.", worker_id=worker_id)

        client = (client_factory or _get_default_client)()
        client.ensure_ready()
        read_result = client.request("thread/read", {"threadId": dispatch["thread_id"], "includeTurns": True})
        thread = read_result.get("thread")
        turns = thread.get("turns") if isinstance(thread, dict) else None
        if not isinstance(turns, list):
            raise WorkerPoolError("CODEX_TURN_STATE_UNAVAILABLE", "Codex did not return the task's turn history.", worker_id=worker_id)
        turn = next((item for item in turns if isinstance(item, dict) and item.get("id") == dispatch["turn_id"]), None)
        if not turn or turn.get("status") != "completed":
            raise WorkerPoolError("CODEX_TURN_NOT_COMPLETE", "The Codex turn has not completed.", worker_id=worker_id)
        final_message = _turn_final_message(turn)
        result["codexTurnStatus"] = turn.get("status")
        result["finalAgentMessage"] = final_message

        repository_identity = lease["repository_identity"]
        repository = config.repository(repository_identity)
        root = config.repository_path(worker_id, repository)
        if Path(dispatch["resolved_repository_root"]).resolve() != root.resolve():
            raise WorkerPoolError("WRONG_REPOSITORY", "The dispatch repository does not match the leased Worker clone.", worker_id=worker_id)
        if not root.is_dir() or not _identity_matches(root, repository_identity):
            raise WorkerPoolError("WRONG_REPOSITORY", "The leased Worker clone is missing or has a different Git remote.", worker_id=worker_id)
        branch = lease["branch"]
        if _git(root, "branch", "--show-current") != branch:
            raise WorkerPoolError("WORKER_BRANCH_MISMATCH", "The leased Worker is no longer on the requested branch.", worker_id=worker_id)

        if _status(root):
            _git(root, "add", "-A")
            paths = _changed_paths(root)
            if paths:
                blocked_paths = _secret_paths(paths)
                staged_diff = _git(root, "diff", "--cached", "--unified=0", "--", ".")
                if blocked_paths or _SECRET_TEXT.search(staged_diff):
                    result.update(
                        reason="SECRET_CONTENT_NOT_COMMITTED",
                        error="Staged changes include a credential-like value or a local secret/runtime file.",
                        changedPaths=paths,
                        changedPathCount=len(paths),
                        recoveryHint="Remove the secret from the staged changes without deleting needed work, then call finalize_codex_task again.",
                    )
                    return result
                _commit(root, work_identity, task_key)
                commit_sha = _git(root, "rev-parse", "HEAD")
            else:
                commit_sha = _task_commit(root, work_identity, task_key)
        else:
            commit_sha = _task_commit(root, work_identity, task_key)
            paths = _changed_paths(root, committed=True) if commit_sha else []

        if commit_sha:
            result["commitSha"] = commit_sha
            if not paths:
                paths = _changed_paths(root, committed=True)
            result["changedPaths"] = paths
            result["changedPathCount"] = len(paths)
            result["resultLocators"] = [
                path for path in paths
                if "result" in PurePosixPath(path).name.casefold()
            ]
            try:
                _git(root, "push", "origin", branch)
                result["pushStatus"] = "PUSHED"
            except _GitFailure as exc:
                result.update(
                    status="HOLD", reason="GIT_PUSH_FAILED", pushStatus="FAILED",
                    error="Git rejected or could not complete the non-force push; the local commit is preserved.",
                    recoveryHint="Inspect the remote and local branch, resolve any conflict manually, then call finalize_codex_task again. No force push, reset, or rebase was attempted.",
                )
                return result
        else:
            result["pushStatus"] = "NOT_NEEDED"

        result["status"] = "FINALIZED"
        result["workerState"] = "FREE"
        ledger.save_finalization(work_identity, task_key, result)
        released = pool.release_task(worker_id, work_identity, task_key)
        result["workerState"] = released["state"]
        return result
    except AppServerUnavailable:
        result.update(reason="CODEX_UNAVAILABLE", error="Codex app-server could not be read; the Worker remains leased.")
        return result
    except WorkerPoolError as exc:
        result.update(status="HOLD", workerState="LEASED", reason=exc.reason, error=str(exc), recoveryHint="Resolve the reported local issue and call finalize_codex_task again.")
        return result
    except _GitFailure as exc:
        result.update(
            reason="GIT_OPERATION_FAILED", error=f"Git {exc.operation} failed; local work is preserved.",
            recoveryHint="Inspect the Worker branch and Git configuration, then call finalize_codex_task again.",
        )
        return result
    except Exception as exc:
        result.update(reason="FINALIZE_FAILED", error=f"Finalization stopped ({type(exc).__name__}); local work is preserved.")
        return result
