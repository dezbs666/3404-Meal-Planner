#!/usr/bin/env bash
# Family Meal Planner — Raspberry Pi (or any Debian/Ubuntu host) installer.
# Run this from inside the cloned repo:
#   sudo bash install.sh
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Please run with sudo:  sudo bash install.sh"
  exit 1
fi

APP_USER="${SUDO_USER:-pi}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="mealplanner"

echo "==> Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip >/dev/null

echo "==> Creating Python virtual environment in ${REPO_DIR}/venv ..."
if [[ ! -d "${REPO_DIR}/venv" ]]; then
  python3 -m venv "${REPO_DIR}/venv"
fi
"${REPO_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${REPO_DIR}/venv/bin/pip" install --quiet -r "${REPO_DIR}/requirements.txt"

echo "==> Creating systemd service (${SERVICE_NAME})..."
chown -R "${APP_USER}:${APP_USER}" "${REPO_DIR}"

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=Family Meal Planner (Flask web app)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${REPO_DIR}
Environment=MEALPLANNER_HOST=0.0.0.0
ExecStart=${REPO_DIR}/venv/bin/python ${REPO_DIR}/app.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"

TS_IP="$(tailscale ip -4 2>/dev/null || true)"
FIRST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "Meal Planner is running and will start automatically at boot."
if [[ -n "${TS_IP}" ]]; then
  echo "  From any device on your tailnet:  http://${TS_IP}:5000"
fi
if [[ -n "${FIRST_IP}" ]]; then
  echo "  From your home network:           http://${FIRST_IP}:5000"
fi
echo
echo "Useful commands:"
echo "    systemctl status ${SERVICE_NAME}"
echo "    sudo systemctl restart ${SERVICE_NAME}"
echo "    journalctl -u ${SERVICE_NAME} -f"
