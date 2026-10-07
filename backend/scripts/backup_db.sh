#!/bin/sh
# Резервное копирование БД (NFR-08).
# Запуск внутри контейнера API:  docker compose exec -T api sh scripts/backup_db.sh
# Восстановление:             docker compose exec -T api sh scripts/restore_db.sh backups/<файл>.sql
set -eu

mkdir -p /app/backups
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="/app/backups/fsp-${STAMP}.sql"

echo "Создаю резервную копию: ${OUT}"
pg_dump -h db -U fsp -d fsp --no-owner --clean --if-exists > "${OUT}"

# Копия наружу (на хост) по желанию:
# docker cp fsp_2k26-api-1:/app/backups/fsp-${STAMP}.sql ./

echo "Готово: ${OUT}"
ls -lh /app/backups | tail -5