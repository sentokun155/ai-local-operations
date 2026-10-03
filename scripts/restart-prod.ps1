param([string]$Branch)

. "$PSScriptRoot\_runtime-common.ps1"
Assert-RequiredCommand "git"
Assert-RequiredCommand "uv"
Assert-RequiredCommand "tunnel-client.exe"
Import-RuntimeApiKey
$null = Assert-ProfileRuntime $script:ProdProfile $script:ProdRoot
Assert-DistinctTunnelProfiles
if ([string]::IsNullOrWhiteSpace($Branch)) {
    $Branch = & git -C $script:ProdRoot branch --show-current
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$Branch)) { throw "Production branchを確認できません。" }
}
$null = Sync-RuntimeBranch -Root $script:ProdRoot -ExpectedBranch ([string]$Branch)
Stop-TunnelProfile $script:ProdProfile
Start-TunnelProfile $script:ProdProfile
Show-RuntimeHealth "Production" $script:ProdPort $script:ProdProfile
Write-Output "PRODUCTION_READY=http://127.0.0.1:$($script:ProdPort)/readyz"
