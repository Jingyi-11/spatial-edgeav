param(
    [string]$WslIp = "172.17.123.167",
    [int]$Port = 2222
)

Write-Host "Configuring Windows portproxy: 0.0.0.0:$Port -> $WslIp:$Port"

netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$Port 2>$null
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$Port connectaddress=$WslIp connectport=$Port

if (-not (Get-NetFirewallRule -Name WSL-SSH-2222 -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule `
        -Name WSL-SSH-2222 `
        -DisplayName "WSL SSH 2222" `
        -Enabled True `
        -Direction Inbound `
        -Protocol TCP `
        -Action Allow `
        -LocalPort $Port
} else {
    Set-NetFirewallRule -Name WSL-SSH-2222 -Enabled True
}

netsh interface portproxy show all

