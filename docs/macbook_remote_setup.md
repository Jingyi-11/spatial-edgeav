# MacBook Remote Setup for EdgeAV/RKNN

This checklist turns the MacBook into the travel machine for this project:

```text
MacBook
  -> SSH/Tailscale
Windows PC
  -> WSL2 Ubuntu for training, ONNX export, RKNN conversion
  -> optional SSH jump host to RK3576
RK3576 + USB camera
  -> V4L2 capture, RKNN Runtime, streaming/service tests
```

## 1. Current MacBook Status

Checked on this MacBook:

```text
macOS: 15.7.3, Apple Silicon arm64
Available: Homebrew, ssh, rsync, git, cmake, ninja, jq
Missing/unfinished: Tailscale app, VS Code CLI
SSH key: ~/.ssh/id_ed25519 exists
SSH config: currently only has github.com
```

Tailscale installation was attempted with Homebrew, but macOS needs an admin
password for the package installer. Run this manually in Terminal:

```bash
brew install --cask tailscale
```

Then open Tailscale from Applications, log in, and enable it at login.

## 2. Use the Existing SSH Key

This Mac already has:

```text
~/.ssh/id_ed25519
~/.ssh/id_ed25519.pub
```

Show the public key:

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

If you want a dedicated project key instead of reusing the existing one:

```bash
ssh-keygen -t ed25519 -C "macbook-edgeav" -f ~/.ssh/id_ed25519_edgeav
ssh-add --apple-use-keychain ~/.ssh/id_ed25519_edgeav
cat ~/.ssh/id_ed25519_edgeav.pub
```

## 3. Add SSH Host Shortcuts

After you know the Windows Tailscale name/IP, Windows username, WSL username,
and RK3576 IP, append this to `~/.ssh/config`:

```sshconfig
Host winbox
    HostName <windows_tailscale_ip_or_hostname>
    User <windows_user>
    IdentityFile ~/.ssh/id_ed25519
    AddKeysToAgent yes
    UseKeychain yes
    ServerAliveInterval 30
    ServerAliveCountMax 3

Host wsl
    HostName <windows_tailscale_ip_or_hostname>
    User <wsl_user>
    Port 2222
    IdentityFile ~/.ssh/id_ed25519
    AddKeysToAgent yes
    UseKeychain yes
    ServerAliveInterval 30
    ServerAliveCountMax 3

Host rk3576
    HostName <rk3576_lan_or_tailscale_ip>
    User kickpi
    IdentityFile ~/.ssh/id_ed25519
    AddKeysToAgent yes
    UseKeychain yes
    ServerAliveInterval 30
    ServerAliveCountMax 3

Host rk3576-via-win
    HostName <rk3576_lan_ip>
    User kickpi
    IdentityFile ~/.ssh/id_ed25519
    ProxyJump winbox
    AddKeysToAgent yes
    UseKeychain yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

Keep permissions tight:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/config ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
```

Or let the project script update the marked block automatically:

```bash
WIN_HOST=100.x.y.z \
WIN_USER=<windows_user> \
WSL_USER=<wsl_user> \
RK3576_HOST=192.168.1.88 \
./scripts/configure_mac_ssh_hosts.sh
```

Optional variables:

```bash
WSL_PORT=2222
RK3576_USER=kickpi
SSH_KEY=~/.ssh/id_ed25519
```

## 4. Windows Setup Checklist

On Windows, do this before travelling:

```powershell
Get-WindowsCapability -Online | ? Name -like 'OpenSSH.Server*'
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

Also:

```text
[ ] Install and log in to Tailscale
[ ] Disable sleep while plugged in
[ ] Disable network adapter power saving
[ ] Keep Windows plugged in
[ ] Confirm Windows can reach RK3576 over LAN
```

## 5. WSL2 SSH Setup

Inside WSL2 Ubuntu:

```bash
sudo apt update
sudo apt install -y openssh-server git rsync build-essential cmake ninja-build python3 python3-pip
sudo mkdir -p /run/sshd
sudo sed -i 's/^#Port 22/Port 2222/' /etc/ssh/sshd_config
sudo service ssh restart
```

Put the Mac public key in:

```bash
mkdir -p ~/.ssh
nano ~/.ssh/authorized_keys
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

## 6. Project Sync

From the MacBook project directory:

```bash
rsync -av --delete \
  --exclude build \
  --exclude out \
  --exclude data \
  ./ wsl:~/linux_camera/
```

Copy to RK3576:

```bash
rsync -av --delete \
  --exclude build \
  --exclude out \
  --exclude training \
  ./ rk3576:~/linux_camera/
```

Copy converted models:

```bash
scp models/*.rknn rk3576:~/linux_camera/models/
```

## 7. Connection Tests

Run these from MacBook:

```bash
ssh winbox hostname
ssh wsl 'uname -a'
ssh rk3576 'uname -a'
ssh rk3576-via-win 'ls /dev/video*'
```

Before travelling, repeat those tests from a phone hotspot instead of home Wi-Fi.

## 8. Project Workflow

MacBook:

```bash
make clean
make
make rk3567-sim
rsync -av --delete --exclude build --exclude out ./ wsl:~/linux_camera/
```

WSL2:

```bash
cd ~/linux_camera
# training / ONNX export / RKNN conversion lives here later
scp models/*.rknn rk3576:~/linux_camera/models/
```

RK3576:

```bash
cd ~/linux_camera
make
./scripts/01_rk3567_probe_media.sh /dev/video0
./scripts/02_rk3567_capture_nv12.sh /dev/video0
```
