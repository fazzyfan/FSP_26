"""Проверка восстановления БД из резервной копии (NFR-08).

Запуск (с хоста, из корня репозитория):
    python backend/scripts/verify_backup.py
    # или внутри проекта при доступном docker CLI:
    docker compose exec -T api python scripts/verify_backup.py  # не работает: нужен docker CLI

Шаги:
1. создаёт резервную копию main-БД через backup_db.sh (pg_dump в backend/backups/);
2. разворачивает её в отдельную базу fsp_restore_check;
3. сравнивает количество строк ключевых таблиц (accounts, candidate_profiles,
   test_attempts, invitations, test_questions) с источником;
4. удаляет проверочную базу и завершается с кодом 0 только при полном совпадении.

Требуется docker CLI и доступ к контейнеру `db` сервиса (docker compose).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "docker-compose.yml")]
CHECK_DB = "fsp_restore_check"
TABLES = ["accounts", "candidate_profiles", "test_attempts", "test_attempt_answers",
          "invitations", "test_questions", "confirmed_categories"]


async def sh(*cmd: str, input_text: str | None = None) -> tuple[subprocess.CompletedProcess, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(ROOT),
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    out, _ = await proc.communicate(input_text.encode() if input_text is not None else None)
    return proc, out.decode("utf-8", "replace")


def count_line(out: str) -> int:
    """Число строк из psql -tA (пустая строка — нет данных)."""
    return int((out.strip() or "0").splitlines()[0]) if out.strip() else 0


async def main() -> int:
    print("1/4 Создаю резервную копию основной БД ...")
    dump = await sh("sh", "backend/scripts/backup_db.sh")
    if dump[0].returncode != 0:
        print("Резервная копия не создана:\n" + dump[1])
        return 1
    dump_line = [l for l in dump[1].splitlines() if l.startswith("Резервная копия:") or ".sql" in l][0].strip()
    print("Копия:", dump_line)

    async def psql(db: str, sql: str) -> tuple[int, str]:
        proc, out = await sh(
            *COMPOSE, "exec", "-T", "db", "psql", "-U", "fsp", "-d", db, "-tA", "-c", sql
        )
        return proc.returncode, out

    print(f"2/4 Готовлю проверочную базу {CHECK_DB} ...")
    await sh(*COMPOSE, "exec", "-T", "db", "psql", "-U", "fsp", "-d", "postgres",
             "-c", f"DROP DATABASE IF EXISTS {CHECK_DB}")
    rc, out = await sh(*COMPOSE, "exec", "-T", "db", "psql", "-U", "fsp", "-d", "postgres",
                       "-c", f"CREATE DATABASE {CHECK_DB}")
    if rc != 0:
        print("Не удалось создать проверочную базу:\n" + out)
        return 1

    print("3/4 Восстанавливаю копию в проверочную базу ...")
    latest = max((ROOT / "backend" / "backups").glob("fsp-*.sql"), key=lambda p: p.stat().st_mtime)
    rest = await sh(*COMPOSE, "exec", "-T", "db", "psql", "-U", "fsp", "-d", CHECK_DB,
                    "-v", "ON_ERROR_STOP=1", input_text=latest.read_text(encoding="utf-8", errors="replace"))
    if rest[0].returncode != 0:
        print("Восстановление упало:\n" + rest[1][:2000])
        await sh(*COMPOSE, "exec", "-T", "db", "psql", "-U", "fsp", "-d", "postgres",
                 "-c", f"DROP DATABASE IF EXISTS {CHECK_DB}")
        return 1

    mismatches = []
    for table in TABLES:
        src_rc, src_out = await psql("fsp", f"SELECT count(*) FROM {table}")
        chk_rc, chk_out = await psql(CHECK_DB, f"SELECT count(*) FROM {table}")
        if src_rc != 0 or chk_rc != 0:
            mismatches.append(f"{table}: ошибка чтения (src_rc={src_rc}, chk_rc={chk_rc})")
            continue
        s, c = count_line(src_out), count_line(chk_out)
        status = "OK " if s == c else "FAIL"
        print(f"[{status}] {table}: источник={s}, восстановлено={c}")
        if s != c:
            mismatches.append(f"{table}: {s} != {c}")

    print("4/4 Удаляю проверочную базу ...")
    await sh(*COMPOSE, "exec", "-T", "db", "psql", "-U", "fsp", "-d", "postgres",
             "-c", f"DROP DATABASE IF EXISTS {CHECK_DB}")

    if mismatches:
        print(f"\nВОССТАНОВЛЕНИЕ НЕ ПОДТВЕРЖДЕНО: {mismatches}")
        return 1
    print("\nВосстановление подтверждено: все ключевые таблицы совпадают с источником.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))