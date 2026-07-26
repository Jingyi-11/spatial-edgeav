# MacBook Remote Development Setup

This checklist configures a MacBook as the only travel machine while a Windows
PC, WSL2 Ubuntu, RK3576 board, and USB camera stay online remotely.

## Target Topology

```text
MacBook M1
  -> SSH/Tailscale
Windows PC
  -> WSL2 Ubuntu for training, ONNX export, RKNN conversion
  -> SSH jump host to RK3576 if needed
RK3576 + USB camera
  -> Linux edge runtime, RKNN inference, V4L2 capture
```

## Current RK3576 Discovery

Detected on the local router after plugging in Ethernet:

```text
Host: kickpi
LAN IP: 192.168.1.199
OS: Ubuntu 24.04.3 LTS, aarch64
Kernel: Linux 6.1.75
Active NIC: end1
Camera alias: /dev/video-camera0 -> /dev/video33
```

SSH test:

```bash
ssh kickpi@192.168.1.199
```

## 1. Install Mac Tools

Install Homebrew if it is not installed:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Install daily tools:

```bash
brew install git openssh rsync wget tree cmake ninja pkg-config jq yq
brew install --cask tailscale visual-studio-code
```

Start Tailscale from the app and log in with the same account used by Windows
and, if possible, the RK3576 board.

## 2. Generate SSH Key

Check existing keys:

```bash
ls -la ~/.ssh
```

Create a dedicated key for this project:

```bash
ssh-keygen -t ed25519 -C "macbook-edgeav" -f ~/.ssh/id_ed25519_edgeav
```

Start the SSH agent and add the key:

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519_edgeav
```

Show the public key:

```bash
cat ~/.ssh/id_ed25519_edgeav.pub
```

Copy this public key into:

- Windows OpenSSH: `C:\Users\<WindowsUser>\.ssh\authorized_keys`
- WSL2 Ubuntu: `/home/<UbuntuUser>/.ssh/authorized_keys`
- RK3576: `/home/kickpi/.ssh/authorized_keys`

## 3. Configure SSH Hosts

Edit:

```bash
nano ~/.ssh/config
```

Recommended config:

```sshconfig
Host winbox
    HostName 100.84.212.26
    User HP
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3

Host wsl
    HostName <windows_tailscale_ip_or_hostname>
    User <wsl_user>
    Port 2222
    IdentityFile ~/.ssh/id_ed25519_edgeav
    ServerAliveInterval 30
    ServerAliveCountMax 3

Host rk3576
    HostName 100.95.106.106
    User kickpi
    IdentityFile ~/.ssh/id_ed25519_edgeav
    ServerAliveInterval 30
    ServerAliveCountMax 3

Host rk3576-name
    HostName rk3576-edgeav
    User kickpi
    IdentityFile ~/.ssh/id_ed25519_edgeav
    ServerAliveInterval 30
    ServerAliveCountMax 3

Host rk3576-via-win
    HostName <rk3576_lan_ip>
    User kickpi
    IdentityFile ~/.ssh/id_ed25519_edgeav
    ProxyJump winbox
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

Secure permissions:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/config ~/.ssh/id_ed25519_edgeav
chmod 644 ~/.ssh/id_ed25519_edgeav.pub
```

## 4. Test Connections

Test from MacBook:

```bash
ssh winbox
ssh wsl
ssh rk3576
ssh rk3576-via-win
```

If direct RK3576 access fails outside home, use the jump-host entry:

```bash
ssh rk3576-via-win
```

## 5. Git Setup

```bash
git config --global user.name "<your_name>"
git config --global user.email "<your_email>"
git config --global pull.rebase false
git config --global init.defaultBranch main
```

Optional GitHub SSH test:

```bash
ssh -T git@github.com
```

## 6. Project Sync Commands

MacBook to Windows/WSL:

```bash
rsync -av --delete \
  --exclude .git \
  --exclude build \
  --exclude runs \
  --exclude data \
  ./ wsl:~/spatial-edgeav/
```

MacBook to RK3576:

```bash
rsync -av --delete \
  --exclude .git \
  --exclude training \
  --exclude data \
  ./ rk3576:~/spatial-edgeav/
```

Copy RKNN model to board:

```bash
scp models/*.rknn rk3576:~/spatial-edgeav/models/
```

## 7. Remote Workflow

Train or convert on WSL:

```bash
ssh wsl
cd ~/spatial-edgeav
python3 training/video/export_onnx.py
python3 conversion/onnx_to_rknn.py
scp models/*.rknn rk3576:~/spatial-edgeav/models/
```

Deploy and test on RK3576:

```bash
ssh rk3576
cd ~/spatial-edgeav
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)
./build/edgeav --config configs/device.yaml
```

If systemd service is installed:

```bash
sudo systemctl restart edgeav
journalctl -u edgeav -f
```

## 8. Travel Readiness Test

Before leaving, test this through a mobile hotspot, not home Wi-Fi:

```bash
ssh winbox
ssh wsl
ssh rk3576-via-win
scp README.md rk3576-via-win:/tmp/macbook_ssh_test.md
```

The setup is travel-ready only when all four commands work from the hotspot.
