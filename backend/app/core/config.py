"""Конфигурация приложения через переменные окружения (12-factor)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки сервиса. Секреты — только из окружения (NFR-02).

    Все переменные окружения имеют префикс FSP_ (например FSP_DATABASE_URL),
    чтобы не конфликтовать с системными переменными (DEBUG, PATH и т.п.).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="FSP_",
        extra="ignore",
    )

    app_name: str = "FSP обратный найм"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # База данных
    database_url: str = "postgresql+asyncpg://fsp:fsp@db:5432/fsp"

    # Сессии (NFR-02: HttpOnly cookie, SameSite, срок <= 24 ч, D-06)
    session_cookie_name: str = "fsp_session"
    csrf_cookie_name: str = "fsp_csrf"
    session_ttl_seconds: int = 86400
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    # Почта (FR-02): backend=log | smtp
    mail_backend: str = "log"
    smtp_host: str = ""
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = "FSP Platform <noreply@fsp.local>"
    confirm_base_url: str = "http://localhost:5173/confirm-email"

    # Лимиты (FR-02, FR-01)
    confirm_token_ttl_seconds: int = 86400  # 24 часа
    resend_cooldown_seconds: int = 60       # не чаще 1 письма в минуту
    password_min_length: int = 12
    password_max_length: int = 128

    # Тест и категория (D-02..D-06, FR-08..FR-13)
    test_pass_junior_percent: int = 50   # порог подтверждения Junior
    test_pass_middle_percent: int = 70   # порог подтверждения Middle
    test_retry_failed_hours: int = 24    # повтор после неуспешной попытки
    test_retry_success_days: int = 90    # повтор после успешной попытки

    # CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()