"""Guards against contract drift between backend, frontend types and the LLM schema."""

from alembic import command

from app.export_schemas import OUT, render
from conftest import alembic_config


def test_exported_schemas_are_up_to_date():
    for name, content in render().items():
        assert (OUT / name).read_text() == content, f"schemas/{name} is stale: run `python -m app.export_schemas`"


def test_migrations_downgrade_and_upgrade_cleanly():
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
