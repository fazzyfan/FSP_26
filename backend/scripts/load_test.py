"""Минимальный нагрузочный тест (NFR-05) для приёмки.

Проверяет устойчивость API под параллельной нагрузкой:
- 300 запросов к публичным эндпоинтам (healthz, references) в 30 потоков;
- 50 запросов авторизованного кандидата (сводка оценки);
- выводит p50/p95 и количество ошибок.

Запуск:
    docker compose exec -T api python scripts/load_test.py
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys

import httpx

PASSWORD = "DemoPass2026!"

if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def worker(client: httpx.AsyncClient, path: str, sem: asyncio.Semaphore, lat: list[float], errors: list[str]) -> None:
    async with sem:
        start = asyncio.get_event_loop().time()
        try:
            r = await client.get(path)
            dt = (asyncio.get_event_loop().time() - start) * 1000
            lat.append(dt)
            if r.status_code >= 500:
                errors.append(f"{path}:{r.status_code}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path}:{exc}")


async def main() -> int:
    base = os.environ.get("SMOKE_BASE", "http://localhost:8000")
    api = f"{base}/api/v1"
    lat_public: list[float] = []
    lat_auth: list[float] = []
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.post(f"{api}/auth/login", json={"email": "candidate@example.com", "password": PASSWORD})
        if r.status_code != 200:
            print(f"Вход не удался: {r.status_code} {r.text[:200]}")
            return 1
        headers = {"X-CSRF-Token": c.cookies.get("fsp_csrf") or ""}

        sem = asyncio.Semaphore(30)
        await asyncio.gather(*[
            worker(c, f"{api}/references/grades", sem, lat_public, errors) for _ in range(150)
        ] + [
            worker(c, f"{base}/healthz", sem, lat_public, errors) for _ in range(150)
        ])

        sem2 = asyncio.Semaphore(10)
        await asyncio.gather(*[
            worker(c, f"{api}/candidate/assessment", sem2, lat_auth, errors) for _ in range(50)
        ])

    def report(name: str, data: list[float]) -> None:
        if not data:
            print(f"{name}: нет данных")
            return
        data_sorted = sorted(data)
        p50 = data_sorted[len(data_sorted) // 2]
        p95 = data_sorted[int(len(data_sorted) * 0.95) - 1]
        print(f"{name}: {len(data)} запросов, p50={p50:.0f} мс, p95={p95:.0f} мс, max={data_sorted[-1]:.0f} мс")

    report("публичные эндпоинты", lat_public)
    report("сводка оценки (авторизован)", lat_auth)

    if errors:
        print(f"Ошибок: {len(errors)}: {errors[:5]}")
        return 1
    print("Нагрузочный тест пройден: ошибок нет.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))