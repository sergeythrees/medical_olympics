"""Initial schema: cases, findings, answer options, submissions, scoring view.

Revision ID: 0001
Revises:
Create Date: 2026-10-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("presenting_complaint", sa.Text, nullable=False),
        sa.Column("history", sa.Text, nullable=False),
        sa.Column("patient_age", sa.SmallInteger, nullable=False),
        sa.Column("patient_sex", sa.Text, nullable=False),
        sa.Column("heart_rate", sa.SmallInteger),
        sa.Column("systolic_bp", sa.SmallInteger),
        sa.Column("diastolic_bp", sa.SmallInteger),
        sa.Column("respiratory_rate", sa.SmallInteger),
        sa.Column("temperature_c", sa.Numeric(3, 1)),
        sa.Column("spo2", sa.SmallInteger),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("patient_age BETWEEN 0 AND 120", name="ck_cases_patient_age"),
        sa.CheckConstraint("patient_sex IN ('female', 'male')", name="ck_cases_patient_sex"),
        sa.CheckConstraint("spo2 BETWEEN 0 AND 100", name="ck_cases_spo2"),
    )

    op.create_table(
        "case_findings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("case_id", sa.Integer, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.SmallInteger, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.UniqueConstraint("case_id", "position", name="uq_case_findings_position"),
        sa.CheckConstraint("kind IN ('exam', 'lab', 'imaging', 'ecg', 'other')", name="ck_case_findings_kind"),
    )

    op.create_table(
        "answer_options",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("case_id", sa.Integer, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("position", sa.SmallInteger, nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("points", sa.SmallInteger, nullable=False),
        sa.Column("explanation", sa.Text),
        sa.UniqueConstraint("case_id", "kind", "position", name="uq_answer_options_position"),
        # Target for the composite FK from submission_answers.
        sa.UniqueConstraint("id", "case_id", "kind", name="uq_answer_options_id_case_kind"),
        sa.CheckConstraint("kind IN ('diagnosis', 'management')", name="ck_answer_options_kind"),
        sa.CheckConstraint("points BETWEEN -10 AND 10", name="ck_answer_options_points"),
    )
    op.create_index(
        "uq_answer_options_label",
        "answer_options",
        ["case_id", "kind", sa.text("lower(label)")],
        unique=True,
    )

    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("case_id", sa.Integer, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("participant", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # One attempt per participant per case: a competition, not a quiz you can retry.
        sa.UniqueConstraint("case_id", "participant", name="uq_submissions_case_participant"),
        sa.UniqueConstraint("id", "case_id", name="uq_submissions_id_case"),
    )

    op.create_table(
        "submission_answers",
        sa.Column("submission_id", sa.Integer, primary_key=True),
        sa.Column("option_id", sa.Integer, primary_key=True),
        sa.Column("case_id", sa.Integer, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id", "case_id"],
            ["submissions.id", "submissions.case_id"],
            ondelete="CASCADE",
            name="fk_submission_answers_submission",
        ),
        sa.ForeignKeyConstraint(
            ["option_id", "case_id", "kind"],
            ["answer_options.id", "answer_options.case_id", "answer_options.kind"],
            ondelete="CASCADE",
            name="fk_submission_answers_option",
        ),
    )
    op.create_index(
        "uq_submission_answers_one_diagnosis",
        "submission_answers",
        ["submission_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'diagnosis'"),
    )
    op.create_index("ix_submission_answers_option", "submission_answers", ["option_id"])

    # Scoring lives in the database: one place that the API and the leaderboard both read.
    # score     = sum of points of chosen options, floored at 0 (harmful actions subtract);
    # max_score = best diagnosis + every indicated management option.
    op.execute(
        """
        CREATE VIEW submission_scores AS
        SELECT s.id AS submission_id,
               s.case_id,
               s.participant,
               s.created_at,
               GREATEST(0, COALESCE(SUM(o.points) FILTER (WHERE a.option_id IS NOT NULL), 0))::int AS score,
               (MAX(o.points) FILTER (WHERE o.kind = 'diagnosis')
                + COALESCE(SUM(o.points) FILTER (WHERE o.kind = 'management' AND o.points > 0), 0))::int
                   AS max_score,
               COALESCE(BOOL_OR(a.option_id IS NOT NULL AND o.kind = 'diagnosis' AND o.points = 10), FALSE)
                   AS diagnosis_correct
        FROM submissions s
        JOIN answer_options o ON o.case_id = s.case_id
        LEFT JOIN submission_answers a ON a.submission_id = s.id AND a.option_id = o.id
        GROUP BY s.id
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW submission_scores")
    op.drop_table("submission_answers")
    op.drop_table("submissions")
    op.drop_table("answer_options")
    op.drop_table("case_findings")
    op.drop_table("cases")
