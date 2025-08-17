#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/pi-video-system"
RELEASES="$APP_ROOT/releases"
UNIT="motion_wide.service"
TS="$(date +%Y%m%d-%H%M%S)"
WORKDIR="$(mktemp -d /tmp/pivs-inst.XXXXXX)"
trap 'rm -rf "$WORKDIR" || true' EXIT

echo "[1/11] Preparing target layout"
sudo mkdir -p "$APP_ROOT" "$RELEASES" "$APP_ROOT/config" "$APP_ROOT/media" "$APP_ROOT/logs"
sudo chown -R "$USER:$USER" "$APP_ROOT"

echo "[2/11] Stop service if running"
if systemctl list-unit-files | grep -q "^$UNIT"; then
  sudo systemctl stop "$UNIT" || true
fi

echo "[3/11] Stage this bundle into temp (exclude runtime dirs)"
rsync -a --delete --exclude='.venv/' --exclude='releases/' --exclude='media/' --exclude='logs/' ./ "$WORKDIR/"

echo "[4/11] Remove old releases (as requested)"
rm -rf "$RELEASES" || true
mkdir -p "$RELEASES"

echo "[5/11] Create new release dir"
TARGET="$RELEASES/$TS"
mkdir -p "$TARGET"
rsync -a --delete "$WORKDIR/"/ "$TARGET/"

echo "[6/11] Preserve or install config.yaml"
if [ -f "$APP_ROOT/config/config.yaml" ]; then
  echo "  - keeping existing config.yaml in $APP_ROOT/config"
else
  mkdir -p "$APP_ROOT/config"
  cp -a "$TARGET/config/config.yaml" "$APP_ROOT/config/config.yaml"
  echo "  - installed default config.yaml"
fi

echo "[7/11] Python venv (PEP 668 safe) + deps"
if [ ! -x "$APP_ROOT/.venv/bin/python" ]; then
  sudo apt-get update -y
  sudo apt-get install -y python3-venv python3-dev build-essential
  python3 -m venv "$APP_ROOT/.venv"
fi
"$APP_ROOT/.venv/bin/pip" install --upgrade pip setuptools wheel
# Use piwheels first, PyPI as fallback
"$APP_ROOT/.venv/bin/pip" install \
  --index-url https://www.piwheels.org/simple \
  --extra-index-url https://pypi.org/simple \
  -r "$TARGET/requirements.txt"

echo "[8/11] Systemd unit"
sudo tee /etc/systemd/system/$UNIT >/dev/null <<UNIT
[Unit]
Description=Pi Video System (Flask + sensors)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_ROOT/current
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=HOST=0.0.0.0
Environment=PORT=8080
Environment=USE_FLASK=1
ExecStart=$APP_ROOT/.venv/bin/python -m app.web
Restart=on-failure
User=pi
Group=pi

[Install]
WantedBy=multi-user.target
UNIT

echo "[9/11] Flip current -> new release"
ln -sfn "$TARGET" "$APP_ROOT/current"

echo "[10/11] Reload + enable + restart"
sudo systemctl daemon-reload
sudo systemctl enable $UNIT
sudo systemctl restart $UNIT

echo "[11/11] Done. Deployed to $TARGET"
