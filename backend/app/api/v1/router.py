"""Сборка роутеров API v1."""

from fastapi import APIRouter

from app.api.v1 import accounts, auth, candidate, employer, references

router = APIRouter()
router.include_router(auth.router)
router.include_router(accounts.router)
router.include_router(candidate.router)
router.include_router(employer.router)
router.include_router(references.router)