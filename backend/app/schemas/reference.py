"""Схемы справочников и «о себе»."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class ReferenceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


class ConsentDocOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    version: str
    title: str
    text: str