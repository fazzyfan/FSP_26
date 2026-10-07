"""Генерация PDF-профиля кандидата (FR-06).

Разрешение на контакты проверяется единой функцией contacts_service.require_contacts:
PDF не выдаёт контакты без явного согласия кандидата (FR-27).
Кириллица — шрифт DejaVuSans (устанавливается в образе API).
"""

from __future__ import annotations

import io
import uuid

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.models.assessment import ConfirmedCategory, TestAttempt
from app.models.candidate import CandidateProfile

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _register_font() -> None:
    try:
        pdfmetrics.registerFont(TTFont("DejaVu", FONT_PATH))
    except Exception:
        # fallback: стандартный шрифт (латиница), кириллица заменяется '?'
        pass


def build_profile_pdf(
    profile: CandidateProfile,
    category: ConfirmedCategory | None,
    attempts: list[TestAttempt],
    *,
    include_contacts: bool,
    fsp_achievements: list[str] | None = None,
) -> bytes:
    """Формирует байты PDF-файла профиля кандидата."""
    _register_font()
    buf = io.BytesIO()
    doc = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 20 * mm
    y = height - margin

    font_name = "DejaVu"
    try:
        pdfmetrics.getFont(font_name)
    except Exception:
        font_name = "Helvetica"

    def line(text: str, size: int = 10, bold: bool = False, gap: int = 6) -> None:
        nonlocal y
        doc.setFont(font_name, size)
        doc.drawString(margin, y, text[:110])
        y -= gap + size

    def safe_label(value: str | None) -> str:
        return value or "—"

    line("Профиль кандидата — ФСП", 16, gap=10)
    line(f"ФИО: {safe_label(profile.full_name)}", bold=True)
    if include_contacts:
        line(f"Телефон: {safe_label(profile.phone)}")
        line(f"Email: {profile.account.email if profile.account else '—'}")
    else:
        line("Контакты: скрыты (нет согласия работодателю на доступ)")
    line(f"Стаж: {profile.experience_months} мес.")
    line(f"О себе: {safe_label(profile.about)}")
    y -= 6 * mm

    line("Подтверждённая категория", 12, bold=True, gap=8)
    if category is not None:
        line(f"Специализация: {category.specialization.name}")
        line(f"Грейд: {category.grade.name} (подтверждён {category.confirmed_at.strftime('%d.%m.%Y %H:%M')})")
    else:
        line("Категория не подтверждена")
    y -= 6 * mm

    line("Навыки", 12, bold=True, gap=8)
    skills = ", ".join(s.name for s in profile.skills) or "—"
    line(skills, size=9)
    y -= 6 * mm

    line("Результаты теста", 12, bold=True, gap=8)
    if attempts:
        for a in attempts[:5]:
            grade = a.result_grade.name if a.result_grade else "не пройден"
            line(
                f"{a.specialization.name}: {a.score_percent}% ({a.correct_count}/{a.total_count}) — {grade}",
                size=9,
            )
    else:
        line("Попыток нет", size=9)
    y -= 6 * mm

    line("Достижения ФСП", 12, bold=True, gap=8)
    if fsp_achievements:
        for title in fsp_achievements:
            line(f"• {title}", size=9)
    else:
        line("Достижения ФСП не указаны", size=9)

    doc.save()
    return buf.getvalue()