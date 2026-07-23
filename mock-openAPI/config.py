from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 4001

    # Must match VAPP_CLIENT_ID / VAPP_CLIENT_SECRET in server/
    client_id: str = "v-market-dev"
    client_secret: str = "dev-secret"

    # Its own database, not V-Market's — see docker/initdb/01-databases.sql
    database_url: str = (
        "postgresql+asyncpg://vmarket:vmarket@127.0.0.1:5433/vapp_mock"
    )

    # Short on purpose, so expiry and reuse bugs surface early.
    authcode_ttl_seconds: int = 60
    access_token_ttl_seconds: int = 3600

    # Payment gateway simulation. On a confirmed payment the mock posts an
    # IPN to the merchant (server/), signed with a shared secret, and
    # retries on this backoff until it gets a 200. Keep the secret equal to
    # server/'s PAYMENT_IPN_SECRET.
    merchant_ipn_url: str = "http://127.0.0.1:4000/payments/ipn"
    payment_ipn_secret: str = "dev-ipn-secret"
    ipn_retry_delays: list[int] = [2, 4, 8, 16]


settings = Settings()
