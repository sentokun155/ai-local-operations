Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:RuntimeRepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script:DevRoot = "C:\Dev\DevEnv"
$script:ProdRoot = "C:\Dev\ProdEnv"
$script:DevProfile = "local-operations-dev"
$script:ProdProfile = "local-operations"
$script:DevPort = 8081
$script:ProdPort = 8080
$script:TunnelClient = "tunnel-client.exe"

function Assert-RequiredCommand([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name が PATH 上に見つかりません。"
    }
}

function Import-RuntimeApiKey {
    $key = [Environment]::GetEnvironmentVariable("CONTROL_PLANE_API_KEY", "Process")
    if ([string]::IsNullOrWhiteSpace($key)) {
        $key = [Environment]::GetEnvironmentVariable("CONTROL_PLANE_API_KEY", "User")
    }
    if ([string]::IsNullOrWhiteSpace($key)) {
        throw "CONTROL_PLANE_API_KEY がありません。Windows User environment variableへ設定してください。値は表示しません。"
    }
    $env:CONTROL_PLANE_API_KEY = $key
}

function Get-ConfiguredTunnelId([string]$Profile) {
    $path = Join-Path $env:APPDATA "tunnel-client/$Profile.yaml"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "[$Profile] profileがありません。setup.ps1で作成してください。" }
    $content = Get-Content -LiteralPath $path -Raw
    $id = [Regex]::Match($content, '(?im)^\s*tunnel_id:\s*["'']?([^"''\s#]+)')
    if (-not $id.Success) { throw "[$Profile] Tunnel IDを確認できません。" }
    if (-not $content.Contains("env:CONTROL_PLANE_API_KEY")) { throw "[$Profile] credential referenceが安全な環境変数参照ではありません。" }
    return $id.Groups[1].Value
}

function Normalize-ProfileRuntimeCommand([string]$Command) {
    $value = $Command.Trim()
    if ($value.StartsWith('"') -and $value.EndsWith('"')) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    $value = $value.Replace('\\', '\').Replace('\"', '"')
    $value = $value.Replace('\', '/').Replace('"', '').Replace("'", '')
    $value = [Regex]::Replace($value, '\s+', ' ').Trim()
    return $value.ToLowerInvariant()
}

function Test-ProfileRuntimeCommand([string]$Content, [string]$ExpectedCommand) {
    $expected = Normalize-ProfileRuntimeCommand $ExpectedCommand
    $commandLines = [Regex]::Matches($Content, '(?im)^\s*command:\s*(?<value>.*?)\s*(?:#.*)?$')
    foreach ($line in $commandLines) {
        if ((Normalize-ProfileRuntimeCommand $line.Groups['value'].Value) -eq $expected) { return $true }
    }
    return $false
}

function Assert-ProfileRuntime([string]$Profile, [string]$Root) {
    $id = Get-ConfiguredTunnelId $Profile
    $path = Join-Path $env:APPDATA "tunnel-client/$Profile.yaml"
    $content = Get-Content -LiteralPath $path -Raw
    $expectedCommand = "uv --directory `"$Root`" run --locked python server.py"
    if (-not (Test-ProfileRuntimeCommand -Content $content -ExpectedCommand $expectedCommand)) { throw "[$Profile] MCP commandが対象runtime checkoutを指していません。" }
    if ($Root -eq $script:DevRoot) { $expectedHealthAddress = "127.0.0.1:$($script:DevPort)" }
    elseif ($Root -eq $script:ProdRoot) { $expectedHealthAddress = "127.0.0.1:$($script:ProdPort)" }
    else { throw "[$Profile] 未登録runtime rootです。" }
    $healthAddress = [Regex]::Match($content, '(?im)^\s*listen_addr:\s*["'']?([^"''\s#]+)').Groups[1].Value
    if ($healthAddress -ne $expectedHealthAddress) { throw "[$Profile] health listenerは$expectedHealthAddressである必要があります。" }
    return $id
}

function Assert-DistinctTunnelProfiles {
    $devId = Get-ConfiguredTunnelId $script:DevProfile
    $prodId = Get-ConfiguredTunnelId $script:ProdProfile
    if ($devId -eq $prodId) { throw "Development / Production profileが同じTunnel IDを使っています。起動を止めました。" }
}

function Get-RepositoryIdentity([string]$Root) {
    $remote = & git -C $Root remote get-url origin 2>$null
    if ($LASTEXITCODE -ne 0) { throw "origin remoteを確認できません。" }
    $value = [string]$remote
    if ($value -match '^https://github\.com/([^/]+/[^/]+?)(?:\.git)?$') { return $Matches[1].ToLowerInvariant() }
    if ($value -match '^(?:[^@]+@)?github\.com:([^/]+/[^/]+?)(?:\.git)?$') { return $Matches[1].ToLowerInvariant() }
    throw "origin remoteのRepository identityを安全に確認できません。"
}

function Assert-RepositoryRoot([string]$Root, [string]$ExpectedBranch, [switch]$RequireClean) {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { throw "runtime checkoutがありません: $Root" }
    if ((Get-RepositoryIdentity $Root) -ne "sentokun155/ai-local-operations") { throw "runtime checkoutのorigin identityが一致しません。" }
    $branch = & git -C $Root branch --show-current
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$branch)) { throw "runtime checkoutのbranchを確認できません。" }
    if ($ExpectedBranch -and [string]$branch -ne $ExpectedBranch) { throw "runtime branchが期待値と異なります。" }
    if ($RequireClean) {
        $changes = & git -C $Root status --porcelain=v1 --untracked-files=all
        if ($LASTEXITCODE -ne 0 -or $changes) { throw "runtime checkoutにlocal変更があります。内容を保持したまま診断してください。" }
    }
    return [string]$branch
}

function Sync-RuntimeBranch([string]$Root, [string]$ExpectedBranch, [switch]$RequireClean) {
    $branch = Assert-RepositoryRoot -Root $Root -ExpectedBranch $ExpectedBranch -RequireClean:$RequireClean
    & git -C $Root fetch origin $branch
    if ($LASTEXITCODE -ne 0) { throw "origin branchを取得できません。" }
    $counts = & git -C $Root rev-list --left-right --count "HEAD...origin/$branch"
    if ($LASTEXITCODE -ne 0) { throw "runtime branchの差分を確認できません。" }
    $parts = ([string]$counts).Trim() -split '\s+'
    $ahead = [int]$parts[0]
    $behind = [int]$parts[1]
    if ($ahead -gt 0 -and $behind -gt 0) { throw "runtime branchがremoteと分岐しています。更新を止めました。" }
    if ($Root -eq $script:ProdRoot -and $ahead -gt 0) { throw "Production mainにremote未反映commitがあります。更新を止めました。" }
    if ($behind -gt 0) {
        & git -C $Root merge --ff-only "origin/$branch"
        if ($LASTEXITCODE -ne 0) { throw "runtime checkoutをfast-forwardできません。" }
    }
    return $branch
}

function Assert-NoWorkerLeases([string]$Root) {
    $admin = Join-Path $Root "src/local_mcp/admin.py"
    if (-not (Test-Path -LiteralPath $admin -PathType Leaf)) { return }
    & uv --directory $Root run --locked python -m local_mcp.admin check-no-leases
    if ($LASTEXITCODE -ne 0) { throw "Worker leaseが残っているため、Tunnelを再起動しません。" }
}

function Get-ProfileProcesses([string]$Profile) {
    $escaped = [Regex]::Escape($Profile)
    $pattern = "(?i)(?:^|\s)--profile(?:=|\s+)[`"']?$escaped[`"']?(?:\s|$)"
    return @(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine -match $pattern })
}

function Stop-TunnelProfile([string]$Profile) {
    $processes = Get-ProfileProcesses $Profile
    foreach ($proc in $processes) {
        & taskkill.exe /PID $proc.ProcessId /T 2>$null | Out-Null
        Start-Sleep -Milliseconds 750
        if (Get-Process -Id $proc.ProcessId -ErrorAction SilentlyContinue) {
            & taskkill.exe /PID $proc.ProcessId /T /F 2>$null | Out-Null
            Start-Sleep -Milliseconds 250
        }
        if (Get-Process -Id $proc.ProcessId -ErrorAction SilentlyContinue) {
            throw "[$Profile] tunnel-clientを安全に停止できませんでした。"
        }
    }
    Start-Sleep -Milliseconds 500
}

function Start-TunnelProfile([string]$Profile) {
    $existing = @(Get-ProfileProcesses $Profile)
    if ($existing.Count -gt 0) {
        Write-Host "[$Profile] 起動済みです。"
        return
    }
    Start-Process -FilePath $script:TunnelClient -ArgumentList @("run", "--profile", $Profile) -WindowStyle Hidden | Out-Null
}

function Wait-TunnelReady([int]$Port, [int]$TimeoutSeconds = 25) {
    $watch = [Diagnostics.Stopwatch]::StartNew()
    while ($watch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/readyz" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($response.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Show-RuntimeHealth([string]$Name, [int]$Port, [string]$Profile) {
    $base = "http://127.0.0.1:$Port"
    if (-not (Wait-TunnelReady $Port)) { throw "[$Name] READYを確認できません。診断UI: $base/ui" }
    Start-Sleep -Seconds 2
    $readyAgain = Wait-TunnelReady $Port -TimeoutSeconds 2
    $profileProcesses = @(Get-ProfileProcesses $Profile)
    if (-not $readyAgain -or $profileProcesses.Count -eq 0) {
        throw "[$Name] READY_STABILITY_FAILED: READYが安定しません。Tunnel profileとMCP commandを確認してください。"
    }
    Write-Host "[$Name] READY: $base/ui"
}

function Start-OneRuntime([string]$Name, [string]$Root, [string]$Profile, [int]$Port, [string]$ExpectedBranch, [switch]$RequireCleanCheckout) {
    try {
        if ($Profile -eq $script:DevProfile) { $null = Assert-ProfileRuntime $Profile $script:DevRoot }
        if ($Profile -eq $script:ProdProfile) { $null = Assert-ProfileRuntime $Profile $script:ProdRoot }
        Assert-DistinctTunnelProfiles
        $null = Sync-RuntimeBranch -Root $Root -ExpectedBranch $ExpectedBranch -RequireClean:$RequireCleanCheckout
        Start-TunnelProfile $Profile
        Show-RuntimeHealth $Name $Port $Profile
        return $true
    } catch {
        Write-Error "[$Name] $($_.Exception.Message)" -ErrorAction Continue
        return $false
    }
}
