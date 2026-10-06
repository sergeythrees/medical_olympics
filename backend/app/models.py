from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Numeric, SmallInteger, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """ORM mapping for typed reads/writes. The DDL (constraints, indexes, the scoring view)
    is owned by the Alembic migrations."""


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    presenting_complaint: Mapped[str]
    history: Mapped[str]
    patient_age: Mapped[int] = mapped_column(SmallInteger)
    patient_sex: Mapped[str]
    heart_rate: Mapped[int | None] = mapped_column(SmallInteger)
    systolic_bp: Mapped[int | None] = mapped_column(SmallInteger)
    diastolic_bp: Mapped[int | None] = mapped_column(SmallInteger)
    respiratory_rate: Mapped[int | None] = mapped_column(SmallInteger)
    temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    spo2: Mapped[int | None] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    findings: Mapped[list["CaseFinding"]] = relationship(order_by="CaseFinding.position", cascade="all, delete-orphan")
    options: Mapped[list["AnswerOption"]] = relationship(order_by="AnswerOption.position", cascade="all, delete-orphan")


class CaseFinding(Base):
    __tablename__ = "case_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    kind: Mapped[str]
    name: Mapped[str]
    value: Mapped[str]


class AnswerOption(Base):
    __tablename__ = "answer_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"))
    kind: Mapped[str]
    position: Mapped[int] = mapped_column(SmallInteger)
    label: Mapped[str]
    points: Mapped[int] = mapped_column(SmallInteger)
    explanation: Mapped[str | None]


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"))
    participant: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SubmissionAnswer(Base):
    __tablename__ = "submission_answers"
    __table_args__ = (
        # The chosen option must belong to the same case as the submission, and `kind`
        # is copied so the DB can enforce "at most one diagnosis per submission".
        ForeignKeyConstraint(
            ["option_id", "case_id", "kind"], ["answer_options.id", "answer_options.case_id", "answer_options.kind"]
        ),
        ForeignKeyConstraint(
            ["submission_id", "case_id"], ["submissions.id", "submissions.case_id"], ondelete="CASCADE"
        ),
    )

    submission_id: Mapped[int] = mapped_column(primary_key=True)
    option_id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int]
    kind: Mapped[str]
