"""Prepare and restart the fixed Local Operations Production runtime."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit


PRODUCTION_ROOT = Path("C:/Dev/ProdEnv")
REPOSITORY_IDENTITY = "sentokun155/ai-local-operations"
CLONE_URL = "https://github.com/sentokun155/ai-local-operations.git"
PRODUCTION_PROFILE = "local-operations"
DEVELOPMENT_PROFILE = "local-operations-dev"
PRODUCTION_COMMAND = "uv --directory C:/Dev/ProdEnv run --locked python server.py"
PRODUCTION_READY_MARKER = "PRODUCTION_READY=http://127.0.0.1:8080/readyz"


class _ProductionFailure(RuntimeError):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def _run(
    command: list[str],
    *,
    runner: Callable[..., Any],
    check: bool = True,
    timeout: int = 120,
) -> tuple[int, str]:
    try:
        completed = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _ProductionFailure("RUNTIME_COMMAND_FAILED", "A Production runtime command could not be completed.") from exc
    code = int(getattr(completed, "returncode", 1))
    output = getattr(completed, "stdout", "") or ""
    if check and code != 0:
        raise _ProductionFailure("RUNTIME_COMMAND_FAILED", "A Production runtime command failed; local data was preserved.")
    return code, output


def _git(root: Path, *args: str, runner: Callable[..., Any], check: bool = True) -> str:
    _, output = _run(["git", "-C", str(root), *args], runner=runner, check=check)
    return output.strip()


def _repository_identity(remote: str) -> str | None:
    raw = remote.strip()
    if raw.startswith(("https://", "ssh://")):
        try:
            parsed = urlsplit(raw)
            hostname = parsed.hostname
        except ValueError:
            return None
        if (
            hostname is None
            or hostname.casefold() != "github.com"
            or parsed.username not in {None, "git"}
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            return None
        value = parsed.path.strip("/")
    else:
        match = re.fullmatch(r"(?:[^@/\s]+@)?([^:/\s]+):(.+)", raw)
        if not match or match.group(1).casefold() != "github.com":
            return None
        value = match.group(2).strip("/")
    value = value.removesuffix(".git").casefold()
    return value if re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", value) else None


def _validate_branch(branch: str, *, runner: Callable[..., Any]) -> None:
    if (
        not isinstance(branch, str)
        or not branch
        or len(branch) > 128
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", branch)
        or "//" in branch
        or ".." in branch
        or branch.endswith(("/", ".", ".lock"))
        or "@{" in branch
    ):
        raise _ProductionFailure("INVALID_BRANCH", "branch must be a valid Git branch name.")
    # Git performs the final syntax check without needing an initialized repo.
    code, _ = _run(["git", "check-ref-format", "--branch", branch], runner=runner)
    if code != 0:
        raise _ProductionFailure("INVALID_BRANCH", "branch must be a valid Git branch name.")


def _ensure_checkout(root: Path, branch: str, *, runner: Callable[..., Any]) -> str:
    if not root.exists():
        root.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--origin", "origin", "--branch", branch, CLONE_URL, str(root)], runner=runner, timeout=300)
        try:
            remote = _git(root, "remote", "get-url", "origin", runner=runner)
            current = _git(root, "branch", "--show-current", runner=runner)
        except _ProductionFailure as exc:
            raise _ProductionFailure("WRONG_REPOSITORY", "The new Production clone could not be verified.") from exc
        if _repository_identity(remote) != REPOSITORY_IDENTITY or current != branch:
            raise _ProductionFailure("WRONG_REPOSITORY", "The new Production clone does not match the requested repository and branch.")
        return "CLONED"
    if not root.is_dir():
        raise _ProductionFailure("PRODUCTION_PATH_INVALID", "The Production runtime path exists and is not a directory.")

    try:
        remote = _git(root, "remote", "get-url", "origin", runner=runner)
    except _ProductionFailure as exc:
        raise _ProductionFailure("WRONG_REPOSITORY", "The Production runtime origin could not be verified.") from exc
    if _repository_identity(remote) != REPOSITORY_IDENTITY:
        raise _ProductionFailure("WRONG_REPOSITORY", "The Production runtime origin is not the configured repository.")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all", runner=runner):
        raise _ProductionFailure("PRODUCTION_CHECKOUT_DIRTY", "Production checkout has local changes; they were preserved.")

    branch_refspec = f"refs/heads/{branch}:refs/remotes/origin/{branch}"
    _git(root, "fetch", "origin", branch_refspec, runner=runner)
    local_ref = f"refs/heads/{branch}"
    remote_ref = f"refs/remotes/origin/{branch}"
    has_local = _run(["git", "-C", str(root), "show-ref", "--verify", "--quiet", local_ref], runner=runner, check=False)[0] == 0
    has_remote = _run(["git", "-C", str(root), "show-ref", "--verify", "--quiet", remote_ref], runner=runner, check=False)[0] == 0
    if not has_remote:
        raise _ProductionFailure("REQUESTED_BRANCH_NOT_FOUND", "The requested branch was not found on origin.")

    action = "UNCHANGED"
    current = _git(root, "branch", "--show-current", runner=runner)
    if current != branch:
        if has_local:
            _git(root, "switch", branch, runner=runner)
        else:
            _git(root, "switch", "--no-track", "-c", branch, f"origin/{branch}", runner=runner)
            return "BRANCH_SWITCHED"
        action = "BRANCH_SWITCHED"

    counts = _git(root, "rev-list", "--left-right", "--count", f"HEAD...origin/{branch}", runner=runner)
    try:
        ahead, behind = (int(value) for value in counts.split())
    except (TypeError, ValueError) as exc:
        raise _ProductionFailure("BRANCH_STATE_UNAVAILABLE", "Git could not compare the requested Production branch.") from exc
    if ahead and behind:
        raise _ProductionFailure("BRANCH_DIVERGED", "Production branch and origin have diverged; no local commits were changed.")
    if behind:
        _git(root, "merge", "--ff-only", f"origin/{branch}", runner=runner)
        action = "FAST_FORWARDED"
    return action


def _tunnel_id(content: str) -> str | None:
    match = re.search(r"(?im)^[ \t]*tunnel_id:[ \t]*[\"']?([^\"'\s#]+)", content)
    return match.group(1) if match else None


def _normalize_command(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    value = value.replace("\\", "/").replace("\"", "").replace("'", "")
    return re.sub(r"\s+", " ", value).strip().casefold()


def _profile_path(environment: Mapping[str, str]) -> Path | None:
    appdata = environment.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "tunnel-client" / f"{PRODUCTION_PROFILE}.yaml"


def _update_profile_command(profile: Path) -> str:
    try:
        content = profile.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise _ProductionFailure("PRODUCTION_PROFILE_UNAVAILABLE", "The Production profile could not be read.") from exc
    if not _tunnel_id(content):
        raise _ProductionFailure("PRODUCTION_TUNNEL_ID_MISSING", "The Production profile has no Tunnel ID.")
    if "env:CONTROL_PLANE_API_KEY" not in content:
        raise _ProductionFailure("PRODUCTION_CREDENTIAL_REFERENCE_MISSING", "The Production profile must reference CONTROL_PLANE_API_KEY through the environment.")
    command_lines = list(re.finditer(r"(?im)^(?P<indent>[ \t]*)command[ \t]*:[ \t]*(?P<value>[^\r\n]*)(?P<lineending>\r?\n|$)", content))
    if len(command_lines) != 1:
        raise _ProductionFailure("PRODUCTION_MCP_COMMAND_UNAVAILABLE", "The Production profile must contain one MCP command.")
    match = command_lines[0]
    if _normalize_command(match.group("value")) == _normalize_command(PRODUCTION_COMMAND):
        return "UNCHANGED"
    replacement = f"{match.group('indent')}command: {PRODUCTION_COMMAND}{match.group('lineending')}"
    updated = content[:match.start()] + replacement + content[match.end():]
    temp_name: str | None = None
    try:
        handle, temp_name = tempfile.mkstemp(prefix=f".{profile.name}.", suffix=".tmp", dir=profile.parent)
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as temp:
            temp.write(updated)
        os.replace(temp_name, profile)
    except OSError as exc:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        raise _ProductionFailure("PRODUCTION_PROFILE_UPDATE_FAILED", "The Production profile command could not be updated.") from exc
    return "UPDATED"


def prepare_runtime(
    branch: str,
    *,
    production_root: Path = PRODUCTION_ROOT,
    profile_path: Path | None = None,
    restart_script: Path | None = None,
    runner: Callable[..., Any] = subprocess.run,
    environment: Mapping[str, str] | None = None,
    powershell: str = "pwsh.exe",
) -> dict[str, Any]:
    """Prepare the fixed Production checkout, then restart its configured Tunnel."""
    env = environment if environment is not None else os.environ
    response: dict[str, Any] = {
        "status": "HOLD", "repository": REPOSITORY_IDENTITY,
        "runtimePath": str(production_root), "branch": branch,
        "profile": PRODUCTION_PROFILE, "checkoutAction": None,
        "profileAction": None, "tunnelRestarted": False, "ready": False,
        "healthUrl": "http://127.0.0.1:8080/readyz", "reason": None,
    }
    try:
        _validate_branch(branch, runner=runner)
        response["checkoutAction"] = _ensure_checkout(production_root, branch, runner=runner)

        profile = profile_path or _profile_path(env)
        if profile is None or not profile.is_file():
            response["reason"] = "PRODUCTION_PROFILE_MISSING"
            return response
        try:
            content = profile.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise _ProductionFailure("PRODUCTION_PROFILE_UNAVAILABLE", "The Production profile could not be read.") from exc
        prod_id = _tunnel_id(content)
        if not prod_id:
            response["reason"] = "PRODUCTION_TUNNEL_ID_MISSING"
            return response
        if "env:CONTROL_PLANE_API_KEY" not in content:
            raise _ProductionFailure("PRODUCTION_CREDENTIAL_REFERENCE_MISSING", "The Production profile must reference CONTROL_PLANE_API_KEY through the environment.")

        if profile_path is None and env.get("APPDATA"):
            dev_profile = Path(env["APPDATA"]) / "tunnel-client" / f"{DEVELOPMENT_PROFILE}.yaml"
            if dev_profile.is_file():
                try:
                    dev_id = _tunnel_id(dev_profile.read_text(encoding="utf-8-sig"))
                except (OSError, UnicodeError):
                    dev_id = None
                if dev_id and dev_id == prod_id:
                    raise _ProductionFailure("TUNNEL_PROFILE_COLLISION", "Development and Production profiles use the same Tunnel ID.")

        command_action = _update_profile_command(profile)
        response["profileAction"] = command_action
        if not env.get("CONTROL_PLANE_API_KEY"):
            response["reason"] = "CONTROL_PLANE_API_KEY_MISSING"
            return response

        if restart_script is None:
            restart_script = Path(__file__).resolve().parents[2] / "scripts" / "restart-prod.ps1"
        code, output = _run(
            [powershell, "-NoProfile", "-File", str(restart_script), "-Branch", branch],
            runner=runner,
            check=False,
            timeout=180,
        )
        if code != 0:
            response["reason"] = "PRODUCTION_RESTART_FAILED"
            return response
        response["tunnelRestarted"] = True
        if PRODUCTION_READY_MARKER not in output:
            response["reason"] = "PRODUCTION_READY_NOT_CONFIRMED"
            return response
        response.update(status="READY", ready=True)
        return response
    except _ProductionFailure as exc:
        response["reason"] = exc.reason
        return response
