"""Fixed, persistent local worker slots for bounded Codex dispatch."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
from typing import Any
from urllib.parse import urlsplit


MAX_WORKERS = 16
MAX_REPOSITORIES = 32
WORKER_STATES = {"FREE", "LEASED", "DIRTY", "QUARANTINED"}


class WorkerPoolError(RuntimeError):
    def __init__(self, reason: str, message: str, *, worker_id: str | None = None):
        super().__init__(message)
        self.reason = reason
        self.worker_id = worker_id


@dataclass(frozen=True)
class ManagedRepository:
    identity: str
    clone_url: str
    default_branch: str
    directory: str


@dataclass(frozen=True)
class WorkerPoolConfig:
    worker_count: int
    worker_root: Path
    repositories: tuple[ManagedRepository, ...]

    @classmethod
    def load(
        cls,
        *,
        config_path: Path | None = None,
        worker_root: Path | None = None,
    ) -> "WorkerPoolConfig":
        if config_path is None:
            configured_path = os.environ.get("LOCAL_OPERATIONS_WORKER_POOL_CONFIG")
            config_path = Path(configured_path) if configured_path else None
        if config_path is None:
            raise WorkerPoolError(
                "WORKER_POOL_NOT_CONFIGURED",
                "Set LOCAL_OPERATIONS_WORKER_POOL_CONFIG to a local managed-repository configuration.",
            )
        if not config_path.is_absolute():
            raise WorkerPoolError("WORKER_POOL_CONFIG_INVALID", "Worker Pool configuration path must be absolute.")
        try:
            document = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkerPoolError("WORKER_POOL_CONFIG_INVALID", "Worker Pool configuration is missing or invalid.") from exc
        if not isinstance(document, dict) or document.get("version") != 1:
            raise WorkerPoolError("WORKER_POOL_CONFIG_INVALID", "Worker Pool configuration version must be 1.")
        count = document.get("workerCount")
        repos = document.get("repositories")
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_WORKERS:
            raise WorkerPoolError("WORKER_POOL_CONFIG_INVALID", f"workerCount must be from 1 to {MAX_WORKERS}.")
        if not isinstance(repos, list) or not repos or len(repos) > MAX_REPOSITORIES:
            raise WorkerPoolError("WORKER_POOL_CONFIG_INVALID", f"repositories must contain 1 to {MAX_REPOSITORIES} entries.")

        normalized: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for entry in repos:
            if not isinstance(entry, dict):
                raise WorkerPoolError("WORKER_POOL_CONFIG_INVALID", "Each managed repository entry must be an object.")
            identity = entry.get("identity")
            clone_url = entry.get("cloneUrl")
            default_branch = entry.get("defaultBranch")
            if (
                not isinstance(identity, str)
                or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", identity)
                or any(part in {".", ".."} for part in identity.split("/"))
            ):
                raise WorkerPoolError("WORKER_POOL_CONFIG_INVALID", "Repository identity must use owner/name format.")
            key = identity.casefold()
            if key in seen:
                raise WorkerPoolError("WORKER_POOL_CONFIG_INVALID", "Managed repository identities must be unique.")
            seen.add(key)
            if not isinstance(clone_url, str) or not _safe_clone_url(clone_url):
                raise WorkerPoolError("WORKER_POOL_CONFIG_INVALID", "cloneUrl must be an HTTPS, SSH, or SCP Git URL without embedded credentials.")
            if (
                not isinstance(default_branch, str)
                or not re.fullmatch(r"[A-Za-z0-9._/-]{1,128}", default_branch)
                or default_branch.startswith(("/", "."))
                or default_branch.endswith(("/", ".", ".lock"))
                or "//" in default_branch
                or ".." in default_branch
                or "@{" in default_branch
            ):
                raise WorkerPoolError("WORKER_POOL_CONFIG_INVALID", "defaultBranch is invalid.")
            normalized.append((key, clone_url, default_branch))

        names = [identity.rsplit("/", 1)[1] for identity, _, _ in normalized]
        repositories = tuple(
            ManagedRepository(identity, url, branch, name if names.count(name) == 1 else identity.replace("/", "--"))
            for (identity, url, branch), name in zip(normalized, names)
        )
        if worker_root is None:
            configured_root = os.environ.get("LOCAL_OPERATIONS_WORKER_ROOT")
            worker_root = Path(configured_root) if configured_root else None
        if worker_root is None:
            raise WorkerPoolError("WORKER_POOL_NOT_CONFIGURED", "Set LOCAL_OPERATIONS_WORKER_ROOT to the local Worker Pool root.")
        if not worker_root.is_absolute():
            raise WorkerPoolError("WORKER_POOL_CONFIG_INVALID", "Worker Pool root must be an absolute local path.")
        resolved_root = worker_root.expanduser().resolve()
        for runtime in (Path("C:/Dev/DevEnv"), Path("C:/Dev/ProdEnv")):
            try:
                resolved_root.relative_to(runtime)
                overlaps = True
            except ValueError:
                try:
                    runtime.relative_to(resolved_root)
                    overlaps = True
                except ValueError:
                    overlaps = False
            if overlaps:
                raise WorkerPoolError("WORKER_POOL_CONFIG_INVALID", "Worker root must be separate from the Development and Production runtime checkouts.")
        return cls(count, resolved_root, repositories)

    def worker_ids(self) -> tuple[str, ...]:
        return tuple(f"worker-{index:02d}" for index in range(1, self.worker_count + 1))

    def repository(self, identity: str) -> ManagedRepository:
        normalized = _canonical_identity(identity)
        found = [repo for repo in self.repositories if repo.identity == normalized]
        if len(found) != 1:
            raise WorkerPoolError("MANAGED_REPOSITORY_NOT_FOUND", "Repository is not uniquely present in the local managed-repository configuration.")
        return found[0]

    def repository_path(self, worker_id: str, repository: ManagedRepository) -> Path:
        if worker_id not in self.worker_ids():
            raise WorkerPoolError("WORKER_NOT_FOUND", "Worker identity is not configured.", worker_id=worker_id)
        return self.worker_root / worker_id / repository.directory


def default_state_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "LocalOperations" / "dispatch-ledger.sqlite3"


def _safe_clone_url(value: str) -> bool:
    if any(ord(char) < 32 for char in value) or "\n" in value:
        return False
    if "://" in value:
        try:
            parsed = urlsplit(value)
            return parsed.scheme.casefold() in {"https", "ssh"} and bool(parsed.hostname) and parsed.username in {None, "git"} and not parsed.password and not parsed.query and not parsed.fragment
        except ValueError:
            return False
    return bool(re.fullmatch(r"(?:[A-Za-z0-9_.-]+@)?[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", value))


def _canonical_identity(value: str) -> str:
    raw = value.strip()
    if "://" in raw:
        parsed = urlsplit(raw)
        if not parsed.hostname or parsed.username not in {None, "git"} or parsed.password:
            raise WorkerPoolError("REPOSITORY_IDENTITY_UNVERIFIABLE", "Repository remote identity is invalid.")
        path = parsed.path.strip("/")
        host = parsed.hostname.casefold()
        if host != "github.com":
            raise WorkerPoolError("REPOSITORY_IDENTITY_UNVERIFIABLE", "Only configured GitHub owner/name identities are supported by Worker Pool V0.")
        raw = path
    else:
        scp = re.fullmatch(r"(?:[^@/\s]+@)?([^:/\s]+):(.+)", raw)
        if scp:
            if scp.group(1).casefold() != "github.com":
                raise WorkerPoolError("REPOSITORY_IDENTITY_UNVERIFIABLE", "Only configured GitHub owner/name identities are supported by Worker Pool V0.")
            raw = scp.group(2)
        elif raw.casefold().startswith("github.com/"):
            parts = raw.split("/")
            if len(parts) != 3:
                raise WorkerPoolError("REPOSITORY_IDENTITY_UNVERIFIABLE", "Only configured GitHub owner/name identities are supported by Worker Pool V0.")
            raw = "/".join(parts[1:])
    raw = raw.removesuffix(".git").strip("/").casefold()
    if not re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", raw):
        raise WorkerPoolError("REPOSITORY_IDENTITY_UNVERIFIABLE", "Repository must resolve to one GitHub owner/name identity.")
    return raw


def _git(repository: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *args], check=True, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=60,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # Do not surface git stderr: a configured credential helper or remote URL may contain private data.
        raise WorkerPoolError("WORKER_REPOSITORY_PREFLIGHT_FAILED", "A managed repository Git operation failed.") from exc
    return result.stdout.strip()


def _status(repository: Path) -> str:
    return _git(repository, "status", "--porcelain=v1", "--untracked-files=all")


def _identity_matches(repository: Path, expected: str) -> bool:
    if Path(_git(repository, "rev-parse", "--show-toplevel")).resolve() != repository.resolve():
        return False
    remotes = _git(repository, "remote").splitlines()
    if "origin" not in remotes:
        return False
    try:
        urls = _git(repository, "config", "--get-all", "remote.origin.url").splitlines()
    except WorkerPoolError:
        return False
    try:
        identities = {_canonical_identity(url) for url in urls}
    except WorkerPoolError:
        return False
    return identities == {expected}


class WorkerPool:
    """SQLite-backed atomic leases; Git changes are always fast-forward-only."""

    def __init__(self, config: WorkerPoolConfig, state_path: Path | None = None):
        self.config = config
        self.state_path = state_path or default_state_path()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS workers (
                    worker_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL CHECK(state IN ('FREE','LEASED','DIRTY','QUARANTINED')),
                    work_identity TEXT,
                    task_key TEXT,
                    repository_identity TEXT,
                    branch TEXT,
                    thread_id TEXT,
                    turn_id TEXT,
                    leased_at TEXT,
                    updated_at TEXT NOT NULL,
                    failure_reason TEXT
                )"""
            )
            for worker_id in config.worker_ids():
                connection.execute(
                    "INSERT OR IGNORE INTO workers(worker_id,state,updated_at) VALUES(?, 'FREE', datetime('now'))",
                    (worker_id,),
                )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.state_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def status(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM workers ORDER BY worker_id").fetchall()
        return [dict(row) for row in rows]

    def get_lease(self, worker_id: str, work_identity: str, task_key: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM workers WHERE worker_id=? AND work_identity=? AND task_key=? AND state='LEASED'",
                (worker_id, work_identity, task_key),
            ).fetchone()
        return dict(row) if row else None

    def dispatch_state(self, work_identity: str, task_key: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dispatches'"
            ).fetchone()
            if not exists:
                return None
            row = connection.execute(
                "SELECT state,thread_id,turn_id FROM dispatches WHERE work_identity=? AND task_key=?",
                (work_identity, task_key),
            ).fetchone()
        return dict(row) if row else None

    def find_task_lease(self, work_identity: str, task_key: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM workers WHERE work_identity=? AND task_key=? AND state='LEASED'",
                (work_identity, task_key),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        repo = self.config.repository(result["repository_identity"])
        result["repository_root"] = str(self.config.repository_path(result["worker_id"], repo).resolve())
        return result

    def bootstrap(self) -> list[dict[str, str]]:
        outcomes: list[dict[str, str]] = []
        states = {row["worker_id"]: row["state"] for row in self.status()}
        for worker_id in self.config.worker_ids():
            if states.get(worker_id) != "FREE":
                raise WorkerPoolError("WORKER_NOT_FREE", "Bootstrap requires every configured Worker Slot to be FREE.", worker_id=worker_id)
            for repo in self.config.repositories:
                target = self.config.repository_path(worker_id, repo)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    try:
                        subprocess.run(
                            ["git", "clone", "--origin", "origin", "--branch", repo.default_branch, repo.clone_url, str(target)],
                            check=True, capture_output=True, text=True, encoding="utf-8", timeout=300,
                        )
                    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                        raise WorkerPoolError("WORKER_BOOTSTRAP_FAILED", "A configured repository clone could not be created.", worker_id=worker_id) from exc
                    outcomes.append({"workerId": worker_id, "repository": repo.identity, "result": "CLONED"})
                elif target.is_dir() and _identity_matches(target, repo.identity) and not _status(target):
                    outcomes.append({"workerId": worker_id, "repository": repo.identity, "result": "EXISTS_VALIDATED"})
                else:
                    self._quarantine(worker_id, "BOOTSTRAP_FOUND_UNEXPECTED_LOCAL_STATE")
                    raise WorkerPoolError("WORKER_BOOTSTRAP_UNEXPECTED_STATE", "An existing Worker repository is unexpected or dirty; it was preserved and the slot quarantined.", worker_id=worker_id)
        return outcomes

    def lease(self, *, work_identity: str, task_key: str, repository_identity: str, branch: str) -> dict[str, Any]:
        repository = self.config.repository(repository_identity)
        selected: str | None = None
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = connection.execute(
                "SELECT * FROM workers WHERE work_identity=? AND task_key=? AND state='LEASED'",
                (work_identity, task_key),
            ).fetchone()
            if duplicate:
                connection.rollback()
                raise WorkerPoolError("WORKER_TASK_ALREADY_LEASED", "This Task already has a leased Worker; inspect its existing dispatch before retrying.", worker_id=duplicate["worker_id"])
            for worker_id in self.config.worker_ids():
                row = connection.execute("SELECT state FROM workers WHERE worker_id=?", (worker_id,)).fetchone()
                if row and row["state"] == "FREE":
                    selected = worker_id
                    break
            if selected is None:
                connection.rollback()
                raise WorkerPoolError("NO_FREE_WORKER", "No configured Worker Slot is FREE.")
            connection.execute(
                """UPDATE workers SET state='LEASED',work_identity=?,task_key=?,repository_identity=?,
                    branch=?,thread_id=NULL,turn_id=NULL,leased_at=datetime('now'),updated_at=datetime('now'),
                    failure_reason=NULL WHERE worker_id=? AND state='FREE'""",
                (work_identity, task_key, repository.identity, branch, selected),
            )
            connection.commit()

        try:
            target_path = self.config.repository_path(selected, repository)
            if not target_path.is_dir() or not _identity_matches(target_path, repository.identity):
                raise WorkerPoolError("WORKER_REPOSITORY_UNAVAILABLE", "The selected Worker clone is missing or has the wrong remote.", worker_id=selected)
            if _status(target_path):
                raise WorkerPoolError("WORKER_REPOSITORY_DIRTY", "The selected Worker clone has uncommitted changes; nothing was discarded.", worker_id=selected)
            _git(target_path, "check-ref-format", "--branch", branch)
            _git(target_path, "fetch", "origin")
            remote_branch = f"refs/remotes/origin/{branch}"
            remote_commit = _git(target_path, "rev-parse", "--verify", f"{remote_branch}^{{commit}}")
            current_branch = _git(target_path, "branch", "--show-current")
            current_commit = _git(target_path, "rev-parse", "HEAD")
            if current_branch != branch:
                local_branch = _git(target_path, "branch", "--list", branch)
                if local_branch:
                    _git(target_path, "checkout", branch)
                else:
                    _git(target_path, "checkout", "--track", "-b", branch, remote_branch)
            current_commit = _git(target_path, "rev-parse", "HEAD")
            if current_commit != remote_commit:
                relation = _git(target_path, "rev-list", "--left-right", "--count", f"HEAD...{remote_branch}")
                ahead, behind = [int(part) for part in relation.split()]
                if ahead or behind == 0:
                    raise WorkerPoolError("WORKER_BRANCH_DIVERGED", "The requested Worker branch diverges from origin or has local-only commits; it was not reset.", worker_id=selected)
                _git(target_path, "merge", "--ff-only", remote_branch)
            if _status(target_path):
                raise WorkerPoolError("WORKER_REPOSITORY_DIRTY", "Repository preparation left unexpected working-tree changes; nothing was discarded.", worker_id=selected)
            target_commit = _git(target_path, "rev-parse", "HEAD")
            with closing(self._connect()) as connection:
                connection.execute("UPDATE workers SET updated_at=datetime('now') WHERE worker_id=? AND state='LEASED'", (selected,))
            return {
                "worker_id": selected,
                "repository": repository.identity,
                "repository_root": str(target_path.resolve()),
                "branch": branch,
                "repository_commit": target_commit,
            }
        except WorkerPoolError as exc:
            self._quarantine(selected, exc.reason)
            raise
        except Exception as exc:
            self._quarantine(selected, "WORKER_PREPARATION_UNEXPECTED_FAILURE")
            raise WorkerPoolError("WORKER_PREPARATION_FAILED", "Worker preparation failed and the slot was quarantined without cleanup.", worker_id=selected) from exc

    def record_dispatch(self, worker_id: str, work_identity: str, task_key: str, *, thread_id: str | None, turn_id: str | None) -> None:
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """UPDATE workers SET thread_id=?,turn_id=?,updated_at=datetime('now')
                   WHERE worker_id=? AND state='LEASED' AND work_identity=? AND task_key=?""",
                (thread_id, turn_id, worker_id, work_identity, task_key),
            )
            if cursor.rowcount != 1:
                raise WorkerPoolError("WORKER_LEASE_LOST", "The dispatch Worker lease could not be updated.", worker_id=worker_id)

    def abort_pre_dispatch(self, worker_id: str, work_identity: str, task_key: str) -> bool:
        lease = self.get_lease(worker_id, work_identity, task_key)
        if not lease or lease.get("thread_id") or lease.get("turn_id"):
            return False
        try:
            self._release_clean(worker_id, lease, require_completed_turn=False)
            return True
        except WorkerPoolError:
            return False

    def release_task(self, worker_id: str, work_identity: str, task_key: str) -> dict[str, Any]:
        lease = self.get_lease(worker_id, work_identity, task_key)
        if not lease:
            raise WorkerPoolError("WORKER_LEASE_NOT_FOUND", "No matching active Worker lease exists.", worker_id=worker_id)
        repo = self.config.repository(lease["repository_identity"])
        path = self.config.repository_path(worker_id, repo)
        if not path.is_dir() or not _identity_matches(path, repo.identity):
            raise WorkerPoolError("WORKER_REPOSITORY_UNAVAILABLE", "The leased Worker clone is missing or has the wrong remote.", worker_id=worker_id)
        if _git(path, "branch", "--show-current") != lease["branch"]:
            raise WorkerPoolError("WORKER_BRANCH_MISMATCH", "The leased Worker is no longer on its Task branch.", worker_id=worker_id)
        if _status(path):
            raise WorkerPoolError("WORKER_REPOSITORY_DIRTY", "The Task clone still has uncommitted changes; the Worker remains leased.", worker_id=worker_id)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE workers SET state='FREE',work_identity=NULL,task_key=NULL,repository_identity=NULL,
                    branch=NULL,thread_id=NULL,turn_id=NULL,leased_at=NULL,updated_at=datetime('now'),failure_reason=NULL
                   WHERE worker_id=? AND state='LEASED' AND work_identity=? AND task_key=?""",
                (worker_id, work_identity, task_key),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise WorkerPoolError("WORKER_LEASE_NOT_FOUND", "The matching Worker lease changed during release.", worker_id=worker_id)
            connection.commit()
        return {"workerId": worker_id, "state": "FREE", "releasedTaskKey": task_key}

    def _quarantine(self, worker_id: str, reason: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                "UPDATE workers SET state='QUARANTINED',failure_reason=?,updated_at=datetime('now') WHERE worker_id=?",
                (reason[:160], worker_id),
            )


def bootstrap_worker_pool(*, config_path: Path | None = None, worker_root: Path | None = None, state_path: Path | None = None) -> list[dict[str, str]]:
    config = WorkerPoolConfig.load(config_path=config_path, worker_root=worker_root)
    return WorkerPool(config, state_path=state_path).bootstrap()
