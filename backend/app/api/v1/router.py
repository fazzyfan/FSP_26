"""Сборка роутеров API v1."""

from fastapi import APIRouter

from app.api.v1 import (
    accounts,
    assessment,
    auth,
    candidate,
    consents,
    employer,
    fsp,
    invitations,
    matching,
    pdf,
    references,
)

router = APIRouter()
router.include_router(auth.router)
router.include_router(accounts.router)
router.include_router(candidate.router)
router.include_router(employer.router)
router.include_router(references.router)
router.include_router(assessment.router)
router.include_router(matching.router)
router.include_router(invitations.router)
router.include_router(pdf.router)
router.include_router(consents.router)
router.include_router(fsp.router)