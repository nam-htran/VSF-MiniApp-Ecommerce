from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Secrets have no default: .env is their only source, and a missing
    one stops the process instead of falling back to a value from git."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 4000

    # Postgres from docker-compose.yml at the project root.
    database_url: str = (
        "postgresql+asyncpg://vmarket:vmarket@127.0.0.1:5433/vmarket"
    )

    vapp_base_url: str = "http://127.0.0.1:4001"
    vapp_client_id: str = "v-market-dev"
    vapp_client_secret: str

    # Reverse geocoding runs server-side: the MiniApp cannot reach a
    # third-party host (domain whitelist), but the server can. Swap the
    # base URL to point at a self-hosted Nominatim later if needed.
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"

    recommendation_checkpoint_path: str = ""
    recommendation_semantic_ids_path: str = ""

    # Payment IPN: the mock (standing in for V-App's payment gateway) posts
    # a server-to-server notification here when an order is paid. The shared
    # secret signs it (HMAC); the flag lets verification be turned off while
    # debugging. Keep the secret equal to the mock's PAYMENT_IPN_SECRET.
    payment_ipn_secret: str
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
    # Background jobs: release expired stock holds, and ask the gateway
    # about payments whose webhook never arrived. Off in tests, which move
    # the clock by hand and must not race a loop doing the same work.
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 60
    # V-App user ids that get the ADMIN role on login, comma separated.
    # Config rather than a database flag on purpose: there is no admin to
    # grant the first admin, and a self-service "make me admin" endpoint is
    # exactly the thing not to build. Empty by default — nobody is an
    # operator unless deployment says so.
    admin_vapp_user_ids: str = ""

    @property
    def admin_ids(self) -> set[str]:
        return {
            piece.strip()
            for piece in self.admin_vapp_user_ids.split(",")
            if piece.strip()
        }

    jwt_secret: str
    jwt_ttl_seconds: int = 60 * 60 * 12


settings = Settings()
