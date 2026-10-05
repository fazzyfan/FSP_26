"""Пакет моделей. Импортируются в Alembic env и seed."""

from app.models.account import Account, AccountStatus, AuthSession, ConsentDoc, ConsentEvent, ConsentType, Role
from app.models.candidate import CandidateProfile
from app.models.employer import Company, EmployerNeed
from app.models.reference import Grade, Industry, RoleRef, Skill, Specialization

__all__ = [
    "Account",
    "AccountStatus",
    "AuthSession",
    "CandidateProfile",
    "Company",
    "ConsentDoc",
    "ConsentEvent",
    "ConsentType",
    "EmployerNeed",
    "Grade",
    "Industry",
    "Role",
    "RoleRef",
    "Skill",
    "Specialization",
]