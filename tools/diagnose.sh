#!/usr/bin/env bash
set -euo pipefail
echo "# Ports"; sudo ss -ltnp | sed -n '1,10p'
echo "# Service"; systemctl status motion_wide.service --no-pager -l | sed -n '1,25p'
echo "# Stats"; curl -s http://127.0.0.1:8080/api/stats || true; echo
