"""Проверки случаев из ревью UPD 4 (п.1..п.7) против живого API.

Запуск (в контейнере API):
    docker compose exec -T api python scripts/verify_review.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

PASSWORD = "DemoPass2026!"
BASE = os.environ.get("SMOKE_BASE", "http://localhost:8000") + "/api/v1"


async def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        print(f"[{'OK ' if cond else 'FAIL'}] {name} {extra}")
        if not cond:
            failures.append(name)

    # Сброс тестового состояния демо-кандидата: скрипт идемпотентен и не зависит
    # от кулдаунов (24ч/90д) и приглашений, оставшихся от прошлых прогонов.
    from sqlalchemy import text
    from app.db.base import async_session_factory

    async def reset_candidate_state() -> None:
        """Возврат демо-кандидата в исходное состояние (идемпотентность прогонов)."""
        async with async_session_factory() as db:
            await db.execute(text(
                "DELETE FROM test_attempt_answers WHERE attempt_id IN ("
                "SELECT a.id FROM test_attempts a JOIN candidate_profiles p ON p.id=a.candidate_id "
                "JOIN accounts ac ON ac.id=p.account_id WHERE ac.email_normalized='candidate@example.com')"))
            await db.execute(text(
                "DELETE FROM test_attempts WHERE candidate_id IN ("
                "SELECT p.id FROM candidate_profiles p JOIN accounts ac ON ac.id=p.account_id "
                "WHERE ac.email_normalized='candidate@example.com')"))
            await db.execute(text(
                "DELETE FROM confirmed_categories WHERE candidate_id IN ("
                "SELECT p.id FROM candidate_profiles p JOIN accounts ac ON ac.id=p.account_id "
                "WHERE ac.email_normalized='candidate@example.com')"))
            await db.execute(text(
                "DELETE FROM invitations WHERE candidate_id IN ("
                "SELECT p.id FROM candidate_profiles p JOIN accounts ac ON ac.id=p.account_id "
                "WHERE ac.email_normalized='candidate@example.com')"))
            await db.commit()

    await reset_candidate_state()
    async with async_session_factory() as db:
        cand_id = str((await db.execute(text(
            "SELECT p.id FROM candidate_profiles p JOIN accounts ac ON ac.id=p.account_id "
            "WHERE ac.email_normalized='candidate@example.com'"))).scalar())
        await db.execute(text(
            "DELETE FROM test_attempt_answers WHERE attempt_id IN ("
            "SELECT a.id FROM test_attempts a JOIN candidate_profiles p ON p.id=a.candidate_id "
            "JOIN accounts ac ON ac.id=p.account_id WHERE ac.email_normalized='candidate@example.com')"))
        await db.execute(text(
            "DELETE FROM test_attempts WHERE candidate_id IN ("
            "SELECT p.id FROM candidate_profiles p JOIN accounts ac ON ac.id=p.account_id "
            "WHERE ac.email_normalized='candidate@example.com')"))
        await db.execute(text(
            "DELETE FROM confirmed_categories WHERE candidate_id IN ("
            "SELECT p.id FROM candidate_profiles p JOIN accounts ac ON ac.id=p.account_id "
            "WHERE ac.email_normalized='candidate@example.com')"))
        await db.execute(text(
            "DELETE FROM invitations WHERE candidate_id IN ("
            "SELECT p.id FROM candidate_profiles p JOIN accounts ac ON ac.id=p.account_id "
            "WHERE ac.email_normalized='candidate@example.com')"))
        await db.commit()

    async with httpx.AsyncClient(base_url=BASE, timeout=15.0) as c:
        async def login(email: str) -> str:
            r = await c.post("/auth/login", json={"email": email, "password": PASSWORD})
            assert r.status_code == 200, f"login {email}: {r.status_code}"
            return c.cookies.get("fsp_csrf") or ""

        # ---------- кандидат ----------
        csrf = await login("candidate@example.com")
        h = {"X-CSRF-Token": csrf}
        prof = (await c.get("/candidate/profile")).json()
        cand_full = prof["full_name"]
        roles = {x["name"]: x["id"] for x in (await c.get("/references/roles")).json()}
        skills = {x["name"]: x["id"] for x in (await c.get("/references/skills")).json()}

        async def save_profile(fsp_id: str | None, version: int) -> int:
            r = await c.put("/candidate/profile", headers=h, json={
                "full_name": prof["full_name"], "public_name": prof.get("public_name"),
                "phone": prof["phone"], "experience_months": prof["experience_months"],
                "role_ids": [roles[n] for n in prof["roles"] if n in roles],
                "skill_ids": [skills[n] for n in prof["skills"] if n in skills],
                "claimed_level_id": None, "soft_skills": prof["soft_skills"],
                "about": prof["about"], "is_published": prof["is_published"],
                "show_fsp": True, "fsp_member_id": fsp_id, "version": version,
            })
            return r.status_code

        # П.6: банк >= 9 заданий на категорию, старт даёт 6 (2 на блок)
        summary = (await c.get("/candidate/assessment")).json()
        tests = {t["specialization_name"]: t for t in summary["tests"]}
        check("П.6 банк: 9+ заданий на категорию",
              all(g["questions_count"] >= 9 for t in tests.values() for g in t["grades"]),
              str([(t, [g["questions_count"] for g in v["grades"]]) for t, v in tests.items()]))
        spec = next(iter(tests.values()))["specialization_id"]
        # Грейд из подтверждённой категории (смена категории ограничена 90 днями)
        grade = summary["category"]["grade_code"] if summary.get("category") else "junior"
        r = await c.post(f"/candidate/assessment/tests/{spec}/start", headers=h, json={"grade": grade})
        st = r.json()
        if r.status_code != 200:
            print(f"start: {r.status_code} {st}")
        qs = st["questions"]
        blocks = {b: [q for q in qs if q["block"] == b] for b in (1, 2, 3)}
        check("П.6 старт: 6 заданий, 2 на блок", len(qs) == 6 and all(len(v) == 2 for v in blocks.values()))
        attempt_id = st["attempt_id"]
        version = st["answers_version"]

        # П.1: устаревшая версия -> 409
        r = await c.put(f"/candidate/assessment/attempts/{attempt_id}/answers", headers=h,
                        json={"answers": [{"question_id": qs[0]["id"], "option_id": qs[0]["options"][0]["id"]}],
                              "version": version - 1})
        check("П.1 устаревшая версия -> 409", r.status_code == 409, str(r.status_code))

        # П.1: конкурирующие сохранения с разными версиями — без потери данных
        async def save(q: dict, opt: dict, v: int) -> int:
            r = await c.put(f"/candidate/assessment/attempts/{attempt_id}/answers", headers=h,
                            json={"answers": [{"question_id": q["id"], "option_id": opt["id"]}], "version": v})
            return r.status_code

        results = await asyncio.gather(
            save(qs[0], qs[0]["options"][0], version),
            save(qs[1], qs[1]["options"][1], version),
            save(qs[2], qs[2]["options"][0], version),
        )
        check("П.1 конкурентные сохранения: без 500", all(s < 500 for s in results), str(results))
        st2 = (await c.get(f"/candidate/assessment/attempts/{attempt_id}")).json()
        check("П.1 версия выросла, ответы целы",
              st2["answers_version"] >= version + 1 and len(st2["answers"]) >= 1,
              f"v={st2['answers_version']} answers={len(st2['answers'])}")

        # П.2: вариант из другого вопроса -> 422
        r = await c.put(f"/candidate/assessment/attempts/{attempt_id}/answers", headers=h,
                        json={"answers": [{"question_id": qs[0]["id"], "option_id": qs[1]["options"][0]["id"]}],
                              "version": st2["answers_version"]})
        check("П.2 чужой вариант -> 422", r.status_code == 422, str(r.status_code))

        # П.2: неполные ответы -> 422; полные -> submit; повторный submit восстанавливает результат
        r = await c.post(f"/candidate/assessment/attempts/{attempt_id}/submit", headers=h)
        check("П.2 неполные ответы -> 422", r.status_code == 422, str(r.status_code))
        st3 = (await c.get(f"/candidate/assessment/attempts/{attempt_id}")).json()
        v = st3["answers_version"]
        # Эталоны читаем из БД (тест-скрипт): отвечаем верно, чтобы кандидат
        # подтвердил категорию — она нужна для сценария приглашения (П.3).
        from sqlalchemy import select
        from app.models.assessment import TestQuestionOption
        async with async_session_factory() as db:
            rows = (await db.execute(
                select(TestQuestionOption.question_id, TestQuestionOption.id)
                .where(TestQuestionOption.question_id.in_([q["id"] for q in st3["questions"]]),
                       TestQuestionOption.is_correct.is_(True))
            )).all()
        correct = {str(q): str(o) for q, o in rows}
        for q in st3["questions"]:
            r = await c.put(f"/candidate/assessment/attempts/{attempt_id}/answers", headers=h,
                            json={"answers": [{"question_id": q["id"], "option_id": correct[q["id"]]}],
                                  "version": v})
            v = r.json()["answers_version"]
        r1 = await c.post(f"/candidate/assessment/attempts/{attempt_id}/submit", headers=h)
        check("П.2 submit полных ответов", r1.status_code == 200, str(r1.status_code))
        r2 = await c.post(f"/candidate/assessment/attempts/{attempt_id}/submit", headers=h)
        check("П.1 повторный submit восстанавливает результат",
              r2.status_code == 200 and r2.json()["score_percent"] == r1.json()["score_percent"])

        # П.5: известный ID -> достижения, неизвестный -> пусто
        check("П.5 известный ID: 3 достижения",
              await save_profile("FSP-2026-0001", prof["version"]) == 200 and
              len((await c.get("/candidate/fsp/achievements")).json()["achievements"]) == 3)
        check("П.5 неизвестный ID: без достижений",
              await save_profile("UNKNOWN-999", prof["version"] + 1) == 200 and
              len((await c.get("/candidate/fsp/achievements")).json()["achievements"]) == 0)

        # ---------- работодатель ----------
        await c.post("/auth/logout")
        csrf_e = await login("employer@example.com")
        he = {"X-CSRF-Token": csrf_e}
        needs = (await c.get("/employer/needs")).json()
        need = needs[0]
        matches = (await c.get(f"/employer/needs/{need['id']}/matches")).json()["items"]
        check("П.4 подбор: объяснение компетенций вакансии",
              any("Компетенции вакансии" in r for m in matches for r in m["reasons"]),
              str([r for m in matches[:1] for r in m["reasons"]]))
        if matches:
            my_match = next((m for m in matches if m["candidate_id"] == str(cand_id)), None)
            check("П.3 подбор: публичное имя вместо ФИО",
                  my_match is not None and my_match["full_name"] != cand_full,
                  my_match["full_name"] if my_match else "нет в подборе")
            inv = (await c.post(f"/employer/needs/{need['id']}/invitations", headers=he, json={
                "candidate_id": cand_id, "salary_from": 100000, "salary_to": 150000,
                "message": "Приглашаем на позицию backend-разработчика."})).json()
            check("П.3 до согласия: публичное имя в приглашении",
                  inv["candidate_name"] != cand_full, inv["candidate_name"])
            need2 = needs[1] if len(needs) > 1 else need
            r = await c.post(f"/employer/needs/{need2['id']}/invitations", headers=he, json={
                "candidate_id": cand_id, "salary_from": 100000, "salary_to": 150000,
                "message": "Приглашаем на позицию backend-разработчика."})
            check("П.3 повтор с другим need_id -> 409", r.status_code == 409, str(r.status_code))
            # П.3: одновременные accept и withdraw — один 200, другой 409
            await c.post("/auth/logout")
            csrf = await login("candidate@example.com")
            h = {"X-CSRF-Token": csrf}
            r_acc = await c.post(f"/candidate/invitations/{inv['id']}/respond", headers=h, json={"decision": "accept"})
            await c.post("/auth/logout")
            csrf_e = await login("employer@example.com")
            he = {"X-CSRF-Token": csrf_e}
            r_wd = await c.post(f"/employer/invitations/{inv['id']}/withdraw", headers=he)
            check("П.3 accept+withdraw: один успех, один 409",
                  (r_acc.status_code == 200 and r_wd.status_code == 409) or
                  (r_acc.status_code == 409 and r_wd.status_code == 200),
                  f"accept={r_acc.status_code} withdraw={r_wd.status_code}")
            if r_acc.status_code == 200:
                invs = (await c.get("/employer/invitations")).json()
                acc = next(i for i in invs if i["id"] == inv["id"])
                check("П.3 после согласия: полное ФИО", acc["candidate_name"] == cand_full, acc["candidate_name"])

        # ---------- П.7: целостность БД ----------
        from sqlalchemy import text
        from app.db.base import async_session_factory
        async with async_session_factory() as db:
            dup = (await db.execute(text(
                "SELECT candidate_id, count(*) FROM test_attempts WHERE status='in_progress' "
                "GROUP BY candidate_id HAVING count(*)>1"))).all()
            check("П.7 нет дублей активных попыток", not dup, str(dup))
            orphan = (await db.execute(text(
                "SELECT count(*) FROM test_attempt_answers a LEFT JOIN test_attempts t ON t.id=a.attempt_id "
                "WHERE t.id IS NULL"))).scalar()
            check("П.7 нет ответов без попытки", orphan == 0, str(orphan))
            pub = (await db.execute(text(
                "SELECT count(*) FROM candidate_profiles p JOIN accounts ac ON ac.id=p.account_id "
                "WHERE ac.email_normalized='candidate@example.com' AND p.public_name IS NULL"))).scalar()
            check("П.7 public_name демо-кандидата заполнен", pub == 0, str(pub))

    await reset_candidate_state()

    print("\n" + "=" * 50)
    if failures:
        print(f"ПРОВЕРКИ РЕВЬЮ: {len(failures)} упало: {failures}")
        return 1
    print("ПРОВЕРКИ РЕВЬЮ: все случаи зелёные.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))