#!/bin/sh
# Восстановление БД из резервной копии (NFR-08).
# Использование:
#   docker compose exec -T api sh scripts/restore_db.sh backups/fsp-YYYYMMDD-HHMMSS.sql
set -eu

FILE="${1:-}"
if [ -z "${FILE}" ] || [ ! -f "/app/${FILE}" ]; then
    echo "Укажите файл копии внутри контейнера, например: backups/fsp-20261007-120000.sql"
    exit 1
fi

echo "Восстановление из ${FILE} ..."
psql -h db -U fsp -d fsp -v ON_ERROR_STOP=1 -f "/app/${FILE}"
echo "Восстановление завершено."