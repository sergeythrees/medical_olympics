import json
import os
from pathlib import Path

import pytest

# Must be set before app.db creates the engine.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/cases_test"
)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, make_url, text  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402

ROOT = Path(__file__).parent.parent
GOLDEN = ROOT / "evals" / "golden"


def alembic_config() -> Config:
    cfg = Config(ROOT / "alembic.ini")
    cfg.attributes["database_url"] = os.environ["DATABASE_URL"]
    return cfg


def _create_test_database() -> None:
    url = make_url(os.environ["DATABASE_URL"])
    server = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": url.database}):
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    server.dispose()


@pytest.fixture(scope="session", autouse=True)
def _schema():
    _create_test_database()
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_db():
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE cases RESTART IDENTITY CASCADE"))


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def golden(name: str) -> dict:
    return json.loads((GOLDEN / f"{name}.json").read_text())


@pytest.fixture
def stemi(client: TestClient) -> dict:
    """The inferior STEMI case as created via the API, plus helpers to address options by label."""
    case = client.post("/cases", json=golden("inferior-stemi")).json()
    ids = {o["label"]: o["id"] for o in case["diagnosis_options"] + case["management_options"]}

    def opt(prefix: str) -> int:
        return next(v for k, v in ids.items() if k.startswith(prefix))

    return {"case": case, "id": case["id"], "opt": opt}
