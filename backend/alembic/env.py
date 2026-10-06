from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import settings
from app.models import Base

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

url = context.config.attributes.get("database_url") or settings.database_url

if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url).connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
