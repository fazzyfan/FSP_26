"""invitations: required fields, one open per (company, candidate), contact consent/revoke

Revision ID: 3f6a9c7d3e12
Revises: 2f5a9c7d3e11
Create Date: 2026-10-07 01:00:00.000000

Изменения (Этап 1, FR-23..FR-27):
- message, salary_from, salary_to становятся обязательными (backfill без потери данных);
- вместо ограничения (need, candidate) — одно «открытое» приглашение на пару
  (company, candidate): partial unique index + дедупликация существующих;
- добавляются contacts_consented_at / contacts_revoked_at (согласие и отзыв доступа),
  для ранее принятых приглашений согласие восстанавливается из responded_at;
- CHECK-ограничения положительной вилки и длины описания.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '3f6a9c7d3e12'
down_revision: Union[str, None] = '2f5a9c7d3e11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_MESSAGE = 'Приглашение от компании. Исходные условия зафиксированы.'


def upgrade() -> None:
    # --- дедупликация: одно открытое приглашение на пару (company, candidate) ---
    op.execute(
        """
        UPDATE invitations SET status = 'withdrawn',
               responded_at = COALESCE(responded_at, created_at)
        WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY company_id, candidate_id
                    ORDER BY created_at
                ) AS rn
                FROM invitations
                WHERE status IN ('pending', 'accepted')
            ) dup WHERE rn > 1
        )
        """
    )

    # --- backfill обязательных полей (NFR-08: миграции без потери данных) ---
    op.execute(
        f"UPDATE invitations SET message = '{_DEFAULT_MESSAGE}' "
        "WHERE message IS NULL OR char_length(message) < 10"
    )
    op.execute("UPDATE invitations SET salary_from = 1 WHERE salary_from IS NULL OR salary_from <= 0")
    op.execute("UPDATE invitations SET salary_to = GREATEST(salary_to, salary_from) "
               "WHERE salary_to IS NULL OR salary_to < salary_from")

    op.alter_column('invitations', 'message', existing_type=sa.Text(), nullable=False)
    op.alter_column('invitations', 'salary_from', existing_type=sa.Integer(), nullable=False)
    op.alter_column('invitations', 'salary_to', existing_type=sa.Integer(), nullable=False)

    # --- согласие и отзыв доступа к контактам (FR-27) ---
    op.add_column('invitations', sa.Column('contacts_consented_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('invitations', sa.Column('contacts_revoked_at', sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE invitations SET contacts_consented_at = COALESCE(responded_at, created_at) "
        "WHERE status = 'accepted'"
    )

    # --- одно открытое приглашение от компании кандидату ---
    op.drop_constraint('uq_invitation_need_candidate', 'invitations', type_='unique')
    op.create_index(
        'uq_invitation_open_company_candidate', 'invitations', ['company_id', 'candidate_id'],
        unique=True, postgresql_where=sa.text("status IN ('pending', 'accepted')"),
    )

    # --- проверки целостности условий приглашения ---
    op.create_check_constraint('ck_invitations_salary_from_positive', 'invitations', 'salary_from > 0')
    op.create_check_constraint('ck_invitations_salary_range', 'invitations', 'salary_to >= salary_from')
    op.create_check_constraint('ck_invitations_message_min_length', 'invitations', 'char_length(message) >= 10')


def downgrade() -> None:
    op.drop_constraint('ck_invitations_message_min_length', 'invitations', type_='check')
    op.drop_constraint('ck_invitations_salary_range', 'invitations', type_='check')
    op.drop_constraint('ck_invitations_salary_from_positive', 'invitations', type_='check')
    op.drop_index('uq_invitation_open_company_candidate', table_name='invitations')
    op.create_unique_constraint('uq_invitation_need_candidate', 'invitations', ['need_id', 'candidate_id'])
    op.drop_column('invitations', 'contacts_revoked_at')
    op.drop_column('invitations', 'contacts_consented_at')
    op.alter_column('invitations', 'salary_to', existing_type=sa.Integer(), nullable=True)
    op.alter_column('invitations', 'salary_from', existing_type=sa.Integer(), nullable=True)
    op.alter_column('invitations', 'message', existing_type=sa.Text(), nullable=True)