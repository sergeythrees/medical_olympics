# Деплой в GCP: Cloud Run + Cloud SQL + Vertex AI

```
                 ┌──────────────┐  HTTPS   ┌──────────────┐  unix socket  ┌──────────────┐
  браузер ──────▶│  cases-web   │─────────▶│  cases-api   │──────────────▶│  Cloud SQL   │
                 │  Cloud Run   │  API_URL │  Cloud Run   │  /cloudsql/…  │  Postgres 17 │
                 └──────────────┘          └──────┬───────┘               └──────▲───────┘
                                                  │ ADC (service account)        │
                                                  ▼                              │
                                           ┌──────────────┐        ┌─────────────┴───┐
                                           │  Vertex AI   │        │ cases-migrate   │
                                           │  Gemini      │        │ Cloud Run Job   │
                                           └──────────────┘        │ alembic upgrade │
                                                                   └─────────────────┘
```

Ключевые решения:

- **Один образ backend** — и сервис, и job миграций. Миграции не запускаются на старте
  контейнера: при автоскейлинге N инстансов не должны гоняться за `alembic_version`.
- **Без ключей.** К Vertex AI и Cloud SQL сервис ходит от своего service account (ADC).
  Единственный секрет — `DATABASE_URL` с паролем БД — лежит в Secret Manager.
- **Cloud SQL через встроенный коннектор Cloud Run** (`--add-cloudsql-instances`): unix-сокет,
  без публичного IP в allowlist и без sidecar-прокси.

## Один раз: инфраструктура

```bash
PROJECT=my-project
REGION=europe-west1
INSTANCE=$PROJECT:$REGION:cases-db
SA=cases-api@$PROJECT.iam.gserviceaccount.com
gcloud config set project $PROJECT

gcloud services enable run.googleapis.com sqladmin.googleapis.com aiplatform.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com

gcloud artifacts repositories create cases --repository-format=docker --location=$REGION

# Postgres
gcloud sql instances create cases-db --database-version=POSTGRES_17 --edition=ENTERPRISE \
  --tier=db-custom-1-3840 --region=$REGION
gcloud sql databases create cases --instance=cases-db
DB_PASSWORD=$(openssl rand -base64 24)
gcloud sql users create app --instance=cases-db --password="$DB_PASSWORD"
printf 'postgresql+psycopg://app:%s@/cases?host=/cloudsql/%s' "$DB_PASSWORD" "$INSTANCE" \
  | gcloud secrets create database-url --data-file=-

# Service account с минимальными правами
gcloud iam service-accounts create cases-api
for role in roles/cloudsql.client roles/aiplatform.user roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$SA --role=$role
done

# Job миграций (образ обновляется на каждом релизе)
gcloud builds submit backend --tag $REGION-docker.pkg.dev/$PROJECT/cases/api:initial
gcloud run jobs create cases-migrate --region=$REGION \
  --image=$REGION-docker.pkg.dev/$PROJECT/cases/api:initial \
  --command=alembic --args=upgrade,head \
  --service-account=$SA --set-cloudsql-instances=$INSTANCE \
  --set-secrets=DATABASE_URL=database-url:latest
```

Провайдер LLM на GCP — Vertex AI (Gemini): сервис ходит к нему по service account, ключей нет.
Если нужен DeepSeek, ключ кладётся в Secret Manager (`gcloud secrets create deepseek-api-key --data-file=-`)
и добавляется в деплой: `--set-secrets=DATABASE_URL=database-url:latest,DEEPSEEK_API_KEY=deepseek-api-key:latest`.
Учтите, что тексты кейсов при этом уходят внешнему провайдеру за пределы GCP.

Cloud Build service account'у нужны `roles/run.admin` и `roles/iam.serviceAccountUser`
на `cases-api`, чтобы деплоить от его имени.

## Каждый релиз

```bash
gcloud builds submit --config deploy/cloudbuild.yaml \
  --substitutions=_API_URL=$(gcloud run services describe cases-api --region=$REGION --format='value(status.url)')
```

[`cloudbuild.yaml`](cloudbuild.yaml): собирает оба образа параллельно → пушит в Artifact Registry →
обновляет образ job'а и выполняет миграции (`--wait`, при ошибке релиз останавливается) →
деплоит `cases-api` → деплоит `cases-web`. Новая ревизия Cloud Run получает трафик только после
успешного старта, откат — `gcloud run services update-traffic cases-api --to-revisions=<prev>=100`.

Миграции пишутся expand/contract: старая ревизия API должна работать на новой схеме,
пока не переключился трафик.

Кейсы на проде создаются через API: `POST /extract` (черновик из текста) → проверка автором → `POST /cases`.

## Что сознательно упрощено

- `cases-api` открыт наружу (`--allow-unauthenticated`), потому что аутентификация вне scope задания.
  В проде: `--no-allow-unauthenticated`, `roles/run.invoker` для SA фронтенда, фронтенд добавляет
  ID-токен (`google-auth-library`) в запросы из Server Components / Server Actions — браузер
  к API напрямую не ходит, так что меняется только `src/lib/api.ts`.
- Нет Terraform: для двух сервисов и одной БД gcloud-команды читаются проще; при росте
  инфраструктуры — перенести в Terraform.
- Нет отдельных staging/prod проектов, алертов и дашбордов (Cloud Run и Cloud SQL дают базовые
  метрики и логи из коробки; uvicorn пишет в stdout → Cloud Logging).
