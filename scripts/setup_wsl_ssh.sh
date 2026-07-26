#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-2222}"

echo "Installing OpenSSH server inside WSL..."
sudo apt update
sudo apt install -y openssh-server

echo "Configuring sshd on port ${PORT}..."
sudo mkdir -p /run/sshd
sudo cp /etc/ssh/sshd_config "/etc/ssh/sshd_config.backup.$(date +%Y%m%d_%H%M%S)"

sudo sed -i \
  -e "s/^#\\?Port .*/Port ${PORT}/" \
  -e "s/^#\\?PasswordAuthentication .*/PasswordAuthentication yes/" \
  -e "s/^#\\?PubkeyAuthentication .*/PubkeyAuthentication yes/" \
  /etc/ssh/sshd_config

if ! grep -q "^Port ${PORT}$" /etc/ssh/sshd_config; then
  echo "Port ${PORT}" | sudo tee -a /etc/ssh/sshd_config >/dev/null
fi

echo "Starting ssh service..."
sudo service ssh restart

echo "WSL SSH status:"
if command -v systemctl >/dev/null 2>&1; then
  sudo systemctl --no-pager status ssh || true
else
  sudo service ssh status || true
fi

echo "WSL IP:"
hostname -I

echo "Local test:"
ssh -o StrictHostKeyChecking=accept-new -p "${PORT}" "${USER}@localhost" 'echo WSL_SSH_OK && hostname && whoami'
