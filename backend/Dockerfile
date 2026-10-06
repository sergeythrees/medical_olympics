FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY evals ./evals

USER nobody
# Cloud Run sets $PORT; the same image runs migrations as a Cloud Run Job (`alembic upgrade head`).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
