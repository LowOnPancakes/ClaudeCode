#!/usr/bin/env bash
# Installs the Org Chart Wireframe web app as a systemd service on
# CentOS/RHEL/Rocky (or any dnf/yum-based distro), served by gunicorn on
# 127.0.0.1:8000. Put nginx (or another reverse proxy) in front of it for
# public/team access - see nginx-org-chart.conf in this same directory.
#
# Run as root (or with sudo) from anywhere; it locates the repo relative to
# this script, so `sudo bash webapp/deploy/install_centos.sh` from a clone
# of the repo works as-is.
set -euo pipefail

APP_USER="orgchart"
INSTALL_DIR="/opt/org-chart-webapp"
SERVICE_NAME="org-chart-webapp"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEBAPP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_DIR="$(cd "${WEBAPP_DIR}/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Run this as root (sudo bash $0)" >&2
  exit 1
fi

echo "==> Installing OS packages (python3, pip, venv)"
if command -v dnf >/dev/null; then
  dnf install -y python3 python3-pip python3-virtualenv
else
  yum install -y python3 python3-pip python3-virtualenv
fi

echo "==> Creating service user '${APP_USER}' (no login)"
id -u "${APP_USER}" >/dev/null 2>&1 || useradd --system --no-create-home --shell /sbin/nologin "${APP_USER}"

echo "==> Copying application to ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
cp "${REPO_DIR}/org_chart_converter.py" "${INSTALL_DIR}/"
mkdir -p "${INSTALL_DIR}/webapp"
cp "${WEBAPP_DIR}/app.py" "${WEBAPP_DIR}/passenger_wsgi.py" "${WEBAPP_DIR}/requirements.txt" "${INSTALL_DIR}/webapp/"
cp -r "${WEBAPP_DIR}/templates" "${INSTALL_DIR}/webapp/"
chown -R "${APP_USER}:${APP_USER}" "${INSTALL_DIR}"

echo "==> Creating virtualenv and installing dependencies"
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip --quiet
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/webapp/requirements.txt" gunicorn --quiet
chown -R "${APP_USER}:${APP_USER}" "${INSTALL_DIR}/venv"

echo "==> Installing systemd unit"
cp "${SCRIPT_DIR}/${SERVICE_NAME}.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo
echo "==> Done. Service status:"
systemctl --no-pager status "${SERVICE_NAME}" || true
echo
echo "The app is listening on 127.0.0.1:8000 (not exposed externally yet)."
echo "Next: set up nginx (see nginx-org-chart.conf) to serve it publicly,"
echo "and open the relevant port in firewalld, e.g.:"
echo "  firewall-cmd --permanent --add-service=https && firewall-cmd --reload"
echo
echo "To redeploy after a code change, re-run this script - it overwrites"
echo "${INSTALL_DIR} and restarts the service."
