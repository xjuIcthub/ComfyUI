#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "error: run this installer as root" >&2
  exit 1
fi

SOURCE_DIR=${1:-$(cd "$(dirname "$0")" && pwd)}
DEPLOY_DIR=/home/winbeau/services/authentik-deploy
DATA_DIR=/home/winbeau/services/authentik-data
SECRET_DIR=/etc/icthub-auth

for command in docker age openssl python3; do
  if ! command -v "${command}" >/dev/null; then
    echo "error: required system command is missing: ${command}" >&2
    exit 1
  fi
done
if ! docker compose version >/dev/null 2>&1; then
  echo "error: Docker Compose v2 is required" >&2
  exit 1
fi

install -d -o root -g 1000 -m 0750 "${DEPLOY_DIR}" "${DATA_DIR}"
install -d -o 1000 -g 1000 -m 0750 "${DATA_DIR}/data"
install -d -o 70 -g 70 -m 0750 "${DATA_DIR}/postgresql"
install -d -o root -g root -m 0750 "${SECRET_DIR}"

if [[ $(realpath "${SOURCE_DIR}") != $(realpath "${DEPLOY_DIR}") ]]; then
  # Preserve bind mount directory inodes so running containers see updated files.
  for mounted_dir in blueprints custom-templates media; do
    install -d -o root -g 1000 -m 0750 "${DEPLOY_DIR}/${mounted_dir}"
    find "${DEPLOY_DIR}/${mounted_dir}" -mindepth 1 -delete
  done
  find "${DEPLOY_DIR}" -mindepth 1 -maxdepth 1 \
    ! -name blueprints ! -name custom-templates ! -name media \
    -exec rm -rf -- {} +
  cp -a "${SOURCE_DIR}/." "${DEPLOY_DIR}/"
fi
chown -R root:1000 "${DEPLOY_DIR}"
find "${DEPLOY_DIR}" -type d -exec chmod 0750 {} +
find "${DEPLOY_DIR}" -type f -exec chmod 0640 {} +
chmod 0750 "${DEPLOY_DIR}/install.sh" "${DEPLOY_DIR}/manage.py" "${DEPLOY_DIR}/backup.sh" "${DEPLOY_DIR}/restore.sh"

if [[ ! -e "${SECRET_DIR}/authentik.env" ]]; then
  cp "${SOURCE_DIR}/authentik.env.example" "${SECRET_DIR}/authentik.env"
  PG_PASSWORD=$(openssl rand -base64 36 | tr -d '\n')
  SECRET_KEY=$(openssl rand -base64 60 | tr -d '\n')
  OIDC_CLIENT_ID=$(openssl rand -hex 20)
  OIDC_CLIENT_SECRET=$(openssl rand -base64 48 | tr -d '\n')
  python3 - "${SECRET_DIR}/authentik.env" "${PG_PASSWORD}" "${SECRET_KEY}" "${OIDC_CLIENT_ID}" "${OIDC_CLIENT_SECRET}" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace("GENERATE_A_RANDOM_DATABASE_PASSWORD", sys.argv[2])
text = text.replace("GENERATE_A_RANDOM_AUTHENTIK_SECRET_KEY", sys.argv[3])
text = text.replace("GENERATE_A_RANDOM_OIDC_CLIENT_ID", sys.argv[4])
text = text.replace("GENERATE_A_RANDOM_OIDC_CLIENT_SECRET", sys.argv[5])
path.write_text(text, encoding="utf-8")
PY
fi

if [[ ! -e "${SECRET_DIR}/login-config.js" ]]; then
  cp "${SOURCE_DIR}/../login-page/runtime-config.js" "${SECRET_DIR}/login-config.js"
fi
chmod 0640 "${SECRET_DIR}/authentik.env" "${SECRET_DIR}/login-config.js"
chown root:root "${SECRET_DIR}/authentik.env"
chown root:1000 "${SECRET_DIR}/login-config.js"

for unit in icthub-authentik.service icthub-authentik-backup.service icthub-authentik-backup.timer; do
  install -o root -g root -m 0644 "${DEPLOY_DIR}/${unit}" "/etc/systemd/system/${unit}"
done
systemctl daemon-reload

echo "Installed Authentik deployment files."
echo "Next: edit ${SECRET_DIR}/authentik.env, set the exact Cloudflare callback URI and SMTP settings, then run manage.py validate."
