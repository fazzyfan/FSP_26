"""assessment: test questions, attempts, confirmed categories; invitations

Revision ID: 2f5a9c7d3e11
Revises: 1044b338cc6a
Create Date: 2026-10-06 18:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '2f5a9c7d3e11'
down_revision: Union[str, None] = '1044b338cc6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- тест (FR-08..FR-12) ---
    op.create_table('test_questions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('specialization_id', sa.UUID(), nullable=False),
    sa.Column('grade_level', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('explanation', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['specialization_id'], ['specializations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_test_questions_specialization_id'), 'test_questions', ['specialization_id'], unique=False)

    op.create_table('test_question_options',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('question_id', sa.UUID(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('is_correct', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['test_questions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_test_question_options_question_id'), 'test_question_options', ['question_id'], unique=False)

    op.create_table('test_attempts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('candidate_id', sa.UUID(), nullable=False),
    sa.Column('specialization_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.Enum('in_progress', 'completed', name='testattemptstatus'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('correct_count', sa.Integer(), nullable=False),
    sa.Column('total_count', sa.Integer(), nullable=False),
    sa.Column('score_percent', sa.Integer(), nullable=True),
    sa.Column('result_grade_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidate_profiles.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['result_grade_id'], ['grades.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['specialization_id'], ['specializations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_test_attempts_candidate_id'), 'test_attempts', ['candidate_id'], unique=False)

    op.create_table('test_attempt_answers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('attempt_id', sa.UUID(), nullable=False),
    sa.Column('question_id', sa.UUID(), nullable=False),
    sa.Column('option_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['attempt_id'], ['test_attempts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['option_id'], ['test_question_options.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['question_id'], ['test_questions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_test_attempt_answers_attempt_id'), 'test_attempt_answers', ['attempt_id'], unique=False)

    op.create_table('confirmed_categories',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('candidate_id', sa.UUID(), nullable=False),
    sa.Column('specialization_id', sa.UUID(), nullable=False),
    sa.Column('grade_id', sa.UUID(), nullable=False),
    sa.Column('source_attempt_id', sa.UUID(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidate_profiles.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['grade_id'], ['grades.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_attempt_id'], ['test_attempts.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['specialization_id'], ['specializations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_confirmed_categories_candidate_id'), 'confirmed_categories', ['candidate_id'], unique=False)
    op.create_index('uq_confirmed_categories_active', 'confirmed_categories', ['candidate_id'], unique=True,
                    postgresql_where=sa.text('is_active'))

    # --- приглашения (FR-23..FR-27) ---
    op.create_table('invitations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('need_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('candidate_id', sa.UUID(), nullable=False),
    sa.Column('salary_from', sa.Integer(), nullable=True),
    sa.Column('salary_to', sa.Integer(), nullable=True),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('pending', 'accepted', 'declined', 'withdrawn', name='invitationstatus'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('contacts_viewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidate_profiles.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['need_id'], ['employer_needs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('need_id', 'candidate_id', name='uq_invitation_need_candidate')
    )
    op.create_index(op.f('ix_invitations_candidate_id'), 'invitations', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_invitations_company_id'), 'invitations', ['company_id'], unique=False)
    op.create_index(op.f('ix_invitations_need_id'), 'invitations', ['need_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_invitations_need_id'), table_name='invitations')
    op.drop_index(op.f('ix_invitations_company_id'), table_name='invitations')
    op.drop_index(op.f('ix_invitations_candidate_id'), table_name='invitations')
    op.drop_table('invitations')
    op.drop_index('uq_confirmed_categories_active', table_name='confirmed_categories')
    op.drop_index(op.f('ix_confirmed_categories_candidate_id'), table_name='confirmed_categories')
    op.drop_table('confirmed_categories')
    op.drop_index(op.f('ix_test_attempt_answers_attempt_id'), table_name='test_attempt_answers')
    op.drop_table('test_attempt_answers')
    op.drop_index(op.f('ix_test_attempts_candidate_id'), table_name='test_attempts')
    op.drop_table('test_attempts')
    op.drop_index(op.f('ix_test_question_options_question_id'), table_name='test_question_options')
    op.drop_table('test_question_options')
    op.drop_index(op.f('ix_test_questions_specialization_id'), table_name='test_questions')
    op.drop_table('test_questions')
    sa.Enum(name='testattemptstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='invitationstatus').drop(op.get_bind(), checkfirst=True)