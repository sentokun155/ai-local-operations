"""Bounded local Worker Pool maintenance commands (not exposed over MCP)."""

from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

from .worker_pool import WorkerPool, WorkerPoolConfig, WorkerPoolError, default_state_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Operations Worker Pool maintenance")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("bootstrap", help="Clone only configured repositories into configured FREE Worker Slots")
    subparsers.add_parser("status", help="Show configured Worker Slot states")
    subparsers.add_parser("check-no-leases", help="Exit nonzero while any Worker Slot is leased")
    args = parser.parse_args()
    try:
        if args.command == "check-no-leases":
            state_path = default_state_path()
            active: list[str] = []
            if state_path.exists():
                with closing(sqlite3.connect(state_path)) as connection:
                    exists = connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workers'"
                    ).fetchone()
                    if exists:
                        active = [row[0] for row in connection.execute(
                            "SELECT worker_id FROM workers WHERE state='LEASED' ORDER BY worker_id"
                        )]
            if active:
                raise WorkerPoolError("WORKERS_LEASED", "A Codex Task still owns a Worker lease; do not restart this runtime.", worker_id=active[0])
            print(json.dumps({"status": "OK", "leasedWorkerCount": 0}))
            return 0
        pool = WorkerPool(WorkerPoolConfig.load(), state_path=default_state_path())
        if args.command == "bootstrap":
            result: object = pool.bootstrap()
        else:
            result = [
                {
                    "workerId": row["worker_id"],
                    "state": row["state"],
                    "workIdentity": row.get("work_identity"),
                    "taskKey": row.get("task_key"),
                    "repository": row.get("repository_identity"),
                    "branch": row.get("branch"),
                    "failureReason": row.get("failure_reason"),
                }
                for row in pool.status()
                if row["worker_id"] in pool.config.worker_ids()
            ]
        print(json.dumps({"status": "OK", "result": result}, ensure_ascii=False, indent=2))
        return 0
    except WorkerPoolError as exc:
        print(json.dumps({"status": "HOLD", "reason": exc.reason, "workerId": exc.worker_id, "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
