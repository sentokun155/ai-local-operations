param(
    [string]$DevTunnelId,
    [string]$ProdTunnelId,
    [switch]$ConfigureProfiles,
    [switch]$ReplaceExistingProfiles
)

. "$PSScriptRoot\_runtime-common.ps1"
Assert-RequiredCommand "git"
Assert-RequiredCommand "uv"
Assert-RequiredCommand "codex"
Assert-RequiredCommand "tunnel-client.exe"

if ($script:RuntimeRepositoryRoot -ne $script:DevRoot) {
    throw "SetupはCanonical sourceを配置したC:\Dev\DevEnvから実行してください。"
}
if ((Get-RepositoryIdentity $script:DevRoot) -ne "sentokun155/ai-local-operations") { throw "Development checkout identityが一致しません。" }
if ((Get-RepositoryIdentity $script:ProdRoot) -ne "sentokun155/ai-local-operations") { throw "Production checkout identityが一致しません。" }
if (-not (Test-Path (Join-Path $script:DevRoot "pyproject.toml")) -or -not (Test-Path (Join-Path $script:DevRoot "server.py"))) {
    throw "Development runtimeにpyproject.tomlまたはserver.pyがありません。"
}
if (-not (Test-Path (Join-Path $script:ProdRoot ".git"))) { throw "Production runtimeがGit checkoutではありません。" }

$key = [Environment]::GetEnvironmentVariable("CONTROL_PLANE_API_KEY", "Process")
if ([string]::IsNullOrWhiteSpace($key)) { $key = [Environment]::GetEnvironmentVariable("CONTROL_PLANE_API_KEY", "User") }
if ([string]::IsNullOrWhiteSpace($key)) { throw "CONTROL_PLANE_API_KEY が設定されていません。値は表示しません。" }
$env:CONTROL_PLANE_API_KEY = $key

& uv --directory $script:DevRoot run --locked python -c "import mcp; print('Development MCP dependencies: PASS')"
if ($LASTEXITCODE -ne 0) { throw "Development MCP dependenciesを確認できません。" }
if (-not (Test-Path (Join-Path $script:ProdRoot "server.py"))) {
    Write-Warning "Production checkoutにLocal Operations runtime sourceがありません。起動前に使用するbranchを確認してください。"
}

if ($ConfigureProfiles) {
    if ([string]::IsNullOrWhiteSpace($DevTunnelId) -or [string]::IsNullOrWhiteSpace($ProdTunnelId)) {
        throw "ConfigureProfilesにはDevTunnelIdとProdTunnelIdが必要です。"
    }
    if ($DevTunnelId -eq $ProdTunnelId) { throw "DevelopmentとProductionには異なるTunnel IDが必要です。" }

    foreach ($item in @(
        @{Root=$script:DevRoot; Profile=$script:DevProfile; Id=$DevTunnelId; Port=$script:DevPort},
        @{Root=$script:ProdRoot; Profile=$script:ProdProfile; Id=$ProdTunnelId; Port=$script:ProdPort}
    )) {
        $profilePath = Join-Path $env:APPDATA "tunnel-client/$($item.Profile).yaml"
        $expectedCommand = "uv --directory `"$($item.Root)`" run --locked python server.py"
        $expectedHealthAddress = "127.0.0.1:$($item.Port)"
        if (Test-Path -LiteralPath $profilePath -PathType Leaf) {
            $content = Get-Content -LiteralPath $profilePath -Raw
            $tunnelMatch = [Regex]::Match($content, '(?im)^\s*tunnel_id:\s*["'']?([^"''\s#]+)')
            $healthAddress = [Regex]::Match($content, '(?im)^\s*listen_addr:\s*["'']?([^"''\s#]+)').Groups[1].Value
            $isCurrent = (
                (Test-ProfileRuntimeCommand -Content $content -ExpectedCommand $expectedCommand) -and
                $healthAddress -eq $expectedHealthAddress -and
                $tunnelMatch.Success -and $tunnelMatch.Groups[1].Value -eq $item.Id -and
                $content.Contains("env:CONTROL_PLANE_API_KEY")
            )
            if ($isCurrent) { Write-Host "[$($item.Profile)] profileは設定済みです。"; continue }
            if (-not $ReplaceExistingProfiles) { throw "[$($item.Profile)] profileが既存設定と異なります。安全のため上書きしません。必要ならReplaceExistingProfilesを明示してください。" }
        }
        $initArgs = @(
            "init", "--sample", "sample_mcp_stdio_local", "--profile", $item.Profile,
            "--tunnel-id", $item.Id, "--health-listen-addr", "127.0.0.1:$($item.Port)",
            "--control-plane-api-key-ref", "env:CONTROL_PLANE_API_KEY", "--mcp-command", $expectedCommand
        )
        if ($ReplaceExistingProfiles) { $initArgs += "--force" }
        & $script:TunnelClient @initArgs
        if ($LASTEXITCODE -ne 0) { throw "[$($item.Profile)] profileを設定できません。" }
    }
}

$devProfilePath = Join-Path $env:APPDATA "tunnel-client/$($script:DevProfile).yaml"
$prodProfilePath = Join-Path $env:APPDATA "tunnel-client/$($script:ProdProfile).yaml"
if (-not (Test-Path $devProfilePath)) { Write-Warning "Development profileがありません。DevTunnelIdを確認してsetup.ps1 -ConfigureProfilesを実行してください。" }
if (-not (Test-Path $prodProfilePath)) { Write-Warning "Production profileがありません。ProdTunnelIdを確認してsetup.ps1 -ConfigureProfilesを実行してください。" }
Write-Host "Runtime checkout / tools / credential referenceを確認しました。Tunnelは起動していません。"
