from mcp.server import MCPServer
from local_mcp.dispatch import dispatch_task
from local_mcp.finalize import finalize_task, recover_worker
from local_mcp.production import prepare_runtime
from local_mcp.unity_probe import probe_unity_host_connectivity as _probe_unity_host_connectivity
from local_mcp.unity_project_open import open_leased_unity_project as _open_leased_unity_project
from local_mcp.worker_pool import WorkerPool, WorkerPoolConfig, WorkerPoolError, default_state_path

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
    """Start one Codex task from the current Task Request file in a local Git repository.

    repository is the logical remote identity (for example owner/name or
    github.example/owner/name). Local Operations resolves it through its
    bounded repository registry and linked Git worktrees. repository_path is
    an explicit local root override. For backward compatibility, repository
    may still be an absolute local root; an absolute Task Request path with no
    repository also remains supported. The Task Request file is canonical and
    is read from the requested branch's current worktree without a starting
    revision pin. Dispatch runs
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
def finalize_codex_task(worker_id: str, work_identity: str, task_key: str) -> dict[str, object]:
    """Read a completed Codex Result, persist its changes, and release its clean Worker."""
    return finalize_task({
        "worker_id": worker_id,
        "work_identity": work_identity,
        "task_key": task_key,
    })


@mcp.tool()
def recover_quarantined_worker(worker_id: str) -> dict[str, object]:
    """Preserve completed local work and return one quarantined Worker to service."""
    return recover_worker(worker_id)


@mcp.tool()
def prepare_production_runtime(branch: str) -> dict[str, object]:
    """Prepare the fixed Production checkout on the requested branch and verify readiness."""
    return prepare_runtime(branch)


@mcp.tool()
def probe_unity_host_connectivity() -> dict[str, object]:
    """Read-only probe for the Unity Editor visible to the Local Operations Host process."""
    return _probe_unity_host_connectivity()


@mcp.tool()
def open_leased_unity_project(worker_id: str, work_identity: str, task_key: str) -> dict[str, object]:
    """Open the Unity project resolved from one exact active Worker lease.

    Inputs identify the lease only. The Host resolves the managed repository
    path and project-declared Editor version, uses an installed Unity CLI
    version, and returns bounded identity/readiness fields. No arbitrary path
    or CLI arguments are accepted, and descriptor/token or raw CLI data is
    never returned.
    """
    return _open_leased_unity_project(worker_id, work_identity, task_key)


if __name__ == "__main__":
    mcp.run()
