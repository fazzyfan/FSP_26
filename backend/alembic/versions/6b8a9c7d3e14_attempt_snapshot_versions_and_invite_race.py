"""assessment: attempt snapshot, answers version, one-active-attempt DB guard; invitations: revoked contacts unblock new invite

Revision ID: 6b8a9c7d3e14
Revises: 4a7b9c7d3e13
Create Date: 2026-10-07 23:00:00.000000

Изменения (Этап 5, NFR-06 / автосохранение / приёмка):
- test_attempts.questions_snapshot (JSONB): снимок заданий и эталонов на момент
  старта попытки — банк вопросов можно менять без искажения старых попыток;
- test_attempts.answers_version (int): версия сохранённых ответов; запоздалый
  запрос автосохранения с устаревшей версией отклоняется (409), а не затирает
  новый выбор;
- partial unique index uq_test_attempts_active_candidate: одна активная
  (in_progress) попытка на кандидата гарантируется на уровне БД — параллельные
  старты больше не создают две активные попытки;
- invitations: частичный уникальный индекс открытых приглашений теперь
  исключает accepted-приглашения с отозванными контактами — после отзыва
  доступа новое предложение той же компании не блокируется.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '6b8a9c7d3e14'
down_revision: Union[str, None] = '4a7b9c7d3e13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- попытки: снимок заданий + версия ответов ---
    op.add_column('test_attempts', sa.Column('questions_snapshot', JSONB(), nullable=True))
    op.add_column('test_attempts', sa.Column('answers_version', sa.Integer(), nullable=False, server_default='0'))
    op.alter_column('test_attempts', 'answers_version', existing_type=sa.Integer(), nullable=False,
                    server_default=None)

    # Одна активная попытка на кандидата (NFR-06): дубликаты не создаются даже
    # при одновременных стартах. Просроченные попытки переведены в expired заранее.
    op.execute(
        """
        UPDATE test_attempts SET status = 'expired'
        WHERE status = 'in_progress' AND expires_at < now()
        """
    )
    op.execute(
        """
        DELETE FROM test_attempts a USING test_attempts b
        WHERE a.id > b.id AND a.candidate_id = b.candidate_id
          AND a.status = 'in_progress' AND b.status = 'in_progress'
        """
    )
    op.create_index('uq_test_attempts_active_candidate', 'test_attempts', ['candidate_id'],
                    unique=True, postgresql_where=sa.text("status = 'in_progress'"))

    # --- приглашения: отзыв контактов освобождает пару (company, candidate) ---
    op.drop_index('uq_invitation_open_company_candidate', table_name='invitations')
    op.create_index(
        'uq_invitation_open_company_candidate',
        'invitations',
        ['company_id', 'candidate_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'accepted') AND contacts_revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index('uq_test_attempts_active_candidate', table_name='test_attempts')
    op.drop_column('test_attempts', 'answers_version')
    op.drop_column('test_attempts', 'questions_snapshot')

    op.drop_index('uq_invitation_open_company_candidate', table_name='invitations')
    op.create_index(
        'uq_invitation_open_company_candidate',
        'invitations',
        ['company_id', 'candidate_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'accepted')"),
    )