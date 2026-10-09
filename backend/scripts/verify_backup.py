"""Проверка восстановления БД из резервной копии (NFR-08).

Запуск (с хоста, из корня репозитория; требуется docker CLI):
    python backend/scripts/verify_backup.py

Шаги:
1. создаёт резервную копию main-БД (pg_dump через docker compose) во временный файл;
2. разворачивает её в отдельную базу fsp_restore_check;
3. сравнивает количество строк ключевых таблиц (accounts, candidate_profiles,
   test_attempts, invitations, test_questions) с источником;
4. удаляет проверочную базу и завершается с кодом 0 только при полном совпадении.

Скрипт кроссплатформенный (Windows/Linux): вызывает только `docker compose ...`.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "docker-compose.yml")]
CHECK_DB = "fsp_restore_check"
TABLES = ["accounts", "candidate_profiles", "test_attempts", "test_attempt_answers",
          "invitations", "test_questions", "confirmed_categories"]


async def run(*cmd: str, input_bytes: bytes | None = None) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(ROOT),
        stdin=asyncio.subprocess.PIPE if input_bytes is not None else None,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate(input_bytes)
    return proc.returncode or 0, out.decode("utf-8", "replace")


def count_line(out: str) -> int:
    stripped = out.strip()
    return int(stripped.splitlines()[0]) if stripped else 0


async def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        dump_path = Path(tmp) / "fsp-verify-dump.sql"

        print("1/4 Создаю резервную копию основной БД (pg_dump) ...")
        rc, out = await run(*COMPOSE, "exec", "-T", "db",
                            "pg_dump", "-U", "fsp", "-d", "fsp", "--no-owner", "--clean", "--if-exists")
        if rc != 0 or not out.strip():
            print("Резервная копия не создана:\n" + out[:1000])
            return 1
        dump_path.write_text(out, encoding="utf-8")
        print(f"Копия: {dump_path} ({len(out) // 1024} КБ)")

        print(f"2/4 Готовлю проверочную базу {CHECK_DB} ...")
        await run(*COMPOSE, "exec", "-T", "db", "psql", "-U", "fsp", "-d", "postgres",
                  "-c", f"DROP DATABASE IF EXISTS {CHECK_DB}")
        rc, out = await run(*COMPOSE, "exec", "-T", "db", "psql", "-U", "fsp", "-d", "postgres",
                            "-c", f"CREATE DATABASE {CHECK_DB}")
        if rc != 0:
            print("Не удалось создать проверочную базу:\n" + out[:1000])
            return 1

        print("3/4 Восстанавливаю копию в проверочную базу ...")
        rc, out = await run(*COMPOSE, "exec", "-T", "db", "psql", "-U", "fsp", "-d", CHECK_DB,
                            "-v", "ON_ERROR_STOP=1", input_bytes=dump_path.read_bytes())
        if rc != 0:
            print("Восстановление упало:\n" + out[:2000])
            await run(*COMPOSE, "exec", "-T", "db", "psql", "-U", "fsp", "-d", "postgres",
                      "-c", f"DROP DATABASE IF EXISTS {CHECK_DB}")
            return 1

        mismatches = []
        for table in TABLES:
            src_rc, src_out = await run(*COMPOSE, "exec", "-T", "db", "psql", "-U", "fsp", "-d", "fsp",
                                        "-tA", "-c", f"SELECT count(*) FROM {table}")
            chk_rc, chk_out = await run(*COMPOSE, "exec", "-T", "db", "psql", "-U", "fsp", "-d", CHECK_DB,
                                        "-tA", "-c", f"SELECT count(*) FROM {table}")
            if src_rc != 0 or chk_rc != 0:
                mismatches.append(f"{table}: ошибка чтения (src_rc={src_rc}, chk_rc={chk_rc})")
                continue
            s, c = count_line(src_out), count_line(chk_out)
            status = "OK " if s == c else "FAIL"
            print(f"[{status}] {table}: источник={s}, восстановлено={c}")
            if s != c:
                mismatches.append(f"{table}: {s} != {c}")

        print("4/4 Удаляю проверочную базу ...")
        await run(*COMPOSE, "exec", "-T", "db", "psql", "-U", "fsp", "-d", "postgres",
                  "-c", f"DROP DATABASE IF EXISTS {CHECK_DB}")

        if mismatches:
            print(f"\nВОССТАНОВЛЕНИЕ НЕ ПОДТВЕРЖДЕНО: {mismatches}")
            return 1
        print("\nВосстановление подтверждено: все ключевые таблицы совпадают с источником.")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
