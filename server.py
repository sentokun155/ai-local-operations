from mcp.server import MCPServer
from local_mcp.dispatch import dispatch_task
from local_mcp.worker_pool import WorkerPool, WorkerPoolConfig, WorkerPoolError, default_state_path
from local_mcp.dispatch import AppServerUnavailable, _get_default_client

mcp = MCPServer("local-operations")


@mcp.tool()
def ping() -> str:
    """Return a simple health-check response."""
    return "LOCAL_MCP_OK"

@mcp.tool()
def ping2() -> str:
    """Return a simple health-check response2."""
    return "LOCAL_MCP_OK2"

@mcp.tool()
def dispatch_codex_task(
    work_identity: str,
    task_key: str,
    task_name: str,
    task_request_locator: str,
    repository: str,
    branch: str,
    repository_path: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, object]:
    """Start one Codex task from a tracked Task Request in a local Git repository.

    repository is the logical remote identity (for example owner/name or
    github.example/owner/name). Local Operations resolves it through its
    bounded repository registry and linked Git worktrees. repository_path is
    an explicit local root override. For backward compatibility, repository
    may still be an absolute local root; an absolute Task Request path with no
    repository also remains supported. The Task Request file is canonical and
    must match its committed Git object on the requested branch. Dispatch runs
    in the resolved repository with workspace-write sandboxing. Repeating the
    same work_identity and task_key never starts a second turn when the first
    outcome is accepted or uncertain. DISPATCHED confirms app-server
    acknowledgement; inspect the Codex thread for completion.
    """
    return dispatch_task(
        {
            "work_identity": work_identity,
            "task_key": task_key,
            "task_name": task_name,
            "task_request_locator": task_request_locator,
            "repository": repository,
            "repository_path": repository_path,
            "branch": branch,
            "model": model,
            "reasoning_effort": reasoning_effort,
        }
    )


@mcp.tool()
def get_worker_pool_status() -> dict[str, object]:
    """Return configured Worker Slot state without exposing credentials or repository contents."""
    try:
        pool = WorkerPool(WorkerPoolConfig.load(), state_path=default_state_path())
        configured = set(pool.config.worker_ids())
        rows = pool.status()
        by_id = {row["worker_id"]: row for row in rows}
        return {
            "status": "OK",
            "workers": [
                {
                    "workerId": worker_id,
                    "state": by_id[worker_id]["state"],
                    "workIdentity": by_id[worker_id].get("work_identity"),
                    "taskKey": by_id[worker_id].get("task_key"),
                    "repository": by_id[worker_id].get("repository_identity"),
                    "branch": by_id[worker_id].get("branch"),
                    "threadId": by_id[worker_id].get("thread_id"),
                    "failureReason": by_id[worker_id].get("failure_reason"),
                }
                for worker_id in sorted(configured)
            ],
        }
    except WorkerPoolError as exc:
        return {"status": "HOLD", "reason": exc.reason, "message": str(exc)}


@mcp.tool()
def release_codex_worker(
    worker_id: str,
    work_identity: str,
    task_key: str,
    confirm_completed: bool,
) -> dict[str, object]:
    """Release a completed Codex lease after app-server and repository safety checks."""
    if confirm_completed is not True:
        return {"status": "HOLD", "reason": "COMPLETION_NOT_CONFIRMED", "message": "Confirm the Codex task is complete before release."}
    try:
        pool = WorkerPool(WorkerPoolConfig.load(), state_path=default_state_path())
        lease = pool.get_lease(worker_id, work_identity, task_key)
        if not lease or not lease.get("thread_id"):
            raise WorkerPoolError("WORKER_COMPLETION_UNVERIFIED", "The active Worker lease has no acknowledged thread to verify.", worker_id=worker_id)
        saved_dispatch = pool.dispatch_state(work_identity, task_key)
        if not saved_dispatch or saved_dispatch.get("state") in {"THREAD_STARTING", "TURN_STARTING", "UNKNOWN"}:
            return {"status": "HOLD", "reason": "DISPATCH_OUTCOME_UNKNOWN", "workerId": worker_id, "taskKey": task_key}
        client = _get_default_client()
        client.ensure_ready()
        result = client.request("thread/read", {"threadId": lease["thread_id"], "includeTurns": True})
        thread = result.get("thread")
        turns = thread.get("turns") if isinstance(thread, dict) else None
        if not isinstance(turns, list):
            return {"status": "HOLD", "reason": "CODEX_TURN_STATE_UNAVAILABLE", "workerId": worker_id, "taskKey": task_key}
        if lease.get("turn_id"):
            completed = next((turn for turn in turns if isinstance(turn, dict) and turn.get("id") == lease["turn_id"]), None)
            if not completed or completed.get("status") != "completed":
                return {"status": "HOLD", "reason": "CODEX_TURN_NOT_COMPLETE", "workerId": worker_id, "taskKey": task_key}
        elif any(
            not isinstance(turn, dict) or turn.get("status") not in {"completed", "failed", "interrupted", "cancelled", "rejected"}
            for turn in turns
        ):
            return {"status": "HOLD", "reason": "CODEX_TURN_NOT_COMPLETE", "workerId": worker_id, "taskKey": task_key}
        return {"status": "RELEASED", **pool.release_completed(worker_id, work_identity, task_key)}
    except AppServerUnavailable:
        return {"status": "HOLD", "reason": "CODEX_UNAVAILABLE", "message": "Codex app-server completion could not be verified; the Worker remains leased."}
    except WorkerPoolError as exc:
        return {"status": "HOLD", "reason": exc.reason, "workerId": exc.worker_id, "message": str(exc)}
    except Exception as exc:
        return {"status": "HOLD", "reason": "CODEX_COMPLETION_UNVERIFIED", "message": f"Codex completion could not be verified ({type(exc).__name__}); the Worker remains leased."}


if __name__ == "__main__":
    mcp.run()
