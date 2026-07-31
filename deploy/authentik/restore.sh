#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "error: run restore as root in an isolated recovery environment" >&2
  exit 1
fi
if [[ $# -ne 1 ]]; then
  echo "usage: $0 BACKUP_DIRECTORY" >&2
  exit 1
fi
: "${AGE_IDENTITY_FILE:?set AGE_IDENTITY_FILE to the root-readable age identity file}"

BACKUP_DIR=$(realpath "$1")
DEPLOY_DIR=/home/winbeau/services/authentik-deploy
for file in manifest.txt database.dump.age files.tar.gz.age; do
  [[ -r "${BACKUP_DIR}/${file}" ]] || { echo "error: missing ${file}" >&2; exit 1; }
done
identity_mode=$((8#$(stat -c '%a' "${AGE_IDENTITY_FILE}")))
if (( identity_mode & ~0640 )); then
  echo "error: age identity permissions exceed 0640" >&2
  exit 1
fi

(cd "${BACKUP_DIR}" && sha256sum -c <(grep '  .*\.age$' manifest.txt))
read -r -p 'Type "RESTORE ICTHUB AUTH" to replace the identity service state: ' confirmation
[[ ${confirmation} == "RESTORE ICTHUB AUTH" ]] || { echo "restore cancelled" >&2; exit 1; }

systemctl stop cloudflared-icthub.service icthub-login.service || true
if [[ -d "${DEPLOY_DIR}" ]]; then
  cd "${DEPLOY_DIR}"
  docker compose stop server worker postgresql || true
fi

age -d -i "${AGE_IDENTITY_FILE}" "${BACKUP_DIR}/files.tar.gz.age" | tar -C / -xzf -
cat > /etc/icthub-auth/login-config.js <<'EOF'
window.ICTHUB_AUTH_CONFIG = Object.freeze({
  registrationEnabled: false,
});
EOF
chmod 0640 /etc/icthub-auth/login-config.js
chown root:1000 /etc/icthub-auth/login-config.js
cd "${DEPLOY_DIR}"
python3 manage.py validate
docker compose up -d postgresql

for _ in $(seq 1 60); do
  if docker compose exec -T postgresql sh -c 'pg_isready -d "$POSTGRES_DB" -U "$POSTGRES_USER"' >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker compose exec -T postgresql sh -c 'pg_isready -d "$POSTGRES_DB" -U "$POSTGRES_USER"' >/dev/null

docker compose exec -T postgresql sh -c 'dropdb --force -U "$POSTGRES_USER" "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
age -d -i "${AGE_IDENTITY_FILE}" "${BACKUP_DIR}/database.dump.age" \
  | docker compose exec -T postgresql sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl'

docker compose up -d --remove-orphans
systemctl start icthub-login.service
python3 manage.py health --wait 180

echo "Restore completed with Tunnel stopped and registration disabled. Finish isolated acceptance before restoring public traffic."
