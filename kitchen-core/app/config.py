from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://kitchen:kitchen@postgres:5432/kitchen"
    establishment_webhook_timeout: float = 3.0
    # Demo default only. A real deployment receives this exclusively from a secret store.
    admin_api_key: str = "demo-admin-key"

    model_config = SettingsConfigDict(env_prefix="KITCHEN_")


settings = Settings()
