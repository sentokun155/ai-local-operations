from __future__ import annotations

from pathlib import Path
import os
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class RuntimeScriptBoundaryTests(unittest.TestCase):
    def test_environment_restart_entrypoints_are_separate(self):
        dev = (SCRIPTS / "restart-dev.ps1").read_text(encoding="utf-8")
        prod = (SCRIPTS / "restart-prod.ps1").read_text(encoding="utf-8")
        self.assertIn("$script:DevRoot", dev)
        self.assertIn("$script:DevProfile", dev)
        self.assertNotIn("$script:ProdRoot", dev)
        self.assertNotIn("$script:ProdProfile", dev)
        self.assertIn("$script:ProdRoot", prod)
        self.assertIn("$script:ProdProfile", prod)
        self.assertIn('"main"', prod)
        self.assertNotIn("$script:DevRoot", prod)
        self.assertNotIn("$script:DevProfile", prod)

    def test_runtime_scripts_never_force_discard_or_pass_key_as_argument(self):
        common = (SCRIPTS / "_runtime-common.ps1").read_text(encoding="utf-8")
        setup = (SCRIPTS / "setup.ps1").read_text(encoding="utf-8")
        scripts = "\n".join(path.read_text(encoding="utf-8") for path in SCRIPTS.glob("*.ps1"))
        self.assertNotRegex(scripts, r"(?i)reset\s+--hard|clean\s+-fdx|push\s+--force")
        self.assertIn('GetEnvironmentVariable("CONTROL_PLANE_API_KEY", "User")', setup)
        self.assertIn('"env:CONTROL_PLANE_API_KEY"', setup)
        self.assertNotRegex(common, r"(?i)-ArgumentList[^\n]*CONTROL_PLANE_API_KEY")

    def test_runtime_restart_guard_holds_when_any_worker_is_leased(self):
        with tempfile.TemporaryDirectory(prefix="local-operations-runtime-guard-") as temp:
            state = Path(temp) / "LocalOperations" / "dispatch-ledger.sqlite3"
            state.parent.mkdir()
            connection = sqlite3.connect(state)
            try:
                connection.execute("CREATE TABLE workers(worker_id TEXT, state TEXT)")
                connection.execute("INSERT INTO workers VALUES('worker-01', 'LEASED')")
                connection.commit()
            finally:
                connection.close()
            environment = os.environ.copy()
            environment["LOCALAPPDATA"] = temp
            result = subprocess.run(
                [sys.executable, "-m", "local_mcp.admin", "check-no-leases"],
                cwd=ROOT, env=environment, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("WORKERS_LEASED", result.stdout)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_profile_command_validator_accepts_tunnel_client_yaml_escaping(self):
        command = r'''
$ErrorActionPreference = "Stop"
. "./scripts/_runtime-common.ps1"
$expected = 'uv --directory "C:\Dev\DevEnv" run --locked python server.py'
$serialized = $expected.Replace('\', '\\').Replace('"', '\"')
$yaml = 'command: "' + $serialized + '"'
if (-not (Test-ProfileRuntimeCommand -Content $yaml -ExpectedCommand $expected)) { exit 1 }
$wrong = $expected.Replace('DevEnv', 'ProdEnv')
if (Test-ProfileRuntimeCommand -Content $yaml -ExpectedCommand $wrong) { exit 2 }
'''
        subprocess.run(
            ["pwsh", "-NoProfile", "-Command", command],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_start_profile_handles_no_existing_process_under_strict_mode(self):
        command = r'''
$ErrorActionPreference = "Stop"
. "./scripts/_runtime-common.ps1"
function Get-ProfileProcesses([string]$Profile) { return @() }
function Start-Process([string]$FilePath, [string[]]$ArgumentList, [string]$WindowStyle) {
    if ($WindowStyle -ne 'Hidden' -or $ArgumentList -notcontains '--profile') { exit 1 }
    $script:started = $true
}
$script:started = $false
Start-TunnelProfile 'probe'
if (-not $script:started) { exit 2 }
'''
        subprocess.run(
            ["pwsh", "-NoProfile", "-Command", command],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_all_repository_backed_scripts_parse(self):
        files = [*SCRIPTS.glob("*.ps1"), ROOT / "setup.ps1", ROOT / "start-all.ps1", ROOT / "restart-dev.ps1", ROOT / "restart-prod.ps1"]
        for path in files:
            command = (
                "$tokens=$null;$errors=$null;"
                f"[System.Management.Automation.Language.Parser]::ParseFile('{path.as_posix()}',[ref]$tokens,[ref]$errors)|Out-Null;"
                "if($errors.Count){$errors|ForEach-Object{Write-Error $_.Message};exit 1}"
            )
            subprocess.run(["pwsh", "-NoProfile", "-Command", command], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
