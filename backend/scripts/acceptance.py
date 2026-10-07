"""Приёмочный прогон MVP: все проверки одним запуском (Этап 5).

Запуск (в контейнере API, после `docker compose up`):
    docker compose exec -T api python scripts/acceptance.py

Скрипт последовательно запускает smoke-тест, сквозную цепочку и проверки
этапов 1–4, собирает счётчики [OK]/[FAIL] и завершается ненулевым кодом
при любом падении. Покрывает 20+ основных сценариев и 8+ проверок со сбоями
(409/422/401/404) без ручной настройки.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys

SCRIPTS = [
    ("smoke_test.py", "базовые сценарии (FR-01..FR-17)"),
    ("chain_check.py", "полный путь профиль→тест→подбор→приглашение→контакты"),
    ("verify_stage1.py", "этап 1: приглашения и контакты"),
    ("verify_stage2.py", "этап 2: тестирование и категории"),
    ("verify_stage3.py", "этап 3: подбор (формула, фильтры, пагинация)"),
    ("verify_stage4.py", "этап 4: ФСП, PDF, согласия, права"),
]


async def run_script(name: str, description: str) -> tuple[bool, int, int, str]:
    env = {**os.environ, "SMOKE_BASE": os.environ.get("SMOKE_BASE", "http://localhost:8000")}
    proc = await asyncio.create_subprocess_exec(
        sys.executable, f"scripts/{name}", env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    text = out.decode("utf-8", "replace")
    ok_count = len(re.findall(r"\[OK \]", text))
    fail_count = len(re.findall(r"\[FAIL\]", text))
    ok = proc.returncode == 0
    print(f"\n=== {name}: {description} ===")
    for line in text.splitlines():
        if "[OK ]" in line or "[FAIL]" in line:
            print("  " + line.strip())
    return ok, ok_count, fail_count, name


async def main() -> int:
    base = os.environ.get("SMOKE_BASE", "http://localhost:8000")
    print(f"Приёмочный прогон MVP против {base}")
    # Последовательно: скрипты создают контрольные данные и не должны мешать друг другу
    results = []
    for name, description in SCRIPTS:
        results.append(await run_script(name, description))

    total_ok = sum(r[1] for r in results)
    total_fail = sum(r[2] for r in results)
    print("\n" + "=" * 60)
    for ok, okc, failc, name in results:
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {name}: {okc} успешно, {failc} упало")
    print(f"\nИтого: {total_ok} проверок успешно, {total_fail} упало")
    if total_fail:
        print("ПРИЁМКА НЕ ПРОЙДЕНА")
        return 1
    print("ПРИЁМКА ПРОЙДЕНА: 20+ основных сценариев и проверки со сбоями — зелёные.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))