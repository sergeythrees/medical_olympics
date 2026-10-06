from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/cases"
    cors_origins: list[str] = ["http://localhost:3000"]

    # LLM provider is picked by which credentials are set (see extraction.make_llm).
    # DeepSeek: OpenAI-compatible API, JSON mode.
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    # Gemini: Vertex AI on GCP (service account via ADC), or an API key locally.
    gemini_model: str = "gemini-2.5-flash"
    google_cloud_project: str | None = None
    google_cloud_location: str = "europe-west1"
    gemini_api_key: str | None = None


settings = Settings()
