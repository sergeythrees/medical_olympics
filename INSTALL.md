# Установка и запуск (INSTALL.md)

Clinical Cases — мини-версия Medical Olympics: врач читает клинический кейс, выбирает диагноз и
тактику и получает баллы с разбором. Проект состоит из FastAPI + PostgreSQL backend
(скоринг в SQL), Next.js frontend (App Router) и LLM-пайплайна «сырой текст → структурированный
кейс» с харнесом оценки (evals).

## 1. Требования

| Компонент | Версия | Где зафиксировано |
|---|---|---|
| Python | **>= 3.13** | `requires-python` в [backend/pyproject.toml](backend/pyproject.toml); образ `python:3.13-slim` в [backend/Dockerfile](backend/Dockerfile) |
| uv | **0.12** | образ `ghcr.io/astral-sh/uv:0.12` в [backend/Dockerfile](backend/Dockerfile); `astral-sh/setup-uv@v6` в [CI](.github/workflows/ci.yml) |
| Node.js | **24** | образ `node:24-alpine` в [frontend/Dockerfile](frontend/Dockerfile); `node-version: 24` в [CI](.github/workflows/ci.yml) |
| pnpm | **11.26.0** | поле `packageManager` в [frontend/package.json](frontend/package.json) |
| PostgreSQL | **17** | `postgres:17-alpine` в [docker-compose.yml](docker-compose.yml) и в [CI](.github/workflows/ci.yml) |
| Docker + плагин `compose` | любая актуальная | нужен только для варианта §3 (Docker Compose) |
| gcloud | любая актуальная | нужен только для деплоя (§9) |

**На этой машине** (проверено): uv 0.12.20, Python 3.14.7, Node v26.10.0, pnpm 11.26.0,
Docker CLI 29.8.2 + Docker Compose 5.6.0, **gcloud нет**.

## 2. Переменные окружения

| Переменная | Где читается | Дефолт / значение |
|---|---|---|
| `DATABASE_URL` | backend (`app.db`) и Alembic | `postgresql+psycopg://postgres:postgres@localhost:5432/cases`; в compose `…@db:5432/cases`; в облаке — Secret Manager `database-url` |
| `TEST_DATABASE_URL` | pytest ([conftest.py](backend/tests/conftest.py)) | `postgresql+psycopg://postgres:postgres@localhost:5432/cases_test` |
| `DEEPSEEK_API_KEY` | `app.extraction` | в этом рабочем каталоге ключ **уже задан** в `backend/.env` (файл gitignored, значение здесь не приводится); при свежем клоне создайте `backend/.env` из [backend/.env.example](backend/.env.example) |
| `DEEPSEEK_MODEL` | `app.extraction` | `deepseek-flash` |
| `GEMINI_API_KEY` | `app.extraction` | пусто (альтернатива DeepSeek) |
| `GOOGLE_CLOUD_PROJECT` | `app.extraction` (Vertex AI) | пусто |
| `GOOGLE_CLOUD_LOCATION` | `app.extraction` (Vertex AI) | `europe-west1` |
| `API_URL` | **только серверная часть** фронтенда ([frontend/src/lib/api.ts](frontend/src/lib/api.ts)) | `http://localhost:8000`; в compose `http://api:8080` |
| `POSTGRES_PASSWORD` / `POSTGRES_DB` | сервис `db` в compose | `postgres` / `cases` — только для Docker Compose |
| `PORT` | backend-образ | `${PORT:-8080}` (Cloud Run передаёт свой порт) |

Важные пояснения:

- Переменных `NEXT_PUBLIC_*` в проекте **нет**: API-URL читается на сервере (RSC + Server Action),
  в бандл браузера не попадает, поэтому CORS не нужен.
- **Провайдер LLM выбирается по кредам**: есть ключ DeepSeek → DeepSeek, иначе Gemini → иначе
  `POST /extract` отвечает **503**. Дефолты — в [backend/app/config.py](backend/app/config.py),
  шаблон для копирования — [backend/.env.example](backend/.env.example).

## 3. Быстрый старт: Docker Compose

```bash
[ -f backend/.env ] || cp backend/.env.example backend/.env   # НЕ перезаписывайте существующий .env: в нём ключ
docker compose up -d --build
docker compose ps
docker compose logs -f api
docker compose down          # остановить
docker compose down -v       # остановить и снести
```

> **Проверьте ключ после копирования шаблона.** `cp .env.example .env` затирает рабочую копию:
> если в файле остались строки вида `DEEPSEEK_API_KEY=` с пустым значением, `POST /extract` будет
> отвечать **503**. Быстрая проверка: `grep -c '^DEEPSEEK_API_KEY=sk-' backend/.env` должен вернуть `1`.

- http://localhost:3000 — фронтенд (4 демо-кейса)
- http://localhost:8000/docs — Swagger API
- http://localhost:8000/health — healthcheck

Порты: `db` — `5432:5432`, `api` — `8000:8080`, `web` — `3000:3000`.

**Порядок старта** (см. [docker-compose.yml](docker-compose.yml)): `db` (healthcheck `pg_isready`,
interval 2s, retries 20) → одноразовый `migrate` (`alembic upgrade head && python -m app.seed`) →
`api` (ждёт `service_completed_successfully` от `migrate`) → `web`. `backend/.env` подключён как
**необязательный** (`required: false`): без него стек поднимется, а `/extract` будет отдавать 503.

### 3.1. Не смешивайте два способа запуска

Compose и локальный запуск (§4) занимают **одни и те же порты** `5432`, `8000`, `3000`. Перед
`docker compose up` убедитесь, что их никто не держит:

```bash
ss -ltnp | grep -E ':(5432|8000|3000)'
docker ps --format '{{.Names}}\t{{.Ports}}'
```

Самая частая причина «загадочных» падений: параллельно работает контейнер `cases-db` из §4.1 или
локальный `uvicorn`. Если хост-порт занят, Docker **всё равно запускает** контейнер, но без сети
(`docker compose ps` показывает `Up`, а колонка `PORTS` пустая) — и `migrate` падает с
`failed to resolve host 'db'`. Лечение: освободить порт и пересоздать стек
(`docker compose down && docker compose up -d`, см. §10).

### 3.2. Если Docker ещё не настроен (Linux)

Диагностика:

```bash
docker info
ls -l /var/run/docker.sock
getent group docker
systemctl is-active docker
systemctl is-enabled docker
```

Если сокет имеет вид `root:docker` с правами `660`, пользователь должен состоять в группе `docker`:

```bash
sudo usermod -aG docker $USER
newgrp docker        # или перелогиниться
```

Пока группа не активна в текущей сессии, можно работать так:

```bash
sudo docker compose up -d --build
sudo -u "$USER" -g docker docker compose up -d --build
```

Автозапуск демона:

```bash
sudo systemctl enable docker   # по умолчанию обычно disabled
```

`systemctl enable` действует **только со следующей загрузки**. Если включить автозапуск уже после
перезагрузки, демон всё равно нужно поднять руками: `sudo systemctl start docker`. Признак того,
что демон не запущен, — отсутствие файла `/var/run/docker.sock` (см. §10).

## 4. Запуск локально без Docker

### 4.1. Postgres

```bash
docker run -d --name cases-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=cases -p 5432:5432 postgres:17-alpine
```

> Контейнер `cases-db` публикует **тот же порт 5432**, что и сервис `db` в compose. Перед возвратом
> к варианту §3 остановите его: `docker stop cases-db` (данные сохранятся, позже — `docker start cases-db`).
> Если запустить оба, compose-сервис `db` стартует без сети и `migrate` упадёт (см. §3.1 и §10).

### 4.2. Backend

```bash
cd backend
uv sync --frozen
[ -f .env ] || cp .env.example .env   # не перезаписывайте существующий .env с ключом
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/cases"
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> Локальный `uvicorn` занимает порт **8000** — тот же, что публикует сервис `api` в compose.
> Перед `docker compose up` его нужно остановить, иначе `api` не сможет забиндить порт
> (`failed to bind host port 0.0.0.0:8000/tcp: address already in use`).

- Схема `postgresql+psycopg` **обязательна** — это драйвер psycopg 3, который использует проект.
- Локально порт **8000** (в контейнере — 8080), потому что фронтенд по умолчанию ждёт
  `http://localhost:8000` ([frontend/src/lib/api.ts](frontend/src/lib/api.ts)).
- `app.seed` **пропускает работу**, если в таблице `cases` уже есть строки.

### 4.3. Frontend

```bash
cd frontend
pnpm install --frozen-lockfile
export API_URL=http://localhost:8000
pnpm dev
```

Прод-сборка и запуск:

```bash
pnpm build && pnpm start
```

`API_URL` читается **на сервере** (RSC + Server Action), в бандл браузера не попадает, поэтому
CORS не нужен.

## 5. Тесты, линт, типы

```bash
# backend
cd backend
uv run ruff check . && uv run ruff format --check .
docker compose up -d db
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/cases_test uv run pytest -q

# frontend
cd frontend
pnpm typecheck
pnpm test
pnpm build
```

- Backend: **31 тест** (pytest) на **реальном PostgreSQL**; БД `cases_test` создаётся автоматически,
  поэтому у пользователя нужны права `CREATE DATABASE`.
- Frontend: **4 теста** (Vitest + Testing Library).

## 6. Генерация контрактов (если меняли схемы или эндпоинты)

```bash
cd backend && uv run python -m app.export_schemas
cd ../frontend && pnpm gen:api
```

Порядок **обязателен**: backend-тест валит сборку при устаревшем `backend/schemas/openapi.json`,
frontend-тест — при устаревшем `frontend/src/lib/api-schema.ts`.

## 7. Evals

```bash
cd backend
uv run python -m evals.run
uv run python -m evals.run --predictions evals/runs/<run>
```

- Нужны креды LLM (ключ DeepSeek или Gemini).
- Раннер возвращает **код 1**, если не пройдены quality gates: `schema_valid=1`,
  `correct_diagnosis=1`, `vitals_accuracy>=0.95`, `findings_coverage>=0.9`, `findings_grounded=1`,
  `finding_values_accuracy>=0.95`, `management_polarity_errors=0` — см.
  [backend/evals/run.py](backend/evals/run.py).

## 8. CI

[.github/workflows/ci.yml](.github/workflows/ci.yml) на каждый push/PR:

- **backend** — сервис `postgres:17-alpine` + `uv sync --frozen` +
  `uv run ruff check . && uv run ruff format --check .` + `uv run pytest -q` с `TEST_DATABASE_URL`;
- **frontend** — `pnpm install --frozen-lockfile` + `pnpm typecheck` + `pnpm test` + `pnpm build`.

Секретов и evals в CI **нет** (evals требуют ключа и стоят денег).

## 9. Деплой в GCP

Кратко: **Cloud Run** (`cases-api`, `cases-web`) + **Cloud SQL Postgres 17** через unix-сокет +
**Cloud Run Job** `cases-migrate` + **Secret Manager** (`database-url`) + **Vertex AI** по service
account. Пошаговые команды создания инфраструктуры и релиза — в [deploy/README.md](deploy/README.md).

Релиз:

```bash
gcloud builds submit --config deploy/cloudbuild.yaml \
  --substitutions=_API_URL=$(gcloud run services describe cases-api --region=europe-west1 --format='value(status.url)')
```

## 10. Частые проблемы

| Симптом | Причина / что делать |
|---|---|
| `permission denied … /var/run/docker.sock` | пользователь не в группе `docker` → `sudo usermod -aG docker $USER` + `newgrp docker` (см. §3.2) |
| `dial unix /var/run/docker.sock: connect: no such file or directory` | демон Docker не запущен — типично после перезагрузки → `sudo systemctl start docker`; автозапуск: `sudo systemctl enable docker` (действует со следующей загрузки, см. §3.2) |
| После перезагрузки контейнеры не поднялись | демон теперь стартует сам, но у сервисов нет политики перезапуска → выполнить `docker compose up -d`; либо добавить сервисам `restart: unless-stopped` |
| `docker: unknown command: docker compose` | не установлен плагин Compose → поставить `docker-compose-plugin` или использовать `docker-compose` |
| `POST /extract` → 503 | не заданы креды LLM → вписать `DEEPSEEK_API_KEY` (или Gemini) в `backend/.env` |
| `/extract` → 503 сразу после `cp .env.example .env` | шаблон затёр рабочий `.env`, значения пустые → вернуть ключ и пересоздать контейнер: `docker compose up -d --force-recreate api`; проверка `grep -c '^DEEPSEEK_API_KEY=sk-' backend/.env` → `1` |
| `service "migrate" didn't complete successfully: exit 1`, в логе `failed to resolve host 'db'` | хост-порт 5432 занят другим контейнером (`cases-db` из §4.1) → compose-сервис `db` стартовал **без сети**; `docker stop cases-db`, затем `docker compose down && docker compose up -d` |
| `failed to bind host port 0.0.0.0:8000/tcp: address already in use` | порт 8000 держит локальный `uvicorn` из §4.2 → `ss -ltnp \| grep :8000`, остановить процесс, затем `docker compose up -d` |
| `docker compose ps`: сервис `Up`, но колонка `PORTS` пустая и сервис недоступен | контейнер поднялся без сети из-за конфликта портов → `journalctl -u docker --since -10m \| grep -i "Failed to allocate port"`, освободить порт и пересоздать стек |
| API локально не видит БД | проверьте хост (`db` в compose vs `localhost` вне compose) и схему `postgresql+psycopg` |
| `api` не стартует в compose | он ждёт успешного `migrate` → смотреть `docker compose logs migrate` |
| Сид ничего не добавил | в `cases` уже есть строки — seed пропускает работу (это by design) |
| pytest падает на подключении | нет запущенного Postgres или нет прав `CREATE DATABASE` для создания `cases_test` |
| Фронтенд 500 при живом бэкенде | не задан `API_URL` → задать и перезапустить фронтенд |
| Порт 3000 занят другим процессом | `ss -ltnp \| grep :3000` |
| Данные БД исчезают после `docker compose down` | в compose нет named volume для `db` → добавить `volumes: ["cases-db:/var/lib/postgresql/data"]` |
| `buildx Docker CLI plugin not found … falling back to the classic builder` | безобидное предупреждение, сборка продолжается |

## 11. Что проверено

Проверки выполнены **2026-10-06** на этой машине (Postgres 17.11 на `127.0.0.1:55433` и через
docker compose):

| Проверка | Результат |
|---|---|
| `uv run ruff check .` | All checks passed |
| `alembic upgrade head` | `upgrade -> 0001` |
| `python -m app.seed` | 4 кейса |
| `pytest -q` | 31 passed |
| `GET /health` | `{"status":"ok"}` |
| `GET /cases` | 4 кейса |
| `GET /cases/1` | без баллов и объяснений |
| `POST /cases/1/submissions` | 201, score 20/27, `diagnosis_correct` true |
| `GET /cases/1/leaderboard` | rank 1 |
| `POST /extract` (живой DeepSeek) | 200 |
| `pnpm typecheck` | ok |
| `pnpm test` | 4 passed |
| `docker compose up -d --build` | db healthy, migrate Exited 0, api Up `8000->8080`, web Up `3000`, http://localhost:3000/ → 200 со всеми 4 кейсами, `/cases/1` → 200 |
| **Не проверялось** | деплой в GCP (нет gcloud и проекта) |

Дополнительно **после переноса проекта в `~/git/medical_olympics`** (compose-проект
`medical_olympics`): устранены два конфликта портов — `5432` держал контейнер `cases-db` из §4.1
(из-за этого `migrate` падал с `failed to resolve host 'db'`), `8000` держал локальный `uvicorn`.
После `docker stop cases-db` и остановки `uvicorn`: `db`/`api`/`web` получили сеть
(`medical_olympics_default`, IP `172.19.0.2–4`) и проброс портов, `migrate` → "exit 0" с сидом
4 кейсов, `GET /health` → 200, http://localhost:3000/ → 200, `/extract` → 200 (ключ восстановлен
в `backend/.env`).

## 12. Полезные ссылки

- [README.md](README.md) — обзор проекта, API, схема данных, evals.
- [deploy/README.md](deploy/README.md) — пошаговый деплой в GCP (Cloud Run + Cloud SQL).
- [docker-compose.yml](docker-compose.yml) — локальный стек из четырёх сервисов.
- [backend/.env.example](backend/.env.example) — шаблон переменных окружения.
