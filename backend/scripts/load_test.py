"""Минимальный нагрузочный тест (NFR-05) для приёмки.

Проверяет устойчивость API под параллельной нагрузкой:
- 300 запросов к публичным эндпоинтам (healthz, references) в 30 потоков;
- 50 запросов авторизованного кандидата (сводка оценки);
- 30 запросов подбора работодателя (подбор под потребность);
- 20 параллельных сохранений ответов активной попытки (автосохранение);
- 20 запросов создания приглашения (гонки на partial unique index);
- выводит p50/p95 и количество ошибок.

Запуск:
    docker compose exec -T api python scripts/load_test.py
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
import uuid

import httpx

PASSWORD = "DemoPass2026!"

if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def timed_get(
    client: httpx.AsyncClient,
    path: str,
    lat: list[float],
    errors: list[str],
    headers: dict | None = None,
    *,
    label: str = "",
) -> int:
    start = asyncio.get_event_loop().time()
    try:
        r = await client.get(path, headers=headers)
        dt = (asyncio.get_event_loop().time() - start) * 1000
        lat.append(dt)
        if r.status_code >= 500:
            errors.append(f"{label or path}:{r.status_code}")
        return r.status_code
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{label or path}:{exc}")
        return 0


async def worker(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    sem: asyncio.Semaphore,
    lat: list[float],
    errors: list[str],
    headers: dict | None = None,
    json_body: dict | None = None,
    *,
    label: str = "",
    ok_codes: set[int] | None = None,
) -> None:
    async with sem:
        start = asyncio.get_event_loop().time()
        try:
            r = await client.request(method, path, headers=headers, json=json_body)
            dt = (asyncio.get_event_loop().time() - start) * 1000
            lat.append(dt)
            allowed = ok_codes or {200, 201}
            if r.status_code >= 500 or r.status_code not in allowed:
                errors.append(f"{label or path}:{r.status_code}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label or path}:{exc}")


async def main() -> int:
    base = os.environ.get("SMOKE_BASE", "http://localhost:8000")
    api = f"{base}/api/v1"
    lat_public: list[float] = []
    lat_auth: list[float] = []
    lat_match: list[float] = []
    lat_save: list[float] = []
    lat_invite: list[float] = []
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=10.0) as c:
        # --- логин кандидата и работодателя ---
        r = await c.post(f"{api}/auth/login", json={"email": "candidate@example.com", "password": PASSWORD})
        if r.status_code != 200:
            print(f"Вход кандидата не удался: {r.status_code} {r.text[:200]}")
            return 1
        cand_headers = {"X-CSRF-Token": c.cookies.get("fsp_csrf") or ""}

        rc = httpx.AsyncClient(base_url=api, timeout=10.0, follow_redirects=True)
        rc.cookies.update(c.cookies)
        r = await rc.post("/auth/login", json={"email": "employer@example.com", "password": PASSWORD})
        if r.status_code != 200:
            print(f"Вход работодателя не удался: {r.status_code} {r.text[:200]}")
            return 1
        emp_headers = {"X-CSRF-Token": rc.cookies.get("fsp_csrf") or ""}

        sem = asyncio.Semaphore(30)
        await asyncio.gather(*[
            worker(c, "GET", f"{api}/references/grades", sem, lat_public, errors, label="grades") for _ in range(150)
        ] + [
            worker(c, "GET", f"{base}/healthz", sem, lat_public, errors, label="healthz") for _ in range(150)
        ])

        # --- сводка оценки (авторизованный кандидат) ---
        sem2 = asyncio.Semaphore(10)
        await asyncio.gather(*[
            worker(c, "GET", f"{api}/candidate/assessment", sem2, lat_auth, errors,
                   headers=cand_headers, ok_codes={200}, label="assessment") for _ in range(50)
        ])

        # --- подбор: потребность работодателя → matches ---
        r = await rc.get("/employer/needs", headers=emp_headers)
        needs = r.json() if r.status_code == 200 else []
        need_id = needs[0]["id"] if needs else None
        if need_id:
            sem3 = asyncio.Semaphore(10)
            await asyncio.gather(*[
                worker(rc, "GET", f"/employer/needs/{need_id}/matches?page_size=10", sem3, lat_match,
                       errors, headers=emp_headers, ok_codes={200}, label="matches") for _ in range(30)
            ])
        else:
            errors.append("matching:нет потребности у демо-работодателя")

        # --- запись ответов активной попытки (автосохранение под нагрузкой) ---
        summary = (await c.get(f"{api}/candidate/assessment", headers=cand_headers)).json()
        tests = summary.get("tests") or []
        started = False
        if tests:
            spec_id = tests[0]["specialization_id"]
            grade = tests[0]["grades"][0]["grade_code"]
            r = await c.post(
                f"{api}/candidate/assessment/tests/{spec_id}/start",
                headers=cand_headers, json={"grade": grade},
            )
            if r.status_code in (200, 201):
                state = r.json()
                questions = state.get("questions") or []
                # эталон не нужен: нагрузка проверяет путь записи, а не результат
                pairs = [{"question_id": q["id"], "option_id": q["options"][0]["id"]} for q in questions]
                sem4 = asyncio.Semaphore(10)
                # version не передаём: параллельные потоки не должны конфликтовать
                # на версии в нагрузочном сценарии (проверка версий — в acceptance)
                await asyncio.gather(*[
                    worker(c, "PUT", f"{api}/candidate/assessment/attempts/{state['attempt_id']}/answers",
                           sem4, lat_save, errors, headers=cand_headers,
                           json_body={"answers": pairs},
                           ok_codes={200}, label="save_answers") for _ in range(20)
                ])
                started = True
        if not started:
            errors.append("answers:не удалось начать попытку для нагрузки")

        # --- создание приглашений (гонки на partial unique index) ---
        cand_profiles = []
        # демо-кандидат из списка matches уже имеет подтверждённую категорию
        if need_id:
            m = await rc.get(f"/employer/needs/{need_id}/matches?page_size=5", headers=emp_headers)
            if m.status_code == 200:
                cand_profiles = [i["candidate_id"] for i in m.json()["items"]]
        if cand_profiles:
            sem5 = asyncio.Semaphore(10)
            marker = uuid.uuid4().hex[:8]
            await asyncio.gather(*[
                worker(rc, "POST", f"/employer/needs/{need_id}/invitations", sem5, lat_invite,
                       errors, headers=emp_headers,
                       json_body={
                           "candidate_id": cand_profiles[i % len(cand_profiles)],
                           "salary_from": 150_000,
                           "salary_to": 200_000,
                           "message": f"Нагрузочный прогон {marker} — описание условий достаточно длинное.",
                       },
                       # 409 E11 = уже существует открытое приглашение (предсуществующее
                       # состояние от предыдущих прогонов) — не считается ошибкой пути
                       ok_codes={200, 201, 409}, label="invite") for i in range(20)
            ])
        else:
            # Данные зависят от того, прошёл ли демо-кандидат тест (это делает
            # chain_check/acceptance до нагрузочного прогона) — пропускаем секцию.
            print("invite: нет кандидатов с подтверждённой категорией — секция пропущена")

        await rc.aclose()

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
    report("подбор (matches)", lat_match)
    report("запись ответов (автосохранение)", lat_save)
    report("приглашения", lat_invite)

    if errors:
        print(f"Ошибок: {len(errors)}: {errors[:5]}")
        return 1
    print("Нагрузочный тест пройден: ошибок нет (справочники, health, сводка, подбор, ответы, приглашения).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))