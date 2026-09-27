. "$PSScriptRoot\_runtime-common.ps1"
Assert-RequiredCommand "git"
Assert-RequiredCommand "uv"
Assert-RequiredCommand "tunnel-client.exe"
Import-RuntimeApiKey

# 各環境を独立して処理します。一方の失敗で他方を停止しません。
$prodBranch = & git -C $script:ProdRoot branch --show-current 2>$null
$prodOk = $false
if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace([string]$prodBranch)) {
    $prodOk = Start-OneRuntime -Name "Production" -Root $script:ProdRoot -Profile $script:ProdProfile -Port $script:ProdPort -ExpectedBranch ([string]$prodBranch)
} else {
    Write-Error "[Production] branchを確認できません。" -ErrorAction Continue
}
$devBranch = & git -C $script:DevRoot branch --show-current 2>$null
$devOk = $false
if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace([string]$devBranch)) {
    $devOk = Start-OneRuntime -Name "Development" -Root $script:DevRoot -Profile $script:DevProfile -Port $script:DevPort -ExpectedBranch ([string]$devBranch)
} else {
    Write-Error "[Development] branchを確認できません。" -ErrorAction Continue
}
if (-not ($prodOk -and $devOk)) { exit 1 }
