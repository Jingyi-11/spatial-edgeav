#!/usr/bin/env bash
set -euo pipefail

required_vars=(
  WIN_HOST
  WIN_USER
  WSL_USER
  RK3576_HOST
)

for var in "${required_vars[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo "Missing ${var}." >&2
    echo "Example:" >&2
    echo "  WIN_HOST=100.x.y.z WIN_USER=you WSL_USER=ubuntu RK3576_HOST=192.168.1.88 $0" >&2
    exit 1
  fi
done

SSH_KEY="${SSH_KEY:-${HOME}/.ssh/id_ed25519}"
SSH_CONFIG="${HOME}/.ssh/config"
START_MARKER="# >>> linux_camera remote hosts >>>"
END_MARKER="# <<< linux_camera remote hosts <<<"

mkdir -p "${HOME}/.ssh"
touch "${SSH_CONFIG}"
chmod 700 "${HOME}/.ssh"
chmod 600 "${SSH_CONFIG}"

tmp_config="$(mktemp)"
awk -v start="${START_MARKER}" -v end="${END_MARKER}" '
  $0 == start {skip = 1; next}
  $0 == end {skip = 0; next}
  !skip {print}
' "${SSH_CONFIG}" > "${tmp_config}"

cat >> "${tmp_config}" <<EOF

${START_MARKER}
Host winbox
    HostName ${WIN_HOST}
    User ${WIN_USER}
    IdentityFile ${SSH_KEY}
    AddKeysToAgent yes
    UseKeychain yes
    ServerAliveInterval 30
    ServerAliveCountMax 3

Host wsl
    HostName ${WIN_HOST}
    User ${WSL_USER}
    Port ${WSL_PORT:-2222}
    IdentityFile ${SSH_KEY}
    AddKeysToAgent yes
    UseKeychain yes
    ServerAliveInterval 30
    ServerAliveCountMax 3

Host rk3576
    HostName ${RK3576_HOST}
    User ${RK3576_USER:-kickpi}
    IdentityFile ${SSH_KEY}
    AddKeysToAgent yes
    UseKeychain yes
    ServerAliveInterval 30
    ServerAliveCountMax 3

Host rk3576-via-win
    HostName ${RK3576_HOST}
    User ${RK3576_USER:-kickpi}
    IdentityFile ${SSH_KEY}
    ProxyJump winbox
    AddKeysToAgent yes
    UseKeychain yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
${END_MARKER}
EOF

mv "${tmp_config}" "${SSH_CONFIG}"
chmod 600 "${SSH_CONFIG}"

echo "Updated ${SSH_CONFIG}"
echo
echo "Next tests:"
echo "  ssh winbox hostname"
echo "  ssh wsl 'uname -a'"
echo "  ssh rk3576 'uname -a'"
echo "  ssh rk3576-via-win 'ls /dev/video*'"

