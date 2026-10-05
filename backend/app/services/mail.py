"""Отправка писем (FR-02). В dev — перехватчик в лог; реальный SMTP при настройке (NFR-07)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger("fsp.mail")


def send_mail(to: str, subject: str, body_text: str) -> None:
    """Отправляет письмо через выбранный бэкенд.

    - backend=log: письмо выводится в журнал API (локальная разработка, NFR-11).
    - backend=smtp: реальная доставка; ошибка не роняет сервис (NFR-07), но и
      не подтверждает аккаунт автоматически.
    """
    settings = get_settings()
    if settings.mail_backend == "smtp":
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = settings.mail_from
            msg["To"] = to
            msg.set_content(body_text)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=5) as server:
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
            logger.info("Письмо отправлено на %s: %s", to, subject)
        except Exception:
            logger.exception("Не удалось отправить письмо на %s (FR-02: доставка не подтверждает аккаунт)", to)
        return

    # Перехватчик для разработки: письмо видно в логе API
    logger.info(
        "\n========== ПИСЬМО (dev) ==========\nTo: %s\nSubject: %s\n\n%s\n==================================",
        to,
        subject,
        body_text,
    )


def confirmation_email(confirm_url: str) -> str:
    return (
        "Здравствуйте!\n\n"
        "Вы зарегистрировались на платформе обратного найма ФСП.\n"
        "Подтвердите адрес электронной почты по ссылке (действует 24 часа):\n\n"
        f"{confirm_url}\n\n"
        "Если вы не регистрировались — проигнорируйте это письмо."
    )