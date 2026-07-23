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

    # Reverse geocoding runs server-side: the MiniApp cannot reach a
    # third-party host (domain whitelist), but the server can. Swap the
    # base URL to point at a self-hosted Nominatim later if needed.
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"

    # Payment IPN: the mock (standing in for V-App's payment gateway) posts
    # a server-to-server notification here when an order is paid. The shared
    # secret signs it (HMAC); the flag lets verification be turned off while
    # debugging. Keep the secret equal to the mock's PAYMENT_IPN_SECRET.
    payment_ipn_secret: str = "dev-ipn-secret"
    payment_verify_hash: bool = True
    # How long an unpaid order holds its stock. Placing an order decrements
    # stock immediately — that is the hold — and this is how long before it
    # is handed back. Deliberately short so the behaviour is demonstrable in
    # a sitting; a real shop would use hours.
    order_hold_minutes: int = 15
    # Extra time an order keeps its stock once the buyer has opened a
    # payment session. Longer than the plain hold because a bank app, an OTP
    # and poor signal are all slower than browsing.
    payment_grace_minutes: int = 30

    jwt_secret: str = "dev-jwt-secret-change-before-deploy"
    jwt_ttl_seconds: int = 60 * 60 * 12


settings = Settings()
