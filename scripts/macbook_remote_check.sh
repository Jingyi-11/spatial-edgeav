#!/usr/bin/env bash
set -euo pipefail

echo "== macOS =="
sw_vers || true
uname -m

echo
echo "== local tools =="
for tool in brew git ssh rsync cmake ninja jq tailscale code; do
  if command -v "${tool}" >/dev/null 2>&1; then
    printf "found:   %-10s %s\n" "${tool}" "$(command -v "${tool}")"
  else
    printf "missing: %-10s\n" "${tool}"
  fi
done

echo
echo "== ssh directory =="
ls -la "${HOME}/.ssh" || true

echo
echo "== ssh config hosts =="
if [ -f "${HOME}/.ssh/config" ]; then
  awk '/^Host / {print}' "${HOME}/.ssh/config"
else
  echo "missing: ~/.ssh/config"
fi

echo
echo "== suggested next tests =="
cat <<'EOF'
ssh winbox hostname
ssh wsl 'uname -a'
ssh rk3576 'uname -a'
ssh rk3576-via-win 'ls /dev/video*'
EOF

