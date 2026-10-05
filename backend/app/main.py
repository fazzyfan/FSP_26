"""Точка входа FastAPI: middleware request_id, CORS, обработчики ошибок, OpenAPI."""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers

logger = logging.getLogger("fsp")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Платформа обратного найма ФСП (MVP). "
        "Формат ошибок — Problem Details (RFC 9457) с классами E01–E20."
    ),
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """NFR-13: request_id для диагностики; не является правом доступа."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/healthz", tags=["system"])
async def healthz() -> dict:
    """Readiness-проверка (E19: сервис готов после миграций)."""
    return {"status": "ok", "service": "fsp-backend", "version": "0.1.0"}