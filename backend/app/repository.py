from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import schemas
from app.models import AnswerOption, Case, CaseFinding, Submission, SubmissionAnswer


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class InvalidAnswer(Exception):
    pass


def create_case(session: Session, data: schemas.CaseIn) -> Case:
    case = Case(
        title=data.title,
        presenting_complaint=data.presenting_complaint,
        history=data.history,
        patient_age=data.patient.age,
        patient_sex=data.patient.sex,
        **data.vitals.model_dump(),
        findings=[CaseFinding(position=i, **f.model_dump()) for i, f in enumerate(data.findings)],
        options=[
            AnswerOption(kind=kind, position=i, **o.model_dump())
            for kind, options in (("diagnosis", data.diagnosis_options), ("management", data.management_options))
            for i, o in enumerate(options)
        ],
    )
    session.add(case)
    session.commit()
    return case


def list_cases(session: Session) -> list[schemas.CaseSummary]:
    cases = session.scalars(select(Case).order_by(Case.id)).all()
    return [_summary(c) for c in cases]


def get_case(session: Session, case_id: int) -> schemas.CasePublic:
    case = session.scalar(
        select(Case).where(Case.id == case_id).options(selectinload(Case.findings), selectinload(Case.options))
    )
    if case is None:
        raise NotFound(f"case {case_id} not found")
    return schemas.CasePublic(
        **_summary(case).model_dump(),
        history=case.history,
        vitals=schemas.Vitals(
            heart_rate=case.heart_rate,
            systolic_bp=case.systolic_bp,
            diastolic_bp=case.diastolic_bp,
            respiratory_rate=case.respiratory_rate,
            temperature_c=case.temperature_c,
            spo2=case.spo2,
        ),
        findings=[schemas.Finding(kind=f.kind, name=f.name, value=f.value) for f in case.findings],
        diagnosis_options=[schemas.OptionPublic.model_validate(o) for o in case.options if o.kind == "diagnosis"],
        management_options=[schemas.OptionPublic.model_validate(o) for o in case.options if o.kind == "management"],
    )


def submit(session: Session, case_id: int, data: schemas.SubmissionIn) -> schemas.SubmissionResult:
    options = {
        option_id: kind
        for option_id, kind in session.execute(
            select(AnswerOption.id, AnswerOption.kind).where(AnswerOption.case_id == case_id)
        )
    }
    if not options:
        raise NotFound(f"case {case_id} not found")
    if options.get(data.diagnosis_option_id) != "diagnosis":
        raise InvalidAnswer("diagnosis_option_id is not a diagnosis option of this case")
    management_ids = set(data.management_option_ids)
    if any(options.get(i) != "management" for i in management_ids):
        raise InvalidAnswer("management_option_ids contain options that are not management options of this case")

    submission = Submission(case_id=case_id, participant=data.participant)
    session.add(submission)
    try:
        session.flush()
    except IntegrityError as e:
        session.rollback()
        raise Conflict(f"{data.participant!r} has already answered this case") from e
    session.add_all(
        SubmissionAnswer(submission_id=submission.id, option_id=option_id, case_id=case_id, kind=options[option_id])
        for option_id in (data.diagnosis_option_id, *management_ids)
    )
    session.commit()
    return get_result(session, submission.id)


def get_result(session: Session, submission_id: int) -> schemas.SubmissionResult:
    total = (
        session.execute(text("SELECT * FROM submission_scores WHERE submission_id = :id"), {"id": submission_id})
        .mappings()
        .one_or_none()
    )
    if total is None:
        raise NotFound(f"submission {submission_id} not found")
    rows = session.execute(
        text(
            """
            SELECT o.id, o.kind, o.label, o.points, o.explanation, a.option_id IS NOT NULL AS chosen
            FROM answer_options o
            LEFT JOIN submission_answers a ON a.option_id = o.id AND a.submission_id = :id
            WHERE o.case_id = :case_id
            ORDER BY o.kind, o.position
            """
        ),
        {"id": submission_id, "case_id": total["case_id"]},
    ).mappings()
    return schemas.SubmissionResult(
        **{k: v for k, v in total.items() if k in schemas.SubmissionResult.model_fields},
        options=[schemas.ScoredOption(**r) for r in rows],
    )


def leaderboard(session: Session, case_id: int, limit: int = 50) -> list[schemas.LeaderboardEntry]:
    rows = session.execute(
        text(
            """
            SELECT RANK() OVER (ORDER BY score DESC) AS rank,
                   participant, score, max_score, created_at AS submitted_at
            FROM submission_scores
            WHERE case_id = :case_id
            ORDER BY score DESC, created_at
            LIMIT :limit
            """
        ),
        {"case_id": case_id, "limit": limit},
    ).mappings()
    return [schemas.LeaderboardEntry(**r) for r in rows]


def _summary(case: Case) -> schemas.CaseSummary:
    return schemas.CaseSummary(
        id=case.id,
        title=case.title,
        presenting_complaint=case.presenting_complaint,
        patient=schemas.Patient(age=case.patient_age, sex=case.patient_sex),
    )
