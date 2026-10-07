#!/bin/sh
# Восстановление БД из резервной копии (NFR-08).
# Использование (с хоста, из корня репозитория):
#   sh backend/scripts/restore_db.sh backend/backups/fsp-YYYYMMDD-HHMMSS.sql
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FILE="${1:-}"
if [ -z "${FILE}" ] || [ ! -f "${ROOT}/${FILE}" ]; then
    echo "Укажите файл копии относительно корня репозитория, например: backend/backups/fsp-20261007-120000.sql"
    exit 1
fi

echo "Восстановление из ${FILE} ..."
docker compose -f "${ROOT}/docker-compose.yml" exec -T db \
    psql -U fsp -d fsp -v ON_ERROR_STOP=1 < "${ROOT}/${FILE}"
echo "Восстановление завершено. Перезапустите API: docker compose restart api"