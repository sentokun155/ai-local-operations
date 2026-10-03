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
        common = (SCRIPTS / "_runtime-common.ps1").read_text(encoding="utf-8")
        start_all = (SCRIPTS / "start-all.ps1").read_text(encoding="utf-8")
        self.assertIn("$script:DevRoot", dev)
        self.assertIn("$script:DevProfile", dev)
        self.assertIn("Sync-RuntimeBranch", dev)
        self.assertNotIn("-RequireClean", dev)
        self.assertNotIn("$script:ProdRoot", dev)
        self.assertNotIn("$script:ProdProfile", dev)
        self.assertIn("$script:ProdRoot", prod)
        self.assertIn("$script:ProdProfile", prod)
        self.assertIn("$Branch", prod)
        self.assertNotIn('"main"', prod)
        self.assertNotIn("-RequireClean", prod)
        self.assertNotIn("Assert-NoWorkerLeases", prod)
        self.assertNotIn("-RequireCleanCheckout", start_all)
        self.assertIn("-RequireClean:$RequireCleanCheckout", common)
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
    def test_profile_command_validator_accepts_windows_path_spellings(self):
        command = r'''
$ErrorActionPreference = "Stop"
. "./scripts/_runtime-common.ps1"
$expected = 'uv --directory "C:\Dev\DevEnv" run --locked python server.py'
$serialized = $expected.Replace('\', '\\').Replace('"', '\"')
$yaml = 'command: "' + $serialized + '"'
if (-not (Test-ProfileRuntimeCommand -Content $yaml -ExpectedCommand $expected)) { exit 1 }
$forwardSlash = 'command: "uv --directory C:/Dev/DevEnv run --locked python server.py"'
if (-not (Test-ProfileRuntimeCommand -Content $forwardSlash -ExpectedCommand $expected)) { exit 2 }
$unquotedPath = 'command: "uv --directory C:\\Dev\\DevEnv run --locked python server.py"'
if (-not (Test-ProfileRuntimeCommand -Content $unquotedPath -ExpectedCommand $expected)) { exit 3 }
$wrong = $expected.Replace('DevEnv', 'ProdEnv')
if (Test-ProfileRuntimeCommand -Content $yaml -ExpectedCommand $wrong) { exit 4 }
if (Test-ProfileRuntimeCommand -Content 'comment: command: uv --directory C:/Dev/DevEnv run --locked python server.py' -ExpectedCommand $expected) { exit 5 }
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
    def test_stop_profile_force_stops_only_a_process_tree_that_resists_graceful_stop(self):
        command = r'''
$ErrorActionPreference = "Stop"
. "./scripts/_runtime-common.ps1"
$script:running = $true
$script:killCalls = @()
function Get-ProfileProcesses([string]$Profile) {
    if ($Profile -ne 'local-operations-dev') { exit 1 }
    return @([pscustomobject]@{ProcessId=7312})
}
function taskkill.exe([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments) {
    $script:killCalls += ,($Arguments -join ' ')
    if ($Arguments -contains '/F') { $script:running = $false; $global:LASTEXITCODE = 0 }
    else { $global:LASTEXITCODE = 128 }
}
function Get-Process([int]$Id, [string]$ErrorAction) {
    if ($script:running) { return [pscustomobject]@{Id=$Id} }
    return $null
}
function Start-Sleep([int]$Seconds, [int]$Milliseconds) { }
Stop-TunnelProfile 'local-operations-dev'
if ($script:killCalls.Count -ne 2) { exit 2 }
if ($script:killCalls[0] -notmatch '/PID 7312 /T' -or $script:killCalls[0] -match '/F') { exit 3 }
if ($script:killCalls[1] -notmatch '/PID 7312 /T /F') { exit 4 }
if ($script:running) { exit 5 }
'''
        subprocess.run(
            ["pwsh", "-NoProfile", "-Command", command],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_runtime_health_rejects_a_transient_ready_listener(self):
        command = r'''
$ErrorActionPreference = "Stop"
. "./scripts/_runtime-common.ps1"
$script:healthCalls = 0
function Wait-TunnelReady([int]$Port, [int]$TimeoutSeconds = 25) {
    $script:healthCalls++
    return $script:healthCalls -eq 1
}
function Get-ProfileProcesses([string]$Profile) { return @([pscustomobject]@{ProcessId=1}) }
function Start-Sleep([int]$Seconds) { }
$script:correctFailure = $false
try { Show-RuntimeHealth 'Development' 8081 'local-operations-dev' }
catch { $script:correctFailure = $_.Exception.Message.Contains('READY_STABILITY_FAILED') }
if (-not $script:correctFailure) { exit 1 }
if ($script:healthCalls -ne 2) { exit 2 }
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
