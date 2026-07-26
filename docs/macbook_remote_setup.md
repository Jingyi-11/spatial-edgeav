# MacBook Remote Development Setup

This checklist configures a MacBook as the travel machine while a Windows PC,
WSL2 Ubuntu, RK3576 board, and USB camera stay online remotely.

## Target Topology

```text
MacBook M1
  -> SSH/Tailscale
Windows PC
  -> WSL2 Ubuntu for training, ONNX export, RKNN conversion
  -> optional SSH jump host to RK3576
RK3576 + USB camera
  -> V4L2 capture, RKNN Runtime, streaming/service tests
```

## Current Verified Hosts

```text
MacBook Tailscale IP: 100.121.16.63
Windows Tailscale IP: 100.84.212.26
RK3576 Tailscale IP: 100.95.106.106
RK3576 LAN IP observed earlier: 192.168.1.199
```

Configured Mac SSH aliases:

```sshconfig
Host winbox
    HostName 100.84.212.26
    User HP
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3

Host wslbox
    HostName 100.84.212.26
    User jingyi
    Port 2222
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3

Host rk3576
    HostName 100.95.106.106
    User kickpi
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

## RK3576 Discovery

Detected after plugging the board into Ethernet:

```text
Host: kickpi
OS: Ubuntu 24.04.3 LTS, aarch64
Kernel: Linux 6.1.75
USB camera: Logitech HD Pro Webcam C920
Verified capture node: /dev/video73
```

The C920 also exposes a metadata node at `/dev/video74`. The board may expose
other ISP or virtual channels; use `v4l2-ctl --list-devices` before assuming a
node.

## MacBook Tools

Install daily tools:

```bash
brew install git openssh rsync wget tree cmake ninja pkg-config jq yq
brew install --cask tailscale visual-studio-code
```

Test GitHub SSH:

```bash
ssh -T git@github.com
```

## SSH Key Setup

Show the Mac public key:

```bash
cat ~/.ssh/id_ed25519.pub
```

Copy that single-line public key into:

```text
Windows OpenSSH:
C:\Users\<WindowsUser>\.ssh\authorized_keys

WSL2 Ubuntu:
/home/<WslUser>/.ssh/authorized_keys

RK3576:
/home/kickpi/.ssh/authorized_keys
```

Keep permissions tight:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/config ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
```

## Windows Setup Checklist

On Windows PowerShell as Administrator:

```powershell
Get-WindowsCapability -Online | ? Name -like 'OpenSSH.Server*'
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

Also check:

```text
[ ] Install and log in to Tailscale
[ ] Disable sleep while plugged in
[ ] Disable network adapter power saving
[ ] Keep Windows plugged in
[ ] Confirm Windows can reach RK3576 over LAN or Tailscale
```

## WSL2 SSH Setup

Inside WSL2 Ubuntu:

```bash
bash scripts/setup_wsl_ssh.sh
```

The verified WSL SSH path is:

```text
MacBook -> Tailscale Windows IP:2222 -> Windows portproxy -> WSL sshd
```

Windows portproxy was configured as:

```text
0.0.0.0:2222 -> WSL_IP:2222
Firewall rule: WSL-SSH-2222
```

If the WSL IP changes, rerun this in Administrator PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_windows_wsl_portproxy.ps1 -WslIp <WSL_IP>
```

## Connection Tests

Run from MacBook:

```bash
ssh winbox hostname
ssh wslbox 'uname -a'
ssh rk3576 'uname -a'
```

Before travelling, repeat the tests from a phone hotspot instead of home Wi-Fi.

## Project Sync

MacBook to WSL:

```bash
rsync -av --delete \
  --exclude .git \
  --exclude build \
  --exclude out \
  --exclude runs \
  --exclude data \
  ./ wslbox:~/spatial-edgeav/
```

MacBook to RK3576:

```bash
rsync -av --delete \
  --exclude .git \
  --exclude build \
  --exclude out \
  --exclude runs \
  --exclude data \
  ./ rk3576:~/spatial-edgeav/
```

Copy converted models:

```bash
scp models/*.rknn rk3576:~/spatial-edgeav/models/
```

## Remote Workflow

WSL2:

```bash
ssh wslbox
cd ~/spatial-edgeav
# training / ONNX export / RKNN conversion lives here later
scp models/*.rknn rk3576:~/spatial-edgeav/models/
```

RK3576:

```bash
ssh rk3576
cd ~/spatial-edgeav
make
bash scripts/rk3576_camera_smoke_test.sh
bash scripts/rk3576_stream_baseline.sh rk3576 /dev/video73 15 1280 720 30
```

## Travel Readiness Test

The setup is travel-ready when these work away from home Wi-Fi:

```bash
ssh winbox hostname
ssh wslbox 'python3 --version'
ssh rk3576 'ls /dev/video*'
bash scripts/wsl_yolo_smoke_test.sh
```
