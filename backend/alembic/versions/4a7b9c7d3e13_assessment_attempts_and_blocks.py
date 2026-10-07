"""assessment: category grade per attempt, 3 blocks, server timer, expired status

Revision ID: 4a7b9c7d3e13
Revises: 3f6a9c7d3e12
Create Date: 2026-10-07 02:00:00.000000

Изменения (Этап 2, FR-08..FR-13):
- test_questions.block (1..3): разделы теста; существующие вопросы распределяются
  по блокам без потери данных;
- test_attempts.grade_level: выбранная категория (Junior/Middle);
- test_attempts.expires_at: серверный таймер попытки (20 минут);
- test_attempts.blockN_correct: результаты по блокам;
- статус 'expired' у попыток;
- уникальность ответа (attempt_id, question_id) для безопасного upsert.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '4a7b9c7d3e13'
down_revision: Union[str, None] = '3f6a9c7d3e12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- вопросы: разделы 1..3 (внутри (спец, грейд) по порядку) ---
    op.add_column('test_questions', sa.Column('block', sa.Integer(), nullable=False, server_default='1'))
    op.execute(
        """
        UPDATE test_questions q SET block = ranked.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY specialization_id, grade_level ORDER BY sort_order, id
            ) AS rn
            FROM test_questions
        ) ranked
        WHERE q.id = ranked.id AND ranked.rn <= 3
        """
    )
    op.alter_column('test_questions', 'block', existing_type=sa.Integer(), nullable=False,
                    server_default=None)

    # --- попытки: категория, таймер, блоки ---
    op.add_column('test_attempts', sa.Column('grade_level', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('test_attempts', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('test_attempts', sa.Column('block1_correct', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('test_attempts', sa.Column('block2_correct', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('test_attempts', sa.Column('block3_correct', sa.Integer(), nullable=False, server_default='0'))

    # Backfill без потери данных: грейд из подтверждённого результата, таймер из дат попытки
    op.execute(
        """
        UPDATE test_attempts a
        SET grade_level = COALESCE((SELECT g.level FROM grades g WHERE g.id = a.result_grade_id), 1)
        """
    )
    op.execute(
        "UPDATE test_attempts SET expires_at = COALESCE(submitted_at, started_at + INTERVAL '20 minutes')"
    )
    op.alter_column('test_attempts', 'grade_level', existing_type=sa.Integer(), nullable=False,
                    server_default=None)
    op.alter_column('test_attempts', 'expires_at', existing_type=sa.DateTime(timezone=True), nullable=False)
    for col in ('block1_correct', 'block2_correct', 'block3_correct'):
        op.alter_column('test_attempts', col, existing_type=sa.Integer(), nullable=False, server_default=None)

    # --- статус expired ---
    op.execute("ALTER TYPE testattemptstatus ADD VALUE IF NOT EXISTS 'expired'")

    # --- уникальность ответа: один ответ на вопрос в попытке ---
    op.execute(
        """
        DELETE FROM test_attempt_answers a USING test_attempt_answers b
        WHERE a.id > b.id AND a.attempt_id = b.attempt_id AND a.question_id = b.question_id
        """
    )
    op.create_unique_constraint('uq_attempt_answer_question', 'test_attempt_answers',
                                ['attempt_id', 'question_id'])


def downgrade() -> None:
    op.drop_constraint('uq_attempt_answer_question', 'test_attempt_answers', type_='unique')
    for col in ('block3_correct', 'block2_correct', 'block1_correct'):
        op.drop_column('test_attempts', col)
    op.drop_column('test_attempts', 'expires_at')
    op.drop_column('test_attempts', 'grade_level')
    op.drop_column('test_questions', 'block')