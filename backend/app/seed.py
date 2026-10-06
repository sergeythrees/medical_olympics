"""Load demo cases into an empty database: the hand-annotated gold cases of the eval set."""

from pathlib import Path

from sqlalchemy import exists, select

from app.db import SessionLocal
from app.models import Case
from app.repository import create_case
from app.schemas import CaseIn

GOLDEN = Path(__file__).parent.parent / "evals" / "golden"


def main() -> None:
    with SessionLocal() as session:
        if session.scalar(select(exists().where(Case.id.isnot(None)))):
            print("seed: cases already present, skipping")
            return
        for path in sorted(GOLDEN.glob("*.json")):
            case = create_case(session, CaseIn.model_validate_json(path.read_text()))
            print(f"seed: case {case.id} {case.title!r}")


if __name__ == "__main__":
    main()
