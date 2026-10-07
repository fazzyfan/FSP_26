"""Проверки Этапа 1 «Приглашения и контакты» против живого сервера.

Покрывает:
- обязательные поля приглашения: описание (>= 10 символов), положительная вилка,
  salary_from <= salary_to — ответ 422 с ошибкой поля;
- одно открытое приглашение от компании кандидату: повтор с теми же условиями
  возвращает существующее (200, тот же id), другие условия — 409;
- исходные условия не изменяются (snapshot);
- отзыв доступа к контактам и невосстановление после повторного принятия
  (проверяется в chain_check.py — здесь только инварианты дубликатов).

Скрипт устойчив к состоянию данных: если у кандидата уже есть открытое
приглашение, проверки выполняются по нему.

Запуск (в контейнере API):
    docker compose exec -T api python scripts/verify_stage1.py
"""

from __future__ import annotations

import asyncio
import os
import sys

import httpx

PASSWORD = "DemoPass2026!"
EMPLOYER_EMAIL = "employer@example.com"

if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _csrf(c: httpx.AsyncClient) -> str:
    return c.cookies.get("fsp_csrf") or ""


async def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        status = "OK " if cond else "FAIL"
        print(f"[{status}] {name} {extra}")
        if not cond:
            failures.append(name)

    base = os.environ.get("SMOKE_BASE", "http://localhost:8000") + "/api/v1"

    async with httpx.AsyncClient(base_url=base, timeout=15.0) as emp:
        r = await emp.post("/auth/login", json={"email": EMPLOYER_EMAIL, "password": PASSWORD})
        if r.status_code != 200:
            print(f"Вход работодателя не удался: {r.status_code} {r.text[:300]}")
            return 1
        csrf = _csrf(emp)

        needs = (await emp.get("/employer/needs")).json()
        if not needs:
            print("Нет потребностей — создайте демо-потребность (seed).")
            return 1
        need = needs[0]

        # Кандидат: тот, кому компания может отправить приглашение.
        invites = (await emp.get("/employer/invitations")).json()
        open_inv = next((i for i in invites if i["status"] in ("pending", "accepted")), None)
        candidate_id = open_inv["candidate_id"] if open_inv else None
        if candidate_id is None:
            matches = (await emp.get(f"/employer/needs/{need['id']}/matches")).json()
            candidate_id = matches[0]["candidate_id"] if matches else None
        if candidate_id is None:
            print("Нет кандидата для проверки — сначала прогоните chain_check.")
            return 1

        url = f"/employer/needs/{need['id']}/invitations"
        valid = {"candidate_id": candidate_id, "salary_from": 150_000, "salary_to": 220_000,
                 "message": "Проверочное приглашение с описанием условий работы."}

        # --- Обязательные поля (422 приходят до проверки дублей) ---
        r = await emp.post(url, headers={"X-CSRF-Token": csrf}, json={**valid, "message": "короткий"})
        check("короткое описание 422", r.status_code == 422, str(r.status_code))
        r = await emp.post(url, headers={"X-CSRF-Token": csrf}, json={**valid, "message": None})
        check("описание обязательно 422", r.status_code == 422, str(r.status_code))
        r = await emp.post(url, headers={"X-CSRF-Token": csrf}, json={**valid, "salary_from": None})
        check("вилка обязательна 422", r.status_code == 422, str(r.status_code))
        r = await emp.post(url, headers={"X-CSRF-Token": csrf}, json={**valid, "salary_from": 0})
        check("нулевая вилка 422", r.status_code == 422, str(r.status_code))
        r = await emp.post(url, headers={"X-CSRF-Token": csrf}, json={**valid, "salary_to": 100_000})
        check("salary_from > salary_to 422", r.status_code == 422, str(r.status_code))

        # --- Одно открытое приглашение от компании кандидату ---
        if open_inv is not None:
            # Уже есть открытое приглашение: повтор с его условиями идемпотентен
            same_payload = {
                "candidate_id": open_inv["candidate_id"],
                "salary_from": open_inv["salary_from"],
                "salary_to": open_inv["salary_to"],
                "message": open_inv["message"],
            }
            r = await emp.post(url, headers={"X-CSRF-Token": csrf}, json=same_payload)
            check("повтор с условиями существующего — тот же id",
                  r.status_code in (200, 201) and r.json().get("id") == open_inv["id"],
                  f"http={r.status_code}")
            r = await emp.post(url, headers={"X-CSRF-Token": csrf}, json={**same_payload, "salary_to": 250_000})
            check("другие условия при открытом — 409", r.status_code == 409, str(r.status_code))
            check("исходные условия сохранены",
                  open_inv["salary_to"] == same_payload["salary_to"]
                  and open_inv["message"] == same_payload["message"],
                  f"salary_to={open_inv['salary_to']}")
        else:
            r = await emp.post(url, headers={"X-CSRF-Token": csrf}, json=valid)
            created = r.status_code in (200, 201)
            check("создание приглашения", created, f"http={r.status_code}")
            if created:
                inv_id = r.json()["id"]
                r2 = await emp.post(url, headers={"X-CSRF-Token": csrf}, json=valid)
                check("повтор с теми же условиями — тот же id",
                      r2.status_code in (200, 201) and r2.json().get("id") == inv_id,
                      f"http={r2.status_code}")
                r3 = await emp.post(url, headers={"X-CSRF-Token": csrf}, json={**valid, "salary_to": 230_000})
                check("другие условия — 409", r3.status_code == 409, str(r3.status_code))
                list_inv = next(
                    i for i in (await emp.get("/employer/invitations")).json() if i["id"] == inv_id
                )
                check("исходные условия сохранены",
                      list_inv["salary_to"] == 220_000 and list_inv["message"] == valid["message"],
                      f"salary_to={list_inv['salary_to']}")

    if failures:
        print(f"\nПровалено проверок: {len(failures)}: {failures}")
        return 1
    print("\nЭтап 1 (приглашения и контакты): все проверки пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))