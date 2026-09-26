. "$PSScriptRoot\_runtime-common.ps1"
Assert-RequiredCommand "git"
Assert-RequiredCommand "uv"
Assert-RequiredCommand "tunnel-client.exe"
Import-RuntimeApiKey
$null = Assert-ProfileRuntime $script:ProdProfile $script:ProdRoot
Assert-DistinctTunnelProfiles
$null = Assert-RepositoryRoot -Root $script:ProdRoot -ExpectedBranch "main" -RequireClean
$null = Sync-RuntimeBranch -Root $script:ProdRoot -ExpectedBranch "main"
Assert-NoWorkerLeases $script:ProdRoot
Stop-TunnelProfile $script:ProdProfile
Start-TunnelProfile $script:ProdProfile
Show-RuntimeHealth "Production" $script:ProdPort $script:ProdProfile
