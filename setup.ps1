param(
    [string]$DevTunnelId,
    [string]$ProdTunnelId,
    [switch]$ConfigureProfiles,
    [switch]$ReplaceExistingProfiles
)
& "$PSScriptRoot\scripts\setup.ps1" -DevTunnelId $DevTunnelId -ProdTunnelId $ProdTunnelId -ConfigureProfiles:$ConfigureProfiles -ReplaceExistingProfiles:$ReplaceExistingProfiles
exit $LASTEXITCODE
