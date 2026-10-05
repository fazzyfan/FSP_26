"""Единый ответ об ошибке по RFC 9457 (каталог ошибок, ER-01, FR-30).

Формат Problem Details с расширениями команды:
type, title, status, code, error_class (E01..E20), detail,
errors[], request_id, recovery.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import get_settings

# Классы каталога ошибок
E01_REQUIRED = "E01"
E02_FORMAT = "E02"
E03_RANGE = "E03"
E04_REFERENCE = "E04"
E05_PARSE = "E05"
E06_UNAVAILABLE = "E06"
E07_WRITE = "E07"
E08_AUTH = "E08"
E09_ACCESS = "E09"
E10_UNSAFE = "E10"
E11_CONCURRENCY = "E11"
E12_STATE = "E12"
E13_TIME = "E13"
E14_STALE = "E14"
E15_CALC = "E15"
E16_CONTENT = "E16"
E17_RENDER = "E17"
E18_LIMIT = "E18"
E19_CONFIG = "E19"
E20_INTERNAL = "E20"

# Коды API
VALIDATION_FAILED = "VALIDATION_FAILED"
EMAIL_UNCONFIRMED = "EMAIL_UNCONFIRMED"
TOKEN_INVALID = "TOKEN_INVALID"
LOGIN_FAILED = "LOGIN_FAILED"
AUTH_REQUIRED = "AUTH_REQUIRED"
CSRF_FAILED = "CSRF_FAILED"
RATE_LIMITED = "RATE_LIMITED"
RESOURCE_NOT_AVAILABLE = "RESOURCE_NOT_AVAILABLE"
ACCESS_DENIED = "ACCESS_DENIED"
CONFLICT = "CONFLICT"
INTERNAL_ERROR = "INTERNAL_ERROR"
EMAIL_ALREADY_REGISTERED = "EMAIL_ALREADY_REGISTERED"
INVALID_STATE = "INVALID_STATE"


class Problem(Exception):
    """Исключение Problem Details; выбрасывается бизнес-слоем."""

    def __init__(
        self,
        status_code: int,
        code: str,
        error_class: str | None,
        title: str,
        detail: str | None = None,
        errors: list[dict[str, str]] | None = None,
        recovery: str = "none",
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.error_class = error_class
        self.title = title
        self.detail = detail
        self.errors = errors or []
        self.recovery = recovery
        self.extra = extra or {}
        super().__init__(title)


def problem_response(
    problem: Problem,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"urn:northfox:problem:{problem.code.lower()}",
        "title": problem.title,
        "status": problem.status_code,
        "code": problem.code,
        "error_class": problem.error_class,
        "detail": problem.detail,
        "errors": problem.errors,
        "request_id": request_id,
        "recovery": problem.recovery,
    }
    body.update(problem.extra)
    return JSONResponse(status_code=problem.status_code, content=body, headers=headers)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def register_error_handlers(app: FastAPI) -> None:
    """Подключает обработчики Problem, ошибок валидации и необработанных исключений."""

    @app.exception_handler(Problem)
    async def problem_handler(request: Request, exc: Problem) -> JSONResponse:
        return problem_response(exc, request_id=_request_id(request))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors: list[dict[str, str]] = []
        for err in exc.errors():
            field = ".".join(str(p) for p in err.get("loc", []) if p not in ("body", "query", "path"))
            code = err.get("type", "TYPE_MISMATCH").upper()
            errors.append(
                {
                    "field": field,
                    "code": code,
                    "error_class": E01_REQUIRED if code == "MISSING" else E02_FORMAT,
                    "message": err.get("msg", "Некорректное значение поля"),
                }
            )
        problem = Problem(
            status_code=422,  # HTTP 422 Unprocessable Content (имя-константа устарело в Starlette)
            code=VALIDATION_FAILED,
            error_class=None,  # несколько классов в errors[]
            title="Проверьте заполнение формы",
            detail="Исправьте отмеченные поля.",
            errors=errors,
            recovery="correct_input",
        )
        return problem_response(problem, request_id=_request_id(request))

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        settings = get_settings()
        if settings.debug:
            import logging

            logging.getLogger(__name__).exception("Unhandled error", exc_info=exc)
        problem = Problem(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=INTERNAL_ERROR,
            error_class=E20_INTERNAL,
            title="Внутренняя ошибка сервера",
            detail="Произошла непредвиденная ошибка. Повторите запрос позже.",
            recovery="contact_support",
        )
        return problem_response(problem, request_id=_request_id(request))