#!/usr/bin/env bash
echo "=== motion_wide.service ==="
systemctl --no-pager --full status motion_wide.service || true
echo
echo "=== Current release ==="
readlink -f /opt/pi-video-system/current || true
echo
echo "=== Ports (8080) ==="
ss -lntp | awk '$4 ~ /:8080$/'
echo
echo "=== /api/stats ==="
curl -s http://localhost:8080/api/stats | python3 -m json.tool || true
echo
echo "=== /api/debug/distance ==="
curl -s http://localhost:8080/api/debug/distance | python3 -m json.tool || true
echo
echo "=== I2C scan (bus 1) ==="
i2cdetect -y 1 || true
