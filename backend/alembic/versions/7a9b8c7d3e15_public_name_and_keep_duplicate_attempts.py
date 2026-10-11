"""candidate public_name; keep duplicate attempts (close by rule, no delete)

Revision ID: 7a9b8c7d3e15
Revises: 6b8a9c7d3e14
Create Date: 2026-10-11 10:00:00.000000

Изменения (UPD 4, п.3 и п.7):
- candidate_profiles.public_name: согласованное публичное имя, показываемое
  работодателям до согласия кандидата на открытие контактов (FR-27);
  по умолчанию выводится из ФИО («Имя Ф.»);
- защитное закрытие оставшихся дублей активных попыток по явному правилу
  (expired, ответы сохраняются) — для баз, где миграция 6b8a9c7d3e14 уже
  применялась с DELETE, и для свежих баз как страховка.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '7a9b8c7d3e15'
down_revision: Union[str, None] = '6b8a9c7d3e14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('candidate_profiles', sa.Column('public_name', sa.String(150), nullable=True))
    op.execute(
        """
        UPDATE candidate_profiles
        SET public_name = CASE
            WHEN full_name ~ ' ' THEN split_part(full_name, ' ', 1) || ' ' ||
                 left(split_part(full_name, ' ', 2), 1) || '.'
            ELSE full_name
        END
        WHERE public_name IS NULL
        """
    )

    # П.7: лишние активные попытки закрываются (expired), а не удаляются —
    # ответы и история сохраняются. Остаётся самая свежая in_progress.
    op.execute(
        """
        UPDATE test_attempts a SET status = 'expired',
               submitted_at = COALESCE(a.expires_at, a.started_at + INTERVAL '20 minutes')
        FROM test_attempts b
        WHERE a.candidate_id = b.candidate_id AND a.status = 'in_progress'
          AND b.status = 'in_progress'
          AND (a.started_at < b.started_at OR (a.started_at = b.started_at AND a.id < b.id))
        """
    )


def downgrade() -> None:
    op.drop_column('candidate_profiles', 'public_name')