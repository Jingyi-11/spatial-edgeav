# Windows / WSL Model Validation

This machine is used as the x86 Linux workstation for model validation,
training, ONNX export, and RKNN conversion.

## Current Status

Working:

```text
MacBook -> Tailscale -> Windows OpenSSH
MacBook -> Windows file transfer with scp
MacBook -> Tailscale -> WSL OpenSSH on port 2222
RK3576 sample image -> Windows C:\Users\HP\edgeav_data
WSL YOLOv8n CPU inference -> annotated result copied back to Mac
```

Current SSH aliases from Mac:

```bash
ssh winbox
ssh wslbox
```

The recommended path for model validation is `ssh wslbox`, because it enters
Ubuntu directly and avoids nested Windows `wsl.exe` command forwarding.

## Send RK3576 Sample Image to Windows

```bash
bash scripts/send_sample_to_windows.sh
```

Default destination:

```text
C:\Users\HP\edgeav_data\rk3576_preview.jpg
```

Inside WSL:

```text
/mnt/c/Users/HP/edgeav_data/rk3576_preview.jpg
```

## Scripted WSL Model Smoke Test

From Mac:

```bash
bash scripts/wsl_yolo_smoke_test.sh
```

What it does:

```text
1. Checks /mnt/c/Users/HP/edgeav_data/rk3576_preview.jpg in WSL.
2. Bootstraps pip if the WSL image is minimal.
3. Installs CPU PyTorch, Ultralytics YOLO, and OpenCV in the jingyi user scope.
4. Runs YOLOv8n on CPU.
5. Copies the annotated image back to runs/wsl_yolo_rk3576_preview.jpg.
```

Verified result on the first RK3576 sample:

```text
Ultralytics 8.4.106, Python 3.10.12, torch 2.13.0+cpu
YOLOv8n: 1 person, 1 cup, 1 tv
CPU inference: about 25.9 ms for the sample image
```

## Manual WSL Model Smoke Test

From Mac:

```bash
ssh wslbox
```

Install a lightweight YOLO environment:

```bash
python3 -m pip install --user --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cpu
python3 -m pip install --user --upgrade ultralytics opencv-python-headless
```

Run inference on the RK3576 image:

```bash
export PATH="$HOME/.local/bin:$PATH"
export YOLO_CONFIG_DIR=/mnt/c/Users/HP/edgeav_data/ultralytics_config
yolo predict model=yolov8n.pt \
  source=/mnt/c/Users/HP/edgeav_data/rk3576_preview.jpg \
  project=/mnt/c/Users/HP/edgeav_data/yolo_runs \
  name=smoke \
  exist_ok=True \
  imgsz=640 \
  device=cpu
```

Expected output:

```text
/mnt/c/Users/HP/edgeav_data/yolo_runs/smoke/rk3576_preview.jpg
```

Then from Mac:

```bash
scp wslbox:/mnt/c/Users/HP/edgeav_data/yolo_runs/smoke/rk3576_preview.jpg runs/wsl_yolo_rk3576_preview.jpg
```

## Recommended Fix: SSH Directly Into WSL

Current Mac SSH config has been prepared:

```sshconfig
Host wslbox
    HostName 100.84.212.26
    User jingyi
    Port 2222
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

Windows port forwarding has also been configured once:

```text
0.0.0.0:2222 -> 172.17.123.167:2222
Firewall rule: WSL-SSH-2222
```

If `ssh wslbox` times out during banner exchange, WSL `sshd` is not running or
the WSL IP changed. Run the WSL-side setup below.

Inside WSL:

```bash
sudo apt update
sudo apt install -y openssh-server
sudo sed -i 's/#Port 22/Port 2222/' /etc/ssh/sshd_config
sudo service ssh restart
```

On Windows PowerShell as Administrator:

```powershell
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=2222 connectaddress=127.0.0.1 connectport=2222
New-NetFirewallRule -Name WSL-SSH-2222 -DisplayName "WSL SSH 2222" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 2222
```

Then from Mac:

```bash
ssh jingyi@100.84.212.26 -p 2222
```

After this works, add to `~/.ssh/config`:

```sshconfig
Host wslbox
    HostName 100.84.212.26
    User jingyi
    Port 2222
```

## Scripted Setup

Copy the WSL setup script text into WSL, or run the same commands manually:

```bash
bash scripts/setup_wsl_ssh.sh
```

If the WSL IP shown by `hostname -I` is not `172.17.123.167`, update Windows
portproxy from an Administrator PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_windows_wsl_portproxy.ps1 -WslIp <WSL_IP>
```
