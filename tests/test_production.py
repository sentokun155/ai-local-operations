from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from local_mcp.production import PRODUCTION_COMMAND, PRODUCTION_READY_MARKER, prepare_runtime


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args], check=True,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.stdout.strip()


class ProductionRuntimeTests(unittest.TestCase):
    branch = "gwi-0010-ai-local-operations"
    clone_url = "https://github.com/sentokun155/ai-local-operations.git"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="local-operations-production-")
        self.root = Path(self.temp.name)
        self.bare = self.root / "origin.git"
        subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(self.bare)], check=True, capture_output=True)
        self.seed = self.root / "seed"
        subprocess.run(["git", "clone", str(self.bare), str(self.seed)], check=True, capture_output=True)
        git(self.seed, "config", "user.name", "Production Fixture")
        git(self.seed, "config", "user.email", "production-fixture@example.invalid")
        (self.seed / "server.py").write_text("# fixture runtime\n", encoding="utf-8")
        git(self.seed, "add", "server.py")
        git(self.seed, "commit", "-m", "fixture runtime")
        git(self.seed, "push", "-u", "origin", "main")
        git(self.seed, "switch", "-c", self.branch)
        (self.seed / "candidate.txt").write_text("candidate v1\n", encoding="utf-8")
        git(self.seed, "add", "candidate.txt")
        git(self.seed, "commit", "-m", "candidate v1")
        git(self.seed, "push", "-u", "origin", self.branch)

        self.appdata = self.root / "appdata"
        self.profile_dir = self.appdata / "tunnel-client"
        self.profile_dir.mkdir(parents=True)
        self.profile = self.profile_dir / "local-operations.yaml"
        self.restart_script = self.root / "restart-prod.ps1"
        self.production = self.root / "ProdEnv"
        self.restart_commands: list[list[str]] = []
        self.environment = {"APPDATA": str(self.appdata), "CONTROL_PLANE_API_KEY": "test-only-key"}
        self.write_profile(command="uv run python C:/Dev/ProdEnv/server.py")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_profile(self, *, command: str, tunnel_id: str | None = "fixture-production-tunnel") -> None:
        id_line = f"tunnel_id: {tunnel_id}\n" if tunnel_id is not None else ""
        self.profile.write_text(
            id_line
            + "control_plane_api_key: env:CONTROL_PLANE_API_KEY\n"
            + f"command: {command}\n"
            + "listen_addr: 127.0.0.1:8080\n",
            encoding="utf-8",
        )

    def runner(self, command, **kwargs):
        if command and command[0].casefold() in {"pwsh", "pwsh.exe"}:
            self.restart_commands.append(list(command))
            return subprocess.CompletedProcess(command, 0, stdout=PRODUCTION_READY_MARKER + "\n", stderr="")
        if command[:5] == ["git", "-C", str(self.production), "remote", "get-url"]:
            return subprocess.CompletedProcess(command, 0, stdout=self.clone_url + "\n", stderr="")
        actual = list(command)
        if actual[:2] == ["git", "clone"]:
            actual[actual.index(self.clone_url)] = self.bare.as_uri()
            completed = subprocess.run(actual, **kwargs)
            if completed.returncode == 0:
                target = Path(actual[-1])
                git(target, "remote", "set-url", "origin", self.clone_url)
                git(target, "config", f"url.{self.bare.as_uri()}.insteadOf", self.clone_url)
            return completed
        return subprocess.run(actual, **kwargs)

    def create_production_clone(self, branch: str | None = None) -> None:
        subprocess.run(
            ["git", "clone", "--branch", branch or self.branch, str(self.bare), str(self.production)],
            check=True, capture_output=True,
        )
        git(self.production, "remote", "set-url", "origin", self.clone_url)
        git(self.production, "config", f"url.{self.bare.as_uri()}.insteadOf", self.clone_url)

    def prepare(self):
        return prepare_runtime(
            self.branch,
            production_root=self.production,
            restart_script=self.restart_script,
            runner=self.runner,
            environment=self.environment,
            powershell="pwsh.exe",
        )

    def test_absent_checkout_clones_requested_branch_updates_profile_and_checks_ready(self) -> None:
        result = self.prepare()
        self.assertEqual(result["status"], "READY", result)
        self.assertEqual(result["checkoutAction"], "CLONED")
        self.assertEqual(result["profileAction"], "UPDATED")
        self.assertTrue(result["tunnelRestarted"])
        self.assertTrue(result["ready"])
        self.assertEqual(git(self.production, "branch", "--show-current"), self.branch)
        self.assertIn(PRODUCTION_COMMAND, self.profile.read_text(encoding="utf-8"))
        self.assertEqual(self.restart_commands[0][-2:], ["-Branch", self.branch])

    def test_existing_checkout_fetches_and_fast_forwards_requested_branch(self) -> None:
        self.create_production_clone()
        (self.seed / "candidate.txt").write_text("candidate v2\n", encoding="utf-8")
        git(self.seed, "add", "candidate.txt")
        git(self.seed, "commit", "-m", "candidate v2")
        git(self.seed, "push", "origin", self.branch)
        expected = git(self.seed, "rev-parse", "HEAD")

        result = self.prepare()
        self.assertEqual(result["status"], "READY", result)
        self.assertEqual(result["checkoutAction"], "FAST_FORWARDED")
        self.assertEqual(git(self.production, "rev-parse", "HEAD"), expected)
        self.assertEqual(git(self.production, "branch", "--show-current"), self.branch)

    def test_main_single_branch_clone_can_fetch_and_switch_to_requested_branch(self) -> None:
        self.create_production_clone("main")

        result = self.prepare()
        self.assertEqual(result["status"], "READY", result)
        self.assertEqual(result["checkoutAction"], "BRANCH_SWITCHED")
        self.assertEqual(git(self.production, "branch", "--show-current"), self.branch)

    def test_dirty_production_checkout_is_held_and_preserved(self) -> None:
        self.create_production_clone()
        marker = self.production / "keep-local.txt"
        marker.write_text("preserve this", encoding="utf-8")

        result = self.prepare()
        self.assertEqual(result["reason"], "PRODUCTION_CHECKOUT_DIRTY")
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve this")
        self.assertEqual(self.restart_commands, [])
        self.assertIn("uv run python", self.profile.read_text(encoding="utf-8"))

    def test_missing_production_profile_or_tunnel_id_returns_that_deficiency(self) -> None:
        self.profile.unlink()
        missing_profile = self.prepare()
        self.assertEqual(missing_profile["reason"], "PRODUCTION_PROFILE_MISSING")

        self.write_profile(command="uv run python server.py", tunnel_id=None)
        missing_id = self.prepare()
        self.assertEqual(missing_id["reason"], "PRODUCTION_TUNNEL_ID_MISSING")
        self.assertEqual(self.restart_commands, [])


if __name__ == "__main__":
    unittest.main()
