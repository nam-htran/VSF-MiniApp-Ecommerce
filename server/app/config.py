from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 4000

    # Postgres from docker-compose.yml at the project root.
    database_url: str = (
        "postgresql+asyncpg://vmarket:vmarket@127.0.0.1:5433/vmarket"
    )

    vapp_base_url: str = "http://127.0.0.1:4001"
    vapp_client_id: str = "v-market-dev"
    vapp_client_secret: str = "dev-secret"

    jwt_secret: str = "dev-jwt-secret-change-before-deploy"
    jwt_ttl_seconds: int = 60 * 60 * 12


settings = Settings()
