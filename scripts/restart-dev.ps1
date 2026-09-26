. "$PSScriptRoot\_runtime-common.ps1"
Assert-RequiredCommand "git"
Assert-RequiredCommand "uv"
Assert-RequiredCommand "tunnel-client.exe"
Import-RuntimeApiKey
$branch = & git -C $script:DevRoot branch --show-current
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$branch)) { throw "Development branchを確認できません。" }
$null = Assert-ProfileRuntime $script:DevProfile $script:DevRoot
Assert-DistinctTunnelProfiles
$null = Sync-RuntimeBranch -Root $script:DevRoot -ExpectedBranch ([string]$branch)
Assert-NoWorkerLeases $script:DevRoot
Stop-TunnelProfile $script:DevProfile
Start-TunnelProfile $script:DevProfile
Show-RuntimeHealth "Development" $script:DevPort
