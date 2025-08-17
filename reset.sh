#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="/opt/pi-video-system"
UNIT="motion_wide.service"

echo "[reset] stopping service"
sudo systemctl stop "$UNIT" || true

echo "[reset] removing releases and venv (keep config/media/logs)"
sudo rm -rf "$APP_ROOT/releases" "$APP_ROOT/.venv"
sudo mkdir -p "$APP_ROOT/releases"

echo "[reset] done. Re-run ./install.sh from the new release folder."
