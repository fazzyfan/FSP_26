"""Smoke-тест основного пути API — быстро, без внешнего сервера (ASGITransport).

Запуск (нужна настроенная БД, см. README):
    set FSP_DATABASE_URL=postgresql+asyncpg://fsp:fsp@localhost:5433/fsp
    python scripts/smoke_test.py

Проверка против живого сервера:
    set SMOKE_BASE=http://localhost:8000
    python scripts/smoke_test.py

Покрывает FR-01..FR-05, FR-16, FR-17 и базовые права (FR-03, NFR-01).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import httpx

PASSWORD = "DemoPass2026!"

# Консоль Windows (cp1252) не выводит кириллицу — переключаемся на UTF-8
if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        status = "OK " if cond else "FAIL"
        print(f"[{status}] {name} {extra}")
        if not cond:
            failures.append(name)

    base_url = os.environ.get("SMOKE_BASE")
    if base_url:
        client_kwargs: dict = {"base_url": f"{base_url}/api/v1"}
    else:
        os.environ.setdefault(
            "FSP_DATABASE_URL", "postgresql+asyncpg://fsp:fsp@localhost:5433/fsp"
        )
        from app.main import app

        client_kwargs = {"base_url": "http://test/api/v1", "transport": httpx.ASGITransport(app=app)}

    async with httpx.AsyncClient(**client_kwargs, timeout=10.0) as c:
        # Публичные справочники
        r = await c.get("/references/grades")
        check("справочник грейдов", r.status_code == 200 and len(r.json()) >= 2, str(r.status_code))
        r = await c.get("/references/consents")
        check(
            "тексты согласий",
            r.status_code == 200 and any(d["code"] == "data_processing" for d in r.json()),
        )

        # Доступ без сессии закрыт
        r = await c.get("/auth/session")
        check("без сессии 401", r.status_code == 401, str(r.status_code))
        r = await c.get("/candidate/profile")
        check("кабинет без сессии 401", r.status_code == 401, str(r.status_code))

        # Вход кандидата (демо)
        r = await c.post("/auth/login", json={"email": "candidate@example.com", "password": PASSWORD})
        check("вход кандидата", r.status_code == 200 and r.json()["role"] == "candidate", str(r.status_code))
        csrf = c.cookies.get("fsp_csrf") or ""

        r = await c.get("/me")
        check("me кандидата", r.status_code == 200 and r.json()["role"] == "candidate")

        refs = {x["code"]: x["id"] for x in (await c.get("/references/roles")).json()}
        skills = {x["code"]: x["id"] for x in (await c.get("/references/skills")).json()}
        grades = {x["code"]: x["id"] for x in (await c.get("/references/grades")).json()}

        # Профиль кандидата: используем текущую версию записи (идемпотентность прогона)
        cur = await c.get("/candidate/profile")
        version = 1 if (cur.status_code == 200 and cur.json() is None) else cur.json()["version"]
        r = await c.put(
            "/candidate/profile",
            headers={"X-CSRF-Token": csrf},
            json={
                "full_name": "Иван Тестов",
                "phone": "+7 900 123-45-67",
                "experience_months": 24,
                "role_ids": [refs["backend_dev"]],
                "skill_ids": [skills["python"], skills["fastapi"]],
                "claimed_level_id": grades["junior"],
                "soft_skills": ["Коммуникабельность"],
                "about": "Smoke-профиль для проверки API.",
                "is_published": True,
                "show_fsp": False,
                "fsp_member_id": None,
                "version": version,
            },
        )
        check("сохранение профиля", r.status_code == 200 and r.json()["full_name"] == "Иван Тестов", str(r.status_code))

        # CSRF обязателен для изменяющих запросов
        r = await c.put("/candidate/profile", json={**r.json(), "version": r.json()["version"]})
        check("без CSRF 403", r.status_code == 403, str(r.status_code))

        # Кабинет работодателя недоступен кандидату
        r = await c.get("/employer/company")
        check("доступ по роли 403", r.status_code == 403, str(r.status_code))

        # Выход инвалидирует сессию
        r = await c.post("/auth/logout")
        check("выход", r.status_code == 204, str(r.status_code))
        r = await c.get("/auth/session")
        check("сессия после выхода 401", r.status_code == 401, str(r.status_code))

        # Вход работодателя
        r = await c.post("/auth/login", json={"email": "employer@example.com", "password": PASSWORD})
        check("вход работодателя", r.status_code == 200 and r.json()["role"] == "employer", str(r.status_code))
        csrf = c.cookies.get("fsp_csrf") or ""

        industries = {x["code"]: x["id"] for x in (await c.get("/references/industries")).json()}
        cur_company = (await c.get("/employer/company")).json()
        company_version = 1 if cur_company is None else cur_company["version"]
        r = await c.put(
            "/employer/company",
            headers={"X-CSRF-Token": csrf},
            json={
                "name": "ООО Смоук",
                "industry_id": industries["it"],
                "description": "Проверочная компания для smoke-теста API.",
                "contact_email": "employer@example.com",
                "website": None,
                "phone": None,
                "version": company_version,
            },
        )
        if r.status_code != 200:
            print("  >> тело ошибки компании:", r.text[:500])
        check("сохранение компании", r.status_code == 200 and r.json()["name"] == "ООО Смоук", str(r.status_code))

        specializations = {x["code"]: x["id"] for x in (await c.get("/references/specializations")).json()}
        r = await c.post(
            "/employer/needs",
            headers={"X-CSRF-Token": csrf},
            json={
                "title": "Backend-разработчик на Python",
                "tasks_text": "Развивать сервис на FastAPI: API, модели данных, интеграции с внешними системами.",
                "industry_id": industries["it"],
                "specialization_id": specializations["python_backend"],
                "grade_ids": [grades["junior"], grades["middle"]],
                "skill_ids": [skills["python"], skills["fastapi"]],
            },
        )
        check("создание потребности", r.status_code == 201, str(r.status_code))

        # Чужой/несуществующий объект — единый 404
        r = await c.get(f"/employer/needs/{uuid.UUID(int=0)}")
        check("чужая потребность 404", r.status_code == 404, str(r.status_code))

        # Регистрация нового аккаунта (согласие) + дубль email
        email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "email": email,
            "password": "StrongPass2026!",
            "role": "candidate",
            "consent_version": "1.0",
            "consent_granted": True,
        }
        r = await c.post("/auth/register", json=payload)
        check("регистрация", r.status_code == 201 and r.json()["status"] == "pending_email", str(r.status_code))
        r = await c.post("/auth/register", json=payload)
        check("дубль email 409", r.status_code == 409, str(r.status_code))

        # Невалидный ввод: короткий пароль -> 422 с ошибкой поля
        r = await c.post(
            "/auth/register",
            json={**payload, "email": f"short-{uuid.uuid4().hex[:6]}@example.com", "password": "short"},
        )
        check("короткий пароль 422", r.status_code == 422 and any(e["field"] == "password" for e in r.json()["errors"]), str(r.status_code))

    if failures:
        print(f"\nПровалено проверок: {len(failures)}: {failures}")
        return 1
    print("\nВсе проверки пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))