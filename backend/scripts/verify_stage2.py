"""Проверки Этапа 2 «Тестирование и категории» против живого сервера.

Покрывает:
- 4 категории: 2 специализации × 2 грейда, 6 заданий в 3 блоках;
- попытка создаётся на старте с серверным таймером 20 минут;
- ответы сохраняются по мере выбора и восстанавливаются после перезагрузки;
- одна активная попытка; повторная отправка и перезапись завершённой — 409;
- пороги: суммарно >= 70% и >= 50% в каждом блоке;
- просроченная попытка помечается expired (таймер на сервере);
- пересдача той же категории через 24 ч; смена подтверждённой через 90 дней.

Скрипт создаёт собственных кандидатов (без влияния на демо-данные).
Запуск (в контейнере API):
    docker compose exec -T api python scripts/verify_stage2.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

import httpx

# Скрипт запускается из подкаталога scripts/ — нужен корень проекта для импорта app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASSWORD = "DemoPass2026!"

if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _csrf(c: httpx.AsyncClient) -> str:
    return c.cookies.get("fsp_csrf") or ""


async def create_candidate(name: str) -> str:
    """Создаёт кандидата напрямую в БД и возвращает email."""
    from app.core.security import hash_password
    from app.db.base import async_session_factory
    from app.models.account import Account, AccountStatus, Role
    from app.models.candidate import CandidateProfile

    email = f"stage2-{uuid.uuid4().hex[:8]}@example.com"
    now = datetime.now(UTC)
    async with async_session_factory() as session:
        acc = Account(
            email=email, email_normalized=email, password_hash=hash_password(PASSWORD),
            role=Role.CANDIDATE, status=AccountStatus.ACTIVE,
            consent_version="1.0", consent_granted_at=now, confirmed_at=now,
        )
        session.add(acc)
        await session.flush()
        profile = CandidateProfile(
            account_id=acc.id, full_name=f"Этап2 {name}", phone="+7 900 000-00-02",
            experience_months=12, claimed_level_id=None, soft_skills=[],
            about="Автоматическая проверка этапа 2.", is_published=True, show_fsp=False,
        )
        session.add(profile)
        await session.commit()
    return email


async def correct_answers() -> dict[str, str]:
    from sqlalchemy import select

    from app.db.base import async_session_factory
    from app.models.assessment import TestQuestionOption

    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(TestQuestionOption.question_id, TestQuestionOption.id)
                .where(TestQuestionOption.is_correct.is_(True))
            )
        ).all()
        return {str(q): str(o) for q, o in rows}


async def expire_attempt(attempt_id: str) -> None:
    """Переводит попытку в просроченное состояние (имитация истечения таймера)."""
    from datetime import UTC, datetime, timedelta

    from app.db.base import async_session_factory
    from app.models.assessment import TestAttempt

    async with async_session_factory() as session:
        attempt = await session.get(TestAttempt, uuid.UUID(attempt_id))
        if attempt is not None:
            attempt.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()


async def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        status = "OK " if cond else "FAIL"
        print(f"[{status}] {name} {extra}")
        if not cond:
            failures.append(name)

    base = os.environ.get("SMOKE_BASE", "http://localhost:8000") + "/api/v1"

    cand_email = await create_candidate("Проход")
    async with httpx.AsyncClient(base_url=base, timeout=15.0) as c:
        r = await c.post("/auth/login", json={"email": cand_email, "password": PASSWORD})
        if r.status_code != 200:
            print(f"Вход кандидата не удался: {r.status_code} {r.text[:300]}")
            return 1
        csrf = _csrf(c)

        # --- Сводка: 4 категории ---
        r = await c.get("/candidate/assessment")
        summary = r.json()
        tests = {t["specialization_name"]: t for t in summary["tests"]}
        py = tests.get("Python backend")
        sa = tests.get("Системный анализ")
        check("4 категории (2 спец × 2 грейда)",
              py and sa and {g["grade_code"] for g in py["grades"]} == {"junior", "middle"}
              and all(g["questions_count"] == 6 for t in (py, sa) for g in t["grades"]),
              str({k: len(v["grades"]) for k, v in tests.items()}))

        # --- Старт попытки (junior / python) ---
        r = await c.post(f"/candidate/assessment/tests/{py['specialization_id']}/start",
                         headers={"X-CSRF-Token": csrf}, json={"grade": "junior"})
        check("старт попытки", r.status_code == 201, str(r.status_code))
        st = r.json()
        attempt_id = st["attempt_id"]
        qs = st["questions"]
        check("6 заданий, 3 блока по 2",
              len(qs) == 6 and [sum(1 for q in qs if q["block"] == b) for b in (1, 2, 3)] == [2, 2, 2],
              f"{len(qs)} заданий")
        check("серверный таймер 20 минут", 1190 <= st["remaining_seconds"] <= 1200,
              f"{st['remaining_seconds']} c")

        # --- Одна активная попытка: повторный старт возвращает ту же ---
        r2 = await c.post(f"/candidate/assessment/tests/{py['specialization_id']}/start",
                          headers={"X-CSRF-Token": csrf}, json={"grade": "junior"})
        check("повторный старт — та же попытка",
              r2.status_code == 201 and r2.json()["attempt_id"] == attempt_id, str(r2.status_code))

        # --- Сохранение ответов и восстановление ---
        correct = await correct_answers()
        all_correct = [{"question_id": q["id"], "option_id": correct[q["id"]]} for q in qs]
        r = await c.put(f"/candidate/assessment/attempts/{attempt_id}/answers",
                        headers={"X-CSRF-Token": csrf}, json={"answers": all_correct[:5]})
        check("частичное сохранение", r.status_code == 200 and len(r.json()["answers"]) == 5, str(r.status_code))
        r = await c.put(f"/candidate/assessment/attempts/{attempt_id}/answers",
                        headers={"X-CSRF-Token": csrf}, json={"answers": all_correct})
        check("сохранение всех ответов", r.status_code == 200 and len(r.json()["answers"]) == 6, str(r.status_code))

        # восстановление после "перезагрузки"
        r = await c.get(f"/candidate/assessment/attempts/{attempt_id}")
        check("восстановление попытки",
              r.status_code == 200 and len(r.json()["answers"]) == 6 and r.json()["remaining_seconds"] > 0,
              str(r.status_code))

        # --- Отправка: все верно → категория подтверждена ---
        r = await c.post(f"/candidate/assessment/attempts/{attempt_id}/submit",
                         headers={"X-CSRF-Token": csrf})
        check("отправка теста", r.status_code == 200, str(r.status_code))
        result = r.json()
        check("тест пройден (100%)", result["passed"] is True and result["grade_code"] == "junior",
              f"score={result['score_percent']}%")
        check("все блоки 2/2", all(b["correct"] == 2 and b["total"] == 2 for b in result["block_results"]),
              str(result["block_results"]))

        # --- Защита от повторов и перезаписи ---
        r2 = await c.post(f"/candidate/assessment/attempts/{attempt_id}/submit",
                          headers={"X-CSRF-Token": csrf})
        check("повторная отправка 409", r2.status_code == 409, str(r2.status_code))
        r2 = await c.put(f"/candidate/assessment/attempts/{attempt_id}/answers",
                         headers={"X-CSRF-Token": csrf}, json={"answers": all_correct})
        check("перезапись завершённой попытки 409", r2.status_code == 409, str(r2.status_code))

        # --- Категория подтверждена; пересдача той же — кулдаун 24 ч ---
        r = await c.get("/candidate/assessment")
        summary = r.json()
        check("категория в сводке", summary["category"] is not None
              and summary["category"]["grade_code"] == "junior", str(summary.get("category")))
        r2 = await c.post(f"/candidate/assessment/tests/{py['specialization_id']}/start",
                          headers={"X-CSRF-Token": csrf}, json={"grade": "junior"})
        check("пересдача той же категории — кулдаун 409",
              r2.status_code == 409 and "next_allowed_at" in r2.json(), f"{r2.status_code}")
        # смена подтверждённой на другую — 90 дней
        r2 = await c.post(f"/candidate/assessment/tests/{sa['specialization_id']}/start",
                          headers={"X-CSRF-Token": csrf}, json={"grade": "middle"})
        check("смена подтверждённой — кулдаун 90 дней", r2.status_code == 409, f"{r2.status_code}")

        # --- Неполные ответы → 422 ---
        r2 = await c.post(f"/candidate/assessment/tests/{sa['specialization_id']}/start",
                          headers={"X-CSRF-Token": csrf}, json={"grade": "junior"})
        # (смена недоступна — выше проверили; используем второго кандидата ниже)
        check("не создана попытка другой категории (смена заблокирована)", r2.status_code == 409, str(r2.status_code))

    # --- Второй кандидат: неполный набор и порог ниже 70% ---
    fail_email = await create_candidate("Провал")
    async with httpx.AsyncClient(base_url=base, timeout=15.0) as c:
        r = await c.post("/auth/login", json={"email": fail_email, "password": PASSWORD})
        csrf = _csrf(c)
        summary = (await c.get("/candidate/assessment")).json()
        py = next(t for t in summary["tests"] if t["specialization_name"] == "Python backend")

        r = await c.post(f"/candidate/assessment/tests/{py['specialization_id']}/start",
                         headers={"X-CSRF-Token": csrf}, json={"grade": "middle"})
        check("старт попытки (2-й кандидат)", r.status_code == 201, str(r.status_code))
        attempt_id = r.json()["attempt_id"]
        qs = r.json()["questions"]

        # неполный набор ответов → 422
        r2 = await c.post(f"/candidate/assessment/attempts/{attempt_id}/submit",
                          headers={"X-CSRF-Token": csrf})
        check("отправка без ответов 422", r2.status_code == 422, str(r2.status_code))

        # 4 из 6 (67% < 70%), но каждый блок >= 1 — категория НЕ подтверждается
        correct = await correct_answers()
        answers: list[dict] = []
        for idx, q in enumerate(qs):
            opt = correct[q["id"]]
            # ошибаемся в первом вопросе каждого блока, кроме второго блока (там обе верно)
            if q["block"] == 1 and idx % 2 == 0:
                wrong = next(o["id"] for o in q["options"] if o["id"] != opt)
                answers.append({"question_id": q["id"], "option_id": wrong})
            elif q["block"] == 3 and idx % 2 == 0:
                wrong = next(o["id"] for o in q["options"] if o["id"] != opt)
                answers.append({"question_id": q["id"], "option_id": wrong})
            else:
                answers.append({"question_id": q["id"], "option_id": opt})
        r = await c.put(f"/candidate/assessment/attempts/{attempt_id}/answers",
                        headers={"X-CSRF-Token": csrf}, json={"answers": answers})
        check("сохранение частичных ответов (2-й)", r.status_code == 200, str(r.status_code))
        r = await c.post(f"/candidate/assessment/attempts/{attempt_id}/submit",
                         headers={"X-CSRF-Token": csrf})
        result = r.json()
        check("67% при блоках ≥50% — не пройден",
              r.status_code == 200 and result["passed"] is False and result["score_percent"] == 67,
              f"score={result.get('score_percent')}%")
        check("категория не подтверждена",
              (await c.get("/candidate/assessment")).json()["category"] is None)

    # --- Третий кандидат: просроченная попытка ---
    exp_email = await create_candidate("Истёкший")
    async with httpx.AsyncClient(base_url=base, timeout=15.0) as c:
        r = await c.post("/auth/login", json={"email": exp_email, "password": PASSWORD})
        csrf = _csrf(c)
        summary = (await c.get("/candidate/assessment")).json()
        py = next(t for t in summary["tests"] if t["specialization_name"] == "Python backend")
        r = await c.post(f"/candidate/assessment/tests/{py['specialization_id']}/start",
                         headers={"X-CSRF-Token": csrf}, json={"grade": "junior"})
        attempt_id = r.json()["attempt_id"]
        await expire_attempt(attempt_id)
        r = await c.get(f"/candidate/assessment/attempts/{attempt_id}")
        check("просроченная попытка — expired",
              r.status_code == 200 and r.json()["status"] == "expired" and r.json()["remaining_seconds"] == 0,
              f"status={r.json()['status']}")
        r2 = await c.post(f"/candidate/assessment/attempts/{attempt_id}/submit",
                          headers={"X-CSRF-Token": csrf})
        check("отправка просроченной 409", r2.status_code == 409, str(r2.status_code))
        # новая попытка после истечения разрешена
        r3 = await c.post(f"/candidate/assessment/tests/{py['specialization_id']}/start",
                          headers={"X-CSRF-Token": csrf}, json={"grade": "junior"})
        check("новая попытка после истечения", r3.status_code == 201, str(r3.status_code))

    if failures:
        print(f"\nПровалено проверок: {len(failures)}: {failures}")
        return 1
    print("\nЭтап 2 (тестирование и категории): все проверки пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))