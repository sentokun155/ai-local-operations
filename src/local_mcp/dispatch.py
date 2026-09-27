"""Bounded Codex task dispatch over the local app-server JSON-RPC protocol."""

from __future__ import annotations

import atexit
from contextlib import closing
import hashlib
import json
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import unquote, urlsplit


_VALID_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max", "ultra"}
_TEXT_LIMIT = 512
_THREAD_NAME_LIMIT = 180
_REQUEST_TIMEOUT_SECONDS = 30
_EVENT_TIMEOUT_SECONDS = 10
_MAX_REGISTRY_ENTRIES = 256
_MAX_WORKTREES_PER_ROOT = 512


class DispatchValidationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        reason: str = "INPUT_VALIDATION_ERROR",
        diagnostic: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.reason = reason
        self.diagnostic = diagnostic


class AppServerUnavailable(RuntimeError):
    pass


class AppServerResponseError(RuntimeError):
    """A JSON-RPC error response, which proves the request was rejected."""


class AppServerTransportError(RuntimeError):
    def __init__(self, message: str, *, request_sent: bool):
        super().__init__(message)
        self.request_sent = request_sent


class AppServerClient:
    """One persistent app-server subprocess owned by the MCP server process."""

    def __init__(self, executable: str | None = None):
        self._executable = executable or os.environ.get("LOCAL_OPERATIONS_CODEX_EXECUTABLE")
        self._process: subprocess.Popen[str] | None = None
        self._reader_threads: list[threading.Thread] = []
        self._response_condition = threading.Condition()
        self._responses: dict[int, dict[str, Any]] = {}
        self._notifications: deque[dict[str, Any]] = deque(maxlen=128)
        self._unexpected_requests: deque[dict[str, Any]] = deque(maxlen=16)
        self._request_id = 0
        self._request_lock = threading.RLock()
        self._stderr_tail: deque[str] = deque(maxlen=20)

    def ensure_ready(self) -> None:
        with self._request_lock:
            if self._process is not None and self._process.poll() is None:
                return

            executable = self._executable or shutil.which("codex")
            if not executable:
                raise AppServerUnavailable("Codex CLI was not found on PATH.")

            try:
                process = subprocess.Popen(
                    [executable, "app-server", "--stdio"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
            except OSError as exc:
                raise AppServerUnavailable("Codex app-server could not be started.") from exc

            self._process = process
            self._reader_threads = [
                threading.Thread(target=self._read_stdout, args=(process,), daemon=True),
                threading.Thread(target=self._read_stderr, args=(process,), daemon=True),
            ]
            for reader in self._reader_threads:
                reader.start()

            try:
                self._request_locked(
                    "initialize",
                    {
                        "clientInfo": {"name": "local-operations", "version": "0.1.0"},
                        "capabilities": {"experimentalApi": True},
                    },
                )
                self._write_notification("initialized", {})
            except (AppServerUnavailable, AppServerResponseError, AppServerTransportError) as exc:
                self.close()
                raise AppServerUnavailable("Codex app-server initialization failed.") from exc

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        with self._request_lock:
            self.ensure_ready()
            return self._request_locked(method, params)

    def wait_for_turn_started(self, thread_id: str, turn_id: str, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._request_lock:
            while True:
                for index, message in enumerate(self._notifications):
                    if message.get("method") != "turn/started":
                        continue
                    params = message.get("params", {})
                    turn = params.get("turn", {})
                    if params.get("threadId") == thread_id and turn.get("id") == turn_id:
                        del self._notifications[index]
                        return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                with self._response_condition:
                    self._response_condition.wait(timeout=min(remaining, 0.25))
                if self._process is None or self._process.poll() is not None:
                    return False

    def wait_for_turn_completed(self, thread_id: str, turn_id: str, timeout: float) -> dict[str, Any] | None:
        """Wait for a matching completion notification; used by local verification harnesses."""
        deadline = time.monotonic() + timeout
        with self._request_lock:
            while True:
                for index, message in enumerate(self._notifications):
                    if message.get("method") != "turn/completed":
                        continue
                    params = message.get("params", {})
                    turn = params.get("turn", {})
                    if params.get("threadId") == thread_id and turn.get("id") == turn_id:
                        del self._notifications[index]
                        return turn if isinstance(turn, dict) else None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                with self._response_condition:
                    self._response_condition.wait(timeout=min(remaining, 0.25))
                if self._process is None or self._process.poll() is not None:
                    return None

    def _request_locked(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        process = self._process
        if process is None or process.poll() is not None or process.stdin is None:
            raise AppServerTransportError("Codex app-server is not running.", request_sent=False)

        self._request_id += 1
        request_id = self._request_id
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        try:
            process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            process.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise AppServerTransportError(
                "The app-server connection failed while sending a request.", request_sent=True
            ) from exc

        deadline = time.monotonic() + _REQUEST_TIMEOUT_SECONDS
        with self._response_condition:
            while request_id not in self._responses:
                if process.poll() is not None:
                    raise AppServerTransportError(
                        "Codex app-server exited before acknowledging the request.", request_sent=True
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AppServerTransportError(
                        "Codex app-server did not acknowledge the request in time.", request_sent=True
                    )
                self._response_condition.wait(timeout=min(remaining, 0.25))
            response = self._responses.pop(request_id)

        if "error" in response:
            error = response.get("error") or {}
            raise AppServerResponseError(
                f"{method} was rejected ({error.get('code', 'unknown')}): {error.get('message', 'unspecified error')}"
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise AppServerTransportError(
                f"{method} returned an invalid response.", request_sent=True
            )
        return result

    def _write_notification(self, method: str, params: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise AppServerUnavailable("Codex app-server is not running.")
        try:
            process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n")
            process.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise AppServerUnavailable("Codex app-server initialization failed.") from exc

    def _read_stdout(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            with self._response_condition:
                if isinstance(message.get("id"), int) and ("result" in message or "error" in message):
                    self._responses[message["id"]] = message
                elif isinstance(message.get("id"), int) and "method" in message:
                    self._unexpected_requests.append(message)
                    self._send_unsupported_request_response(process, message)
                elif message.get("method") in {"turn/started", "turn/completed"}:
                    self._notifications.append(message)
                self._response_condition.notify_all()
        process.stdout.close()
        with self._response_condition:
            self._response_condition.notify_all()

    def _send_unsupported_request_response(self, process: subprocess.Popen[str], message: dict[str, Any]) -> None:
        if process.stdin is None or process.poll() is not None:
            return
        response = {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "error": {"code": -32601, "message": "Local Operations does not support interactive approval requests."},
        }
        try:
            process.stdin.write(json.dumps(response) + "\n")
            process.stdin.flush()
        except (OSError, BrokenPipeError):
            pass

    def _read_stderr(self, process: subprocess.Popen[str]) -> None:
        assert process.stderr is not None
        for line in process.stderr:
            self._stderr_tail.append(line.rstrip())
        process.stderr.close()

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
            process.terminate()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=2)
            except OSError:
                pass
            except subprocess.TimeoutExpired:
                pass
        for reader in self._reader_threads:
            if reader is not threading.current_thread():
                reader.join(timeout=2)
        self._reader_threads = []
        for stream in (process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


_default_client: AppServerClient | None = None
_default_client_lock = threading.Lock()


def _get_default_client() -> AppServerClient:
    global _default_client
    with _default_client_lock:
        if _default_client is None:
            _default_client = AppServerClient()
            atexit.register(_default_client.close)
        return _default_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _text(value: Any, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise DispatchValidationError(f"{field} must be a string.")
    cleaned = value.strip()
    if not cleaned and optional:
        return None
    if not cleaned:
        raise DispatchValidationError(f"{field} is required.")
    if len(cleaned) > _TEXT_LIMIT:
        raise DispatchValidationError(f"{field} is longer than {_TEXT_LIMIT} characters.")
    if any(ord(char) < 32 for char in cleaned):
        raise DispatchValidationError(f"{field} cannot contain control characters.")
    return cleaned


def _git(repository: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise DispatchValidationError("The repository or branch could not be verified.") from exc
    return result.stdout.strip()


def _workspace_error(
    reason: str,
    message: str,
    *,
    missing_fact: str,
    attempted_resolver: str,
    ambiguous: bool = False,
    recovery_action: str,
) -> DispatchValidationError:
    return DispatchValidationError(
        message,
        reason=reason,
        diagnostic={
            "failureClass": reason,
            "missingFact": missing_fact,
            "attemptedResolver": attempted_resolver,
            "ambiguous": ambiguous,
            "recoveryAction": recovery_action,
        },
    )


def _is_absolute_path(value: str) -> bool:
    return Path(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _canonical_repository_identity(value: str, *, remote: bool = False) -> str:
    """Normalize a logical identity or Git remote to host/namespace/repository."""
    raw = value.strip()
    host: str | None = None
    path: str | None = None

    if "://" in raw:
        parsed = urlsplit(raw)
        if parsed.scheme.lower() not in {"http", "https", "ssh", "git"} or not parsed.hostname:
            raise DispatchValidationError("repository must be a host-qualified repository identity or Git remote URL.")
        host = parsed.hostname.casefold()
        try:
            port = parsed.port
        except ValueError as exc:
            raise DispatchValidationError("repository remote URL contains an invalid port.") from exc
        if port:
            host = f"{host}:{port}"
        path = unquote(parsed.path).strip("/")
    else:
        scp_match = re.fullmatch(r"(?:[^@/\s]+@)?([^:/\s]+):(.+)", raw)
        if scp_match and (remote or "." in scp_match.group(1) or scp_match.group(1).lower() == "localhost"):
            host = scp_match.group(1).casefold()
            path = scp_match.group(2).strip("/")
        else:
            parts = raw.strip("/").split("/")
            if len(parts) == 2:
                host = "github.com"
                path = "/".join(parts)
            elif len(parts) >= 3 and ("." in parts[0] or parts[0].lower() == "localhost"):
                host = parts[0].casefold()
                path = "/".join(parts[1:])
            else:
                raise DispatchValidationError(
                    "repository must be owner/name (GitHub) or a host-qualified identity such as github.example/owner/name."
                )

    if not host or not path:
        raise DispatchValidationError("repository identity is incomplete.")
    if path.lower().endswith(".git"):
        path = path[:-4]
    components = path.split("/")
    if len(components) < 2 or any(component in {"", ".", ".."} for component in components):
        raise DispatchValidationError("repository identity must include a namespace and repository name.")
    return f"{host}/{path}".casefold()


def _repository_remote_identities(repository: Path) -> set[str]:
    identities: set[str] = set()
    remote_names = _git(repository, "remote").splitlines()
    for remote_name in remote_names:
        try:
            # Read the configured URL. `remote get-url` expands insteadOf rewrites
            # used by the isolated E2E fixture and may otherwise hide repository identity.
            urls = _git(repository, "config", "--get-all", f"remote.{remote_name}.url").splitlines()
        except DispatchValidationError:
            continue
        for url in urls:
            try:
                identities.add(_canonical_repository_identity(url, remote=True))
            except DispatchValidationError:
                continue
    return identities


def _repository_root(path_text: str, *, resolver: str) -> Path:
    try:
        path = Path(path_text).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise _workspace_error(
            "WORKSPACE_NOT_FOUND",
            "The selected local repository path does not exist.",
            missing_fact="an existing local Git repository root",
            attempted_resolver=resolver,
            recovery_action="Correct the explicit path or add the intended root to the Local Operations repository registry.",
        ) from exc
    if not path.is_dir():
        raise _workspace_error(
            "WORKSPACE_NOT_FOUND",
            "The selected local repository path is not a directory.",
            missing_fact="a local Git repository directory",
            attempted_resolver=resolver,
            recovery_action="Provide the repository root directory, not a file path.",
        )
    try:
        root = Path(_git(path, "rev-parse", "--show-toplevel")).resolve(strict=True)
    except DispatchValidationError as exc:
        raise _workspace_error(
            "WRONG_REPOSITORY",
            "The selected path is not inside a readable Git repository.",
            missing_fact="Git repository metadata at the selected path",
            attempted_resolver=resolver,
            recovery_action="Register or provide the root of a valid local Git repository.",
        ) from exc
    if root != path:
        raise _workspace_error(
            "WRONG_REPOSITORY",
            "The selected path must be the Git repository or worktree root.",
            missing_fact="the exact Git repository root",
            attempted_resolver=resolver,
            recovery_action="Provide the repository root rather than a nested directory.",
        )
    return root


def _default_registry_path() -> Path:
    configured = os.environ.get("LOCAL_OPERATIONS_REPOSITORY_REGISTRY")
    if configured:
        return Path(configured).expanduser()
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "LocalOperations" / "repositories.json"


def _load_repository_registry(path: Path) -> dict[str, list[str]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise _workspace_error(
            "WORKSPACE_NOT_FOUND",
            "No local repository mapping is configured for this repository identity.",
            missing_fact="a mapping from repository identity to one or more local repository roots",
            attempted_resolver="Local Operations repositories.json registry",
            recovery_action="Create %LOCALAPPDATA%/LocalOperations/repositories.json and add the canonical repository identity with its local root path.",
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _workspace_error(
            "WORKSPACE_REGISTRY_INVALID",
            "The Local Operations repository registry could not be read as valid JSON.",
            missing_fact="a readable, valid repositories.json registry",
            attempted_resolver="Local Operations repositories.json registry",
            recovery_action="Repair the registry JSON and keep its version at 1.",
        ) from exc

    if not isinstance(document, dict) or document.get("version") != 1 or not isinstance(document.get("repositories"), dict):
        raise _workspace_error(
            "WORKSPACE_REGISTRY_INVALID",
            "The Local Operations repository registry has an unsupported structure.",
            missing_fact="version 1 registry data with a repositories object",
            attempted_resolver="Local Operations repositories.json registry",
            recovery_action="Use the documented version 1 repositories.json format.",
        )
    entries = document["repositories"]
    if len(entries) > _MAX_REGISTRY_ENTRIES:
        raise _workspace_error(
            "WORKSPACE_REGISTRY_INVALID",
            "The Local Operations repository registry exceeds its bounded entry limit.",
            missing_fact=f"at most {_MAX_REGISTRY_ENTRIES} repository identities",
            attempted_resolver="Local Operations repositories.json registry",
            recovery_action="Remove unused repository mappings.",
        )

    normalized: dict[str, list[str]] = {}
    try:
        for identity, roots in entries.items():
            if not isinstance(identity, str) or not isinstance(roots, list) or not roots:
                raise ValueError("registry identity must map to a non-empty list of root paths")
            key = _canonical_repository_identity(identity)
            if key in normalized:
                raise ValueError("registry contains duplicate normalized repository identities")
            if not all(isinstance(root, str) and _is_absolute_path(root) for root in roots):
                raise ValueError("registry root paths must be absolute strings")
            normalized[key] = roots
    except (ValueError, DispatchValidationError) as exc:
        raise _workspace_error(
            "WORKSPACE_REGISTRY_INVALID",
            "The Local Operations repository registry contains an invalid identity or root path.",
            missing_fact="canonical repository identities and absolute local root paths",
            attempted_resolver="Local Operations repositories.json registry",
            recovery_action="Correct the invalid registry entry; use github.com/owner/repo or another host-qualified identity.",
        ) from exc
    return normalized


def _registered_worktree_roots(roots: list[str]) -> list[Path]:
    result: dict[str, Path] = {}
    for configured_root in roots:
        root = _repository_root(configured_root, resolver="configured repository roots")
        result[os.path.normcase(str(root))] = root
        try:
            output = _git(root, "worktree", "list", "--porcelain")
        except DispatchValidationError as exc:
            raise _workspace_error(
                "WORKSPACE_REGISTRY_INVALID",
                "Git worktree metadata could not be read for a configured repository root.",
                missing_fact="readable Git worktree metadata",
                attempted_resolver="registered Git roots and their linked worktrees",
                recovery_action="Repair the registered Git repository or remove that root from the registry.",
            ) from exc
        worktree_paths = [line[len("worktree ") :] for line in output.splitlines() if line.startswith("worktree ")]
        if len(worktree_paths) > _MAX_WORKTREES_PER_ROOT:
            raise _workspace_error(
                "WORKSPACE_REGISTRY_INVALID",
                "A registered repository has more worktrees than the bounded resolver supports.",
                missing_fact=f"at most {_MAX_WORKTREES_PER_ROOT} linked worktrees per registered root",
                attempted_resolver="registered Git roots and their linked worktrees",
                recovery_action="Register the intended worktree root directly and remove excess unused worktrees.",
            )
        for worktree_path in worktree_paths:
            try:
                worktree = Path(worktree_path).resolve(strict=True)
                if not worktree.is_dir():
                    continue
                actual_root = Path(_git(worktree, "rev-parse", "--show-toplevel")).resolve(strict=True)
                if actual_root == worktree:
                    result[os.path.normcase(str(worktree))] = worktree
            except (OSError, RuntimeError, DispatchValidationError):
                continue
    return list(result.values())


def _resolve_from_registry(identity: str, branch: str, registry_path: Path) -> tuple[Path, str]:
    registry = _load_repository_registry(registry_path)
    configured_roots = registry.get(identity)
    if not configured_roots:
        raise _workspace_error(
            "WORKSPACE_NOT_FOUND",
            "The repository identity is not present in the Local Operations registry.",
            missing_fact=f"a local root mapping for {identity}",
            attempted_resolver="Local Operations repositories.json registry and linked Git worktrees",
            recovery_action="Add this repository identity and its local root to repositories.json; no other directories were scanned.",
        )
    candidates = _registered_worktree_roots(configured_roots)
    matching_identity: list[Path] = []
    unverifiable_count = 0
    for candidate in candidates:
        remote_identities = _repository_remote_identities(candidate)
        if not remote_identities:
            unverifiable_count += 1
            continue
        if identity in remote_identities:
            matching_identity.append(candidate)
    if not matching_identity:
        if unverifiable_count == len(candidates):
            raise _workspace_error(
                "REPOSITORY_IDENTITY_UNVERIFIABLE",
                "The registered repository has no verifiable Git remote identity.",
                missing_fact="a configured fetch remote matching the requested repository identity",
                attempted_resolver="Local Operations registry roots and their linked Git worktrees",
                recovery_action="Configure a Git remote for this repository; V0 fails closed for repositories without one.",
            )
        raise _workspace_error(
            "WRONG_REPOSITORY",
            "No registered root has a Git remote matching the requested repository identity.",
            missing_fact=f"a Git remote matching {identity}",
            attempted_resolver="Local Operations registry roots and their linked Git worktrees",
            recovery_action="Correct the registry mapping or the repository identity; the resolver does not fall back to another repository.",
        )

    branch_matches = [candidate for candidate in matching_identity if _git(candidate, "branch", "--show-current") == branch]
    if not branch_matches:
        raise _workspace_error(
            "BRANCH_MISMATCH",
            "The requested branch is not checked out in any registered matching repository or linked worktree.",
            missing_fact=f"a worktree for branch {branch}",
            attempted_resolver="registered Git roots and linked worktrees with matching repository remotes",
            recovery_action="Check out the requested branch in a registered worktree, or update the requested branch.",
        )
    if len(branch_matches) > 1:
        raise _workspace_error(
            "WORKSPACE_AMBIGUOUS",
            "Multiple registered worktrees match the repository identity and branch.",
            missing_fact="one unique local worktree for the requested repository and branch",
            attempted_resolver="Local Operations repository registry and linked Git worktrees",
            ambiguous=True,
            recovery_action="Remove duplicate roots from the registry or provide repository_path as an explicit override.",
        )
    candidate = branch_matches[0]
    return candidate, "local_registry_git_worktree" if candidate not in [Path(p).resolve() for p in configured_roots] else "local_registry"


def _resolve_workspace(
    repository_input: str | None,
    repository_path_input: str | None,
    locator: str,
    branch: str,
    registry_path: Path,
) -> tuple[Path, str, str]:
    expected_identity: str | None = None
    explicit_path = repository_path_input
    resolver_source = "explicit_repository_path"

    if repository_input and _is_absolute_path(repository_input):
        if explicit_path:
            raise DispatchValidationError("repository cannot be a local path when repository_path is also supplied.")
        explicit_path = repository_input
        resolver_source = "legacy_repository_path"
    elif repository_input:
        expected_identity = _canonical_repository_identity(repository_input)

    if explicit_path:
        repository = _repository_root(explicit_path, resolver="explicit repository_path override")
    elif expected_identity:
        repository, resolver_source = _resolve_from_registry(expected_identity, branch, registry_path)
    elif _is_absolute_path(locator):
        try:
            request_file = Path(locator).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise _workspace_error(
                "TASK_REQUEST_NOT_FOUND",
                "The absolute Task Request path does not exist.",
                missing_fact="an existing absolute Task Request file path",
                attempted_resolver="legacy absolute Task Request path compatibility mode",
                recovery_action="Provide a current Task Request path or use repository identity plus a configured root mapping.",
            ) from exc
        if not request_file.is_file():
            raise _workspace_error(
                "TASK_REQUEST_NOT_FOUND",
                "The absolute Task Request path does not identify a file.",
                missing_fact="an absolute Task Request file path",
                attempted_resolver="legacy absolute Task Request path compatibility mode",
                recovery_action="Provide the absolute path to the Task Request file.",
            )
        try:
            repository = Path(_git(request_file.parent, "rev-parse", "--show-toplevel")).resolve(strict=True)
        except DispatchValidationError as exc:
            raise _workspace_error(
                "WRONG_REPOSITORY",
                "The absolute Task Request file is not inside a Git repository.",
                missing_fact="a Git repository containing the Task Request file",
                attempted_resolver="legacy absolute Task Request path compatibility mode",
                recovery_action="Use a Task Request inside a Git repository, or provide a configured logical repository identity.",
            ) from exc
        resolver_source = "legacy_absolute_task_request_path"
    else:
        raise _workspace_error(
            "WORKSPACE_NOT_FOUND",
            "A logical repository identity is required when no explicit local path is provided.",
            missing_fact="logical repository identity or explicit repository_path override",
            attempted_resolver="Local Operations repository registry; app-server process cwd is not used as a fallback",
            recovery_action="Send repository as owner/name or host/owner/name, and configure its local root in repositories.json.",
        )

    remote_identities = _repository_remote_identities(repository)
    if not remote_identities:
        raise _workspace_error(
            "REPOSITORY_IDENTITY_UNVERIFIABLE",
            "The selected repository has no verifiable Git remote identity.",
            missing_fact="a Git fetch remote identifying the repository",
            attempted_resolver=resolver_source,
            recovery_action="Configure a Git remote; V0 fails closed when repository identity cannot be verified.",
        )
    if expected_identity:
        if expected_identity not in remote_identities:
            raise _workspace_error(
                "WRONG_REPOSITORY",
                "The selected repository's Git remotes do not match the requested identity.",
                missing_fact=f"a Git remote matching {expected_identity}",
                attempted_resolver=resolver_source,
                recovery_action="Correct repository identity or the explicit path; no other repository is selected automatically.",
            )
        resolved_identity = expected_identity
    else:
        if len(remote_identities) != 1:
            raise _workspace_error(
                "REPOSITORY_IDENTITY_AMBIGUOUS",
                "The selected repository has multiple distinct Git remote identities and no expected identity was supplied.",
                missing_fact="one unique expected repository identity",
                attempted_resolver=resolver_source,
                ambiguous=True,
                recovery_action="Provide repository as a logical identity matching one remote.",
            )
        resolved_identity = next(iter(remote_identities))

    actual_branch = _git(repository, "branch", "--show-current")
    if not actual_branch or actual_branch != branch:
        raise _workspace_error(
            "BRANCH_MISMATCH",
            "The selected repository is not checked out on the requested branch.",
            missing_fact=f"the requested branch {branch} checked out at the selected repository root",
            attempted_resolver=resolver_source,
            recovery_action="Select a matching registered worktree or provide an explicit path for the requested branch.",
        )
    return repository, resolved_identity, resolver_source


def _validate(params: dict[str, Any], *, registry_path: Path | None = None) -> dict[str, Any]:
    work_identity = _text(params.get("work_identity"), "work_identity")
    task_key = _text(params.get("task_key"), "task_key")
    task_name = _text(params.get("task_name"), "task_name")
    locator = _text(params.get("task_request_locator"), "task_request_locator")
    repository_text = _text(params.get("repository"), "repository", optional=True)
    repository_path = _text(params.get("repository_path"), "repository_path", optional=True)
    branch = _text(params.get("branch"), "branch")
    model = _text(params.get("model"), "model", optional=True)
    effort = _text(params.get("reasoning_effort"), "reasoning_effort", optional=True)
    if effort and effort not in _VALID_EFFORTS:
        raise DispatchValidationError(f"reasoning_effort must be one of: {', '.join(sorted(_VALID_EFFORTS))}.")

    if registry_path is None:
        registry_path = _default_registry_path()
    workspace_override = params.get("_resolved_worker_repository")
    if workspace_override is not None:
        try:
            repository = Path(workspace_override).resolve(strict=True)
            root = Path(_git(repository, "rev-parse", "--show-toplevel")).resolve(strict=True)
        except (OSError, RuntimeError, DispatchValidationError) as exc:
            raise _workspace_error(
                "WORKER_REPOSITORY_UNAVAILABLE",
                "The selected Worker repository is not a readable Git root.",
                missing_fact="the configured managed repository root inside the selected Worker",
                attempted_resolver="fixed Local Worker Pool configuration",
                recovery_action="Run the bounded Worker Pool bootstrap and repair the configured managed repository.",
            ) from exc
        if root != repository:
            raise _workspace_error(
                "WRONG_REPOSITORY", "The selected Worker path must be a Git repository root.",
                missing_fact="the Worker repository root", attempted_resolver="fixed Local Worker Pool configuration",
                recovery_action="Repair the configured Worker repository path.",
            )
        repository_identity = _canonical_repository_identity(repository_text or "")
        identities = _repository_remote_identities(repository)
        if identities != {repository_identity}:
            raise _workspace_error(
                "WRONG_REPOSITORY", "The selected Worker repository remote does not match the requested identity.",
                missing_fact="an origin remote matching the logical repository identity",
                attempted_resolver="fixed Local Worker Pool managed-repository configuration",
                recovery_action="Repair the configured clone URL; the Worker was not dispatched.",
            )
        actual_branch = _git(repository, "branch", "--show-current")
        if actual_branch != branch:
            raise _workspace_error(
                "BRANCH_MISMATCH", "The selected Worker repository is not on the requested branch.",
                missing_fact=f"the requested branch {branch}", attempted_resolver="fixed Local Worker Pool preparation",
                recovery_action="Inspect or quarantine the Worker; no automatic reset was performed.",
            )
        resolution_source = "fixed_worker_pool"
    else:
        repository, repository_identity, resolution_source = _resolve_workspace(
            repository_text, repository_path, locator, branch, registry_path
        )

    locator_path = Path(locator)
    candidate = locator_path.expanduser() if _is_absolute_path(locator) else repository / locator_path
    try:
        candidate = candidate.resolve(strict=True)
        relative = candidate.relative_to(repository)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _workspace_error(
            "TASK_REQUEST_OUTSIDE_REPOSITORY",
            "task_request_locator does not identify a file inside the resolved repository.",
            missing_fact="a repository-relative Task Request path",
            attempted_resolver=resolution_source,
            recovery_action="Provide the Task Request path relative to the selected repository root.",
        ) from exc
    if not candidate.is_file():
        raise _workspace_error(
            "TASK_REQUEST_NOT_FOUND",
            "task_request_locator does not identify a file.",
            missing_fact="the Task Request file at the supplied repository-relative path",
            attempted_resolver=resolution_source,
            recovery_action="Correct the Task Request locator; it is not searched for elsewhere.",
        )
    relative_posix = relative.as_posix()
    commit = _git(repository, "rev-parse", "HEAD")
    # These revision values are receipt diagnostics, not dispatch gates.
    try:
        current_request_blob = _git(repository, "hash-object", f"--path={relative_posix}", str(candidate))
    except DispatchValidationError:
        current_request_blob = ""

    thread_name = f"{task_key} {task_name}"
    if len(thread_name) > _THREAD_NAME_LIMIT:
        raise DispatchValidationError(f"Task Key plus Task Name must be at most {_THREAD_NAME_LIMIT} characters.")

    return {
        "work_identity": work_identity,
        "task_key": task_key,
        "task_name": task_name,
        "task_request_locator": relative_posix,
        "repository": str(repository),
        "repository_identity": repository_identity,
        "workspace_resolution_source": resolution_source,
        "branch": branch,
        "repository_commit": commit,
        "task_request_blob_id": current_request_blob,
        "model": model,
        "reasoning_effort": effort,
        "thread_name": thread_name,
    }


class DispatchLedger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS dispatches (
                    work_identity TEXT NOT NULL,
                    task_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    task_request_locator TEXT NOT NULL,
                    repository TEXT NOT NULL,
                    repository_identity TEXT,
                    workspace_resolution_source TEXT,
                    worker_id TEXT,
                    resolved_repository_root TEXT,
                    branch TEXT NOT NULL,
                    repository_commit TEXT NOT NULL,
                    task_request_blob_id TEXT NOT NULL,
                    thread_name TEXT NOT NULL,
                    model_requested TEXT,
                    reasoning_effort_requested TEXT,
                    state TEXT NOT NULL,
                    thread_id TEXT,
                    turn_id TEXT,
                    model_reported TEXT,
                    reasoning_effort_reported TEXT,
                    dispatched_at TEXT,
                    thread_name_confirmed INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (work_identity, task_key)
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS finalized_results (
                    work_identity TEXT NOT NULL,
                    task_key TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (work_identity, task_key)
                )"""
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(dispatches)")}
            if "repository_identity" not in columns:
                connection.execute("ALTER TABLE dispatches ADD COLUMN repository_identity TEXT")
            if "workspace_resolution_source" not in columns:
                connection.execute("ALTER TABLE dispatches ADD COLUMN workspace_resolution_source TEXT")
            if "worker_id" not in columns:
                connection.execute("ALTER TABLE dispatches ADD COLUMN worker_id TEXT")
            if "resolved_repository_root" not in columns:
                connection.execute("ALTER TABLE dispatches ADD COLUMN resolved_repository_root TEXT")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def _request_hash(data: dict[str, Any]) -> str:
        # Keep the V0 hash projection stable so existing SQLite receipts remain idempotent.
        stable_fields = {
            "work_identity", "task_key", "task_name", "task_request_locator", "repository",
            "branch", "model", "reasoning_effort",
            "thread_name",
        }
        payload = {key: data[key] for key in sorted(stable_fields)}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def get_or_create(self, data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        request_hash = self._request_hash(data)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM dispatches WHERE work_identity=? AND task_key=?",
                (data["work_identity"], data["task_key"]),
            ).fetchone()
            if row is not None:
                result = dict(row)
                connection.commit()
                return result, False
            connection.execute(
                """INSERT INTO dispatches (
                    work_identity, task_key, request_hash, task_name, task_request_locator,
                    repository, repository_identity, workspace_resolution_source, worker_id, resolved_repository_root, branch,
                    repository_commit, task_request_blob_id, thread_name,
                    model_requested, reasoning_effort_requested, state, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PREPARED', ?)""",
                (
                    data["work_identity"], data["task_key"], request_hash, data["task_name"],
                    data["task_request_locator"], data["repository"], data["repository_identity"],
                    data["workspace_resolution_source"], data.get("worker_id"), data.get("resolved_repository_root"), data["branch"],
                    data["repository_commit"], data["task_request_blob_id"], data["thread_name"],
                    data["model"], data["reasoning_effort"], _now(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM dispatches WHERE work_identity=? AND task_key=?",
                (data["work_identity"], data["task_key"]),
            ).fetchone()
            connection.commit()
            return dict(row), True

    def claim(self, data: dict[str, Any], next_state: str) -> str | None:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state, request_hash FROM dispatches WHERE work_identity=? AND task_key=?",
                (data["work_identity"], data["task_key"]),
            ).fetchone()
            if row is None or row["request_hash"] != self._request_hash(data):
                connection.rollback()
                return None
            state = row["state"]
            allowed = {"PREPARED"} if next_state == "THREAD_STARTING" else {"THREAD_CREATED"}
            if state not in allowed:
                connection.rollback()
                return None
            connection.execute(
                "UPDATE dispatches SET state=?, last_error=NULL, updated_at=? WHERE work_identity=? AND task_key=?",
                (next_state, _now(), data["work_identity"], data["task_key"]),
            )
            connection.commit()
            return state

    def update(self, data: dict[str, Any], **fields: Any) -> None:
        allowed = {
            "state", "thread_id", "turn_id", "model_reported", "reasoning_effort_reported",
            "dispatched_at", "thread_name_confirmed", "last_error",
        }
        if not fields or set(fields) - allowed:
            raise ValueError("invalid dispatch ledger update")
        fields["updated_at"] = _now()
        assignments = ", ".join(f"{key}=?" for key in fields)
        values = list(fields.values()) + [data["work_identity"], data["task_key"]]
        with closing(self._connect()) as connection:
            connection.execute(
                f"UPDATE dispatches SET {assignments} WHERE work_identity=? AND task_key=?", values
            )

    def get(self, data: dict[str, Any]) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM dispatches WHERE work_identity=? AND task_key=?",
                (data["work_identity"], data["task_key"]),
            ).fetchone()
            return dict(row) if row is not None else None

    def find(self, work_identity: str, task_key: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM dispatches WHERE work_identity=? AND task_key=?",
                (work_identity, task_key),
            ).fetchone()
        return dict(row) if row is not None else None

    def finalized_result(self, work_identity: str, task_key: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT result_json FROM finalized_results WHERE work_identity=? AND task_key=?",
                (work_identity, task_key),
            ).fetchone()
        if not row:
            return None
        result = json.loads(row["result_json"])
        return result if isinstance(result, dict) else None

    def save_finalization(self, work_identity: str, task_key: str, result: dict[str, Any]) -> None:
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        with closing(self._connect()) as connection:
            connection.execute(
                """INSERT INTO finalized_results(work_identity,task_key,result_json,updated_at)
                   VALUES(?,?,?,?) ON CONFLICT(work_identity,task_key) DO UPDATE SET
                   result_json=excluded.result_json,updated_at=excluded.updated_at""",
                (work_identity, task_key, encoded, _now()),
            )

    def release_if_prepared(self, data: dict[str, Any]) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                "DELETE FROM dispatches WHERE work_identity=? AND task_key=? AND request_hash=? AND state='PREPARED'",
                (data["work_identity"], data["task_key"], self._request_hash(data)),
            )

    def rebind_prepared_revision(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Refresh diagnostic revision fields for an unfinished compatible dispatch."""
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """UPDATE dispatches SET request_hash=?,repository_commit=?,task_request_blob_id=?,updated_at=?
                   WHERE work_identity=? AND task_key=? AND state IN ('PREPARED','THREAD_CREATED')
                   AND task_name=? AND task_request_locator=? AND repository=? AND branch=? AND thread_name=?
                   AND model_requested IS ? AND reasoning_effort_requested IS ?""",
                (
                    self._request_hash(data), data["repository_commit"], data["task_request_blob_id"],
                    _now(), data["work_identity"], data["task_key"], data["task_name"],
                    data["task_request_locator"], data["repository"], data["branch"], data["thread_name"],
                    data["model"], data["reasoning_effort"],
                ),
            )
            row = connection.execute(
                "SELECT * FROM dispatches WHERE work_identity=? AND task_key=?",
                (data["work_identity"], data["task_key"]),
            ).fetchone()
            connection.commit()
        return dict(row) if row is not None else None


def _manifest(data: dict[str, Any]) -> str:
    return json.dumps(
        {
            "workIdentity": data["work_identity"],
            "taskKey": data["task_key"],
            "taskName": data["task_name"],
            "taskRequestLocator": data["task_request_locator"],
            "repository": data["repository"],
            "repositoryIdentity": data["repository_identity"],
            "workspaceResolutionSource": data["workspace_resolution_source"],
            "branch": data["branch"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _prompt(data: dict[str, Any]) -> str:
    return (
        "The following repository-backed Task Request is the canonical scope for this task. "
        "Read exactly the current specified file in the requested repository and work on the requested "
        "branch. If the file cannot be read, stop and report HOLD without making changes. Do not "
        "substitute another task, branch, or file. Work only within the specified repository. This dispatch grants "
        "no authority for force-push, merge, publication, deployment, or other external side effects.\n"
        "Dispatch manifest (data): " + _manifest(data)
    )


def _model_capabilities(
    client: AppServerClient,
    data: dict[str, Any],
    *,
    existing_model: str | None = None,
    existing_effort: str | None = None,
) -> tuple[str, str | None]:
    """Resolve the effective model and reject an unsupported requested effort before creating a thread."""
    config_result = client.request("config/read", {"cwd": data["repository"]})
    config = config_result.get("config")
    if not isinstance(config, dict):
        raise AppServerUnavailable("Codex app-server did not return its effective configuration.")

    configured_model = config.get("model")
    selected_model = data["model"] or existing_model or (configured_model if isinstance(configured_model, str) else None)
    configured_effort = config.get("model_reasoning_effort")
    effective_effort = data["reasoning_effort"] or existing_effort or (configured_effort if isinstance(configured_effort, str) else None)

    cursor: str | None = None
    models: list[dict[str, Any]] = []
    for _ in range(20):
        params: dict[str, Any] = {"limit": 100, "includeHidden": True}
        if cursor:
            params["cursor"] = cursor
        page = client.request("model/list", params)
        page_data = page.get("data")
        if not isinstance(page_data, list):
            raise AppServerUnavailable("Codex app-server did not return its model catalog.")
        models.extend(model for model in page_data if isinstance(model, dict))
        next_cursor = page.get("nextCursor")
        if not next_cursor:
            break
        if not isinstance(next_cursor, str) or next_cursor == cursor:
            raise AppServerUnavailable("Codex app-server returned an invalid model-catalog cursor.")
        cursor = next_cursor
    else:
        raise AppServerUnavailable("Codex app-server model catalog exceeded the supported page limit.")

    selected = next(
        (model for model in models if selected_model and selected_model in {model.get("model"), model.get("id")}),
        None,
    )
    if selected is None and selected_model is None:
        selected = next((model for model in models if model.get("isDefault") is True), None)
    if selected is None:
        raise DispatchValidationError(f"The requested Codex model is not available: {selected_model or '(default)' }.")

    selected_name = selected.get("model") or selected.get("id")
    if not isinstance(selected_name, str) or not selected_name:
        raise AppServerUnavailable("Codex app-server returned a model without an identifier.")
    supported = {
        option.get("reasoningEffort")
        for option in selected.get("supportedReasoningEfforts", [])
        if isinstance(option, dict)
    }
    if effective_effort and effective_effort not in supported:
        choices = ", ".join(sorted(str(choice) for choice in supported)) or "none reported"
        raise DispatchValidationError(
            f"reasoning_effort {effective_effort!r} is not supported by {selected_name}; supported values: {choices}."
        )
    return selected_name, effective_effort


def _receipt(row: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "status": status,
        "workIdentity": row["work_identity"],
        "taskKey": row["task_key"],
        "taskName": row["task_name"],
        "threadId": row.get("thread_id"),
        "turnId": row.get("turn_id"),
        "threadName": row["thread_name"],
        "threadNameConfirmed": bool(row.get("thread_name_confirmed", 0)),
        "taskRequestLocator": row["task_request_locator"],
        "taskRequestBlobId": row["task_request_blob_id"],
        "repository": row["repository"],
        "repositoryIdentity": row.get("repository_identity"),
        "workspaceResolutionSource": row.get("workspace_resolution_source"),
        "workerId": row.get("worker_id"),
        "resolvedRepositoryRoot": row.get("resolved_repository_root"),
        "repositoryCommit": row["repository_commit"],
        "branch": row["branch"],
        "modelRequested": row["model_requested"],
        "modelReported": row.get("model_reported"),
        "reasoningEffortRequested": row["reasoning_effort_requested"],
        "reasoningEffortReported": row.get("reasoning_effort_reported"),
        "dispatchedAt": row.get("dispatched_at"),
    }


def _hold(
    reason: str,
    message: str,
    row: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "HOLD", "reason": reason, "message": message}
    if diagnostic:
        result["diagnostic"] = diagnostic
    if row:
        result["workIdentity"] = row["work_identity"]
        result["taskKey"] = row["task_key"]
        result["threadId"] = row.get("thread_id")
        result["dispatchedAt"] = row.get("dispatched_at")
    return result


def dispatch_task(
    params: dict[str, Any],
    *,
    client_factory: Any = _get_default_client,
    state_path: Path | None = None,
    registry_path: Path | None = None,
    worker_pool_config_path: Path | None = None,
    worker_root: Path | None = None,
) -> dict[str, Any]:
    if state_path is None:
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        state_path = base / "LocalOperations" / "dispatch-ledger.sqlite3"

    worker_pool = None
    worker_lease: dict[str, Any] | None = None
    validate_params = dict(params)
    uses_worker_pool = False
    repository_input = params.get("repository")
    path_input = params.get("repository_path")
    locator_input = params.get("task_request_locator")
    has_explicit_path = any(
        isinstance(value, str) and _is_absolute_path(value)
        for value in (repository_input, path_input, locator_input)
    )
    # Passing a registry_path is retained as a bounded compatibility/test override.
    if registry_path is None and not has_explicit_path:
        try:
            from .worker_pool import WorkerPool, WorkerPoolConfig, WorkerPoolError

            work_identity = _text(params.get("work_identity"), "work_identity")
            task_key = _text(params.get("task_key"), "task_key")
            repository_identity = _canonical_repository_identity(_text(repository_input, "repository") or "")
            task_name = _text(params.get("task_name"), "task_name")
            locator = _text(locator_input, "task_request_locator")
            branch = _text(params.get("branch"), "branch")
            model = _text(params.get("model"), "model", optional=True)
            effort = _text(params.get("reasoning_effort"), "reasoning_effort", optional=True)
            ledger = DispatchLedger(state_path)
            existing = ledger.find(work_identity, task_key)
            worker_pool = WorkerPool(
                WorkerPoolConfig.load(config_path=worker_pool_config_path, worker_root=worker_root),
                state_path=state_path,
            )
            if existing:
                stable_match = (
                    existing.get("repository_identity") == repository_identity
                    and existing.get("task_name") == task_name
                    and existing.get("task_request_locator") == locator
                    and existing.get("branch") == branch
                    and existing.get("model_requested") == model
                    and existing.get("reasoning_effort_requested") == effort
                )
                if not stable_match:
                    return _hold("IDEMPOTENCY_KEY_CONFLICT", "This work_identity and task_key are already bound to different dispatch inputs.", existing)
                if existing["state"] == "ACCEPTED":
                    return _receipt(existing, "ALREADY_DISPATCHED")
                if existing["state"] in {"THREAD_STARTING", "TURN_STARTING", "UNKNOWN"}:
                    return _hold("DISPATCH_OUTCOME_UNKNOWN", "A prior dispatch may have been accepted. No duplicate was sent; inspect its saved Codex thread.", existing)
                active_lease = worker_pool.find_task_lease(work_identity, task_key)
                if active_lease and existing["state"] in {"PREPARED", "THREAD_CREATED"}:
                    worker_lease = active_lease
                elif existing["state"] == "THREAD_CREATED":
                    return _hold("WORKER_LEASE_NOT_FOUND", "The rejected dispatch thread has no matching Worker lease; recovery is required before retry.", existing)
            if worker_lease is None:
                worker_lease = worker_pool.lease(
                    work_identity=work_identity,
                    task_key=task_key,
                    repository_identity=repository_identity,
                    branch=branch,
                )
            validate_params["_resolved_worker_repository"] = worker_lease["repository_root"]
            uses_worker_pool = True
        except (WorkerPoolError, DispatchValidationError) as exc:
            reason = getattr(exc, "reason", "INPUT_VALIDATION_ERROR")
            diagnostic = {"workerId": getattr(exc, "worker_id", None)}
            if diagnostic["workerId"] is None:
                diagnostic = None
            return _hold(reason, str(exc), diagnostic=diagnostic)

    try:
        data = _validate(validate_params, registry_path=registry_path)
    except DispatchValidationError as exc:
        if uses_worker_pool and worker_lease:
            worker_pool.abort_pre_dispatch(worker_lease["worker_id"], params.get("work_identity", ""), params.get("task_key", ""))
        return _hold(exc.reason, str(exc), diagnostic=exc.diagnostic)

    if uses_worker_pool and worker_lease:
        data["worker_id"] = worker_lease["worker_id"]
        data["resolved_repository_root"] = worker_lease["repository_root"]

    try:
        ledger = ledger if uses_worker_pool else DispatchLedger(state_path)
        row, _created = ledger.get_or_create(data)
    except (OSError, sqlite3.Error) as exc:
        return _hold("DISPATCH_LEDGER_UNAVAILABLE", "The duplicate-protection ledger is unavailable; nothing was dispatched.")

    if row["request_hash"] != DispatchLedger._request_hash(data):
        if row["state"] in {"PREPARED", "THREAD_CREATED"}:
            row = ledger.rebind_prepared_revision(data) or row
        if row["request_hash"] != DispatchLedger._request_hash(data):
            if uses_worker_pool and worker_lease:
                worker_pool.abort_pre_dispatch(worker_lease["worker_id"], data["work_identity"], data["task_key"])
            return _hold("IDEMPOTENCY_KEY_CONFLICT", "This work_identity and task_key are already bound to different dispatch inputs.", row)
    if row["state"] == "ACCEPTED":
        if uses_worker_pool and worker_lease:
            worker_pool.abort_pre_dispatch(worker_lease["worker_id"], data["work_identity"], data["task_key"])
        return _receipt(row, "ALREADY_DISPATCHED")
    if row["state"] in {"THREAD_STARTING", "TURN_STARTING", "UNKNOWN"}:
        return _hold(
            "DISPATCH_OUTCOME_UNKNOWN",
            "A prior dispatch may have been accepted. No duplicate was sent; inspect the existing Codex thread before retrying.",
            row,
        )
    if row["state"] not in {"PREPARED", "THREAD_CREATED"}:
        return _hold("DISPATCH_STATE_INVALID", "The saved dispatch state is not recognized.", row)

    try:
        client = client_factory()
        client.ensure_ready()
    except AppServerUnavailable:
        ledger.release_if_prepared(data)
        if uses_worker_pool and worker_lease:
            worker_pool.abort_pre_dispatch(worker_lease["worker_id"], data["work_identity"], data["task_key"])
        return _hold("CODEX_UNAVAILABLE", "Codex app-server is unavailable. No thread or turn was started.", row)

    try:
        resolved_model, resolved_effort = _model_capabilities(
            client,
            data,
            existing_model=row.get("model_reported") if row["state"] == "THREAD_CREATED" else None,
            existing_effort=row.get("reasoning_effort_reported") if row["state"] == "THREAD_CREATED" else None,
        )
    except DispatchValidationError as exc:
        ledger.release_if_prepared(data)
        if uses_worker_pool and worker_lease:
            worker_pool.abort_pre_dispatch(worker_lease["worker_id"], data["work_identity"], data["task_key"])
        return _hold("MODEL_CONFIGURATION_ERROR", str(exc), row)
    except (AppServerUnavailable, AppServerResponseError, AppServerTransportError):
        ledger.release_if_prepared(data)
        if uses_worker_pool and worker_lease:
            worker_pool.abort_pre_dispatch(worker_lease["worker_id"], data["work_identity"], data["task_key"])
        return _hold("CODEX_CAPABILITY_UNAVAILABLE", "Codex model capabilities could not be verified. No new turn was started.", row)

    starting_new_thread = row["state"] == "PREPARED"
    next_state = "THREAD_STARTING" if starting_new_thread else "TURN_STARTING"
    previous_state = ledger.claim(data, next_state)
    if previous_state is None:
        current = ledger.get(data)
        if current and current["state"] == "ACCEPTED":
            return _receipt(current, "ALREADY_DISPATCHED")
        return _hold("DISPATCH_ALREADY_IN_PROGRESS", "Another caller claimed this dispatch key; no duplicate was sent.", current)

    thread_id = row.get("thread_id")
    if not starting_new_thread and thread_id and uses_worker_pool and worker_lease:
        worker_pool.record_dispatch(worker_lease["worker_id"], data["work_identity"], data["task_key"], thread_id=thread_id, turn_id=None)
    if starting_new_thread:
        thread_params: dict[str, Any] = {
            "cwd": data["repository"],
            "runtimeWorkspaceRoots": [data["repository"]],
            "ephemeral": False,
            "approvalPolicy": "never",
            "sandbox": "workspace-write",
        }
        thread_params["model"] = resolved_model
        try:
            thread_result = client.request("thread/start", thread_params)
        except AppServerResponseError as exc:
            ledger.update(data, state="PREPARED", last_error=str(exc)[:1000])
            if uses_worker_pool and worker_lease:
                worker_pool.abort_pre_dispatch(worker_lease["worker_id"], data["work_identity"], data["task_key"])
            return _hold("CODEX_REJECTED", "Codex rejected thread creation. The same dispatch key may be retried.", ledger.get(data))
        except AppServerTransportError as exc:
            if exc.request_sent:
                ledger.update(data, state="UNKNOWN", last_error=str(exc)[:1000])
                return _hold("DISPATCH_OUTCOME_UNKNOWN", "Thread creation may have succeeded, but its acknowledgement was lost. Do not retry this key.", ledger.get(data))
            ledger.update(data, state="PREPARED", last_error=str(exc)[:1000])
            return _hold("CODEX_UNAVAILABLE", "Codex app-server became unavailable before thread creation.", ledger.get(data))
        except Exception as exc:
            ledger.update(data, state="UNKNOWN", last_error=type(exc).__name__)
            return _hold("DISPATCH_OUTCOME_UNKNOWN", "Thread creation may have succeeded. Do not retry this key.", ledger.get(data))

        thread = thread_result.get("thread")
        thread_id = thread.get("id") if isinstance(thread, dict) else None
        if not isinstance(thread_id, str) or not thread_id:
            ledger.update(data, state="UNKNOWN", last_error="thread/start response did not include a thread id")
            return _hold("DISPATCH_OUTCOME_UNKNOWN", "Codex acknowledged thread creation without a usable thread id. Do not retry this key.", ledger.get(data))
        ledger.update(
            data,
            state="THREAD_CREATED",
            thread_id=thread_id,
            model_reported=thread_result.get("model"),
            reasoning_effort_reported=thread_result.get("reasoningEffort"),
            last_error=None,
        )
        if uses_worker_pool and worker_lease:
            worker_pool.record_dispatch(worker_lease["worker_id"], data["work_identity"], data["task_key"], thread_id=thread_id, turn_id=None)

    if starting_new_thread:
        claimed = ledger.claim(data, "TURN_STARTING")
        if claimed is None:
            current = ledger.get(data)
            return _hold("DISPATCH_ALREADY_IN_PROGRESS", "Another caller claimed this turn; no duplicate was sent.", current)

    turn_params: dict[str, Any] = {
        "threadId": thread_id,
        "input": [{"type": "text", "text": _prompt(data)}],
        "cwd": data["repository"],
    }
    turn_params["model"] = resolved_model
    if resolved_effort:
        turn_params["effort"] = resolved_effort
    try:
        turn_result = client.request("turn/start", turn_params)
    except AppServerResponseError as exc:
        ledger.update(data, state="THREAD_CREATED", last_error=str(exc)[:1000])
        return _hold("CODEX_REJECTED", "Codex rejected the turn. The existing thread is saved and the same dispatch key may be retried.", ledger.get(data))
    except AppServerTransportError as exc:
        if exc.request_sent:
            ledger.update(data, state="UNKNOWN", last_error=str(exc)[:1000])
            return _hold("DISPATCH_OUTCOME_UNKNOWN", "The turn may have started, but its acknowledgement was lost. Do not retry this key.", ledger.get(data))
        ledger.update(data, state="THREAD_CREATED", last_error=str(exc)[:1000])
        return _hold("CODEX_UNAVAILABLE", "Codex app-server became unavailable before the turn started.", ledger.get(data))
    except Exception as exc:
        ledger.update(data, state="UNKNOWN", last_error=type(exc).__name__)
        return _hold("DISPATCH_OUTCOME_UNKNOWN", "The turn may have started. Do not retry this key.", ledger.get(data))

    turn = turn_result.get("turn")
    turn_id = turn.get("id") if isinstance(turn, dict) else None
    if not isinstance(turn_id, str) or not turn_id:
        ledger.update(data, state="UNKNOWN", last_error="turn/start response did not include a turn id")
        return _hold("DISPATCH_OUTCOME_UNKNOWN", "Codex acknowledged turn start without a usable turn id. Do not retry this key.", ledger.get(data))

    dispatched_at = _now()
    ledger.update(data, state="ACCEPTED", turn_id=turn_id, dispatched_at=dispatched_at, last_error=None)
    if uses_worker_pool and worker_lease:
        worker_pool.record_dispatch(worker_lease["worker_id"], data["work_identity"], data["task_key"], thread_id=thread_id, turn_id=turn_id)

    name_confirmed = False
    try:
        if client.wait_for_turn_started(thread_id, turn_id, _EVENT_TIMEOUT_SECONDS):
            try:
                thread_state = client.request("thread/read", {"threadId": thread_id, "includeTurns": False}).get("thread")
                if isinstance(thread_state, dict):
                    reported: dict[str, Any] = {}
                    for source, destination in (("model", "model_reported"), ("reasoningEffort", "reasoning_effort_reported")):
                        value = thread_state.get(source)
                        if isinstance(value, str) and value:
                            reported[destination] = value
                    if reported:
                        ledger.update(data, **reported)
            except Exception:
                pass
            try:
                client.request("thread/name/set", {"threadId": thread_id, "name": data["thread_name"]})
                name_confirmed = True
            except Exception:
                name_confirmed = False
    except Exception:
        name_confirmed = False
    if name_confirmed:
        ledger.update(data, thread_name_confirmed=1)
    receipt_row = ledger.get(data) or row
    return _receipt(receipt_row, "DISPATCHED")
