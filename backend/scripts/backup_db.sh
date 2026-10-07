#!/bin/sh
# Резервное копирование БД (NFR-08).
# Запуск с хоста (из корня репозитория):
#   sh backend/scripts/backup_db.sh
# Копия сохраняется в backend/backups/fsp-<время>.sql
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "${ROOT}/backend/backups"
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="${ROOT}/backend/backups/fsp-${STAMP}.sql"

echo "Создаю резервную копию: ${OUT}"
docker compose -f "${ROOT}/docker-compose.yml" exec -T db \
    pg_dump -U fsp -d fsp --no-owner --clean --if-exists > "${OUT}"

echo "Готово. Размер:"
ls -lh "${OUT}"