#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "error: run backup as root" >&2
  exit 1
fi

if [[ -r /etc/icthub-auth/backup.env ]]; then
  # shellcheck disable=SC1091
  source /etc/icthub-auth/backup.env
fi
: "${AGE_RECIPIENT:?set AGE_RECIPIENT in /etc/icthub-auth/backup.env}"
BACKUP_ROOT=${BACKUP_ROOT:-/home/winbeau/backups/icthub-auth}
BACKUP_RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30}
DEPLOY_DIR=/home/winbeau/services/authentik-deploy
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
PARTIAL="${BACKUP_ROOT}/.${TIMESTAMP}.partial"
FINAL="${BACKUP_ROOT}/${TIMESTAMP}"

install -d -o root -g root -m 0750 "${BACKUP_ROOT}"
install -d -o root -g root -m 0750 "${PARTIAL}"
trap 'rm -rf -- "${PARTIAL}"' EXIT

cd "${DEPLOY_DIR}"
python3 manage.py validate
docker compose exec -T postgresql sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' \
  | age -r "${AGE_RECIPIENT}" -o "${PARTIAL}/database.dump.age"

tar -C / -czf - \
  etc/icthub-auth \
  home/winbeau/services/authentik-data/data \
  home/winbeau/services/authentik-deploy \
  | age -r "${AGE_RECIPIENT}" -o "${PARTIAL}/files.tar.gz.age"

{
  echo "created_at=${TIMESTAMP}"
  echo "authentik_image=ghcr.io/goauthentik/server:2026.5.5"
  echo "postgres_image=postgres:16.11-alpine"
  (cd "${PARTIAL}" && sha256sum database.dump.age files.tar.gz.age)
} > "${PARTIAL}/manifest.txt"
chmod 0640 "${PARTIAL}"/*
mv "${PARTIAL}" "${FINAL}"
trap - EXIT

if [[ ${BACKUP_RETENTION_DAYS} =~ ^[0-9]+$ ]] && (( BACKUP_RETENTION_DAYS > 0 )); then
  find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime "+${BACKUP_RETENTION_DAYS}" -name '20*T*Z' -exec rm -rf -- {} +
fi

echo "Encrypted Authentik backup written to ${FINAL}"
