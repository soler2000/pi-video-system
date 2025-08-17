#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
SRCDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPROOT="/opt/pi-video-system"
RELEASES="$APPROOT/releases"
CURRENT_LINK="$APPROOT/current"
VENV="$APPROOT/.venv"
case "$SRCDIR" in "$APPROOT"|"$APPROOT"/*) echo "ERROR: Do not run install.sh from inside $APPROOT."; exit 1;; esac
echo "[1/12] Stop service"; sudo systemctl stop motion_wide.service || true
echo "[2/12] Apt deps + enable I2C"
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-dev build-essential pkg-config libffi-dev libssl-dev libatlas-base-dev i2c-tools rsync curl git
if ! grep -q '^dtparam=i2c_arm=on' /boot/firmware/config.txt 2>/dev/null; then echo 'dtparam=i2c_arm=on' | sudo tee -a /boot/firmware/config.txt; fi
sudo modprobe i2c-dev || true
STAMP="$(date +%Y%m%d-%H%M%S)"; STAGE="$(mktemp -d /tmp/pivs.stage.XXXXXX)"; NEWREL="$RELEASES/$STAMP"; trap 'rm -rf "$STAGE" || true' EXIT
echo "[3/12] Stage source to $STAGE"; rsync -a --delete --exclude '.venv' "$SRCDIR/" "$STAGE/"
echo "[4/12] Copy staged → $NEWREL"; sudo mkdir -p "$RELEASES"; sudo rsync -a --delete "$STAGE/" "$NEWREL/"
echo "[5/12] Preserve existing config.yaml"; if [[ -f "$APPROOT/config/config.yaml" ]]; then sudo mkdir -p "$NEWREL/config"; sudo cp "$APPROOT/config/config.yaml" "$NEWREL/config/config.yaml"; echo "  - preserved config.yaml"; fi
echo "[6/12] Ensure required subfolders"; sudo mkdir -p "$NEWREL"/{app,app/templates,app/static,config,systemd,tools}
echo "[7/12] Create/upgrade venv at $VENV"; if [[ ! -d "$VENV" ]]; then sudo python3 -m venv "$VENV"; fi; sudo "$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
echo "[8/12] pip install requirements into venv"
if ! sudo "$VENV/bin/python" -m pip install -r "$NEWREL/requirements.txt"; then echo "  - retry after clearing pip cache…"; sudo rm -rf /root/.cache/pip || true; sudo "$VENV/bin/python" -m pip install -r "$NEWREL/requirements.txt"; fi
echo "[9/12] Install/refresh systemd unit"; sudo install -m 0644 "$NEWREL/systemd/motion_wide.service" /etc/systemd/system/motion_wide.service; sudo systemctl daemon-reload; sudo systemctl enable motion_wide.service
echo "[10/12] Switch /opt/pi-video-system/current → new release"; sudo mkdir -p "$APPROOT"; TMP_LINK="$(mktemp -u /tmp/pivs.link.XXXXXX)"; sudo ln -sfn "$NEWREL" "$TMP_LINK"; sudo mv -Tf "$TMP_LINK" "$CURRENT_LINK"
echo "[11/12] Permissions + start"; sudo chown -R root:root "$APPROOT"; sudo find "$APPROOT" -type d -exec chmod 755 {} \; >/dev/null 2>&1 || true; sudo find "$APPROOT" -type f -exec chmod 644 {} \; >/dev/null 2>&1 || true; sudo chmod 755 "$APPROOT" "$VENV" "$VENV/bin" || true; sudo systemctl restart motion_wide.service
echo "[12/12] Health checks"; sleep 1; systemctl --no-pager --full status motion_wide.service | tail -n 40 || true; echo; echo "Active release: $(readlink -f "$CURRENT_LINK")"; echo "pip:"; sudo "$VENV/bin/python" -m pip -V; echo; echo "Stats:"; curl -s http://localhost:8080/api/stats || true; echo; echo "Open http://<PI-IP>:8080/?v=1"
