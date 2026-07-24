from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The secrets this repo ships so a fresh clone runs without setup. They are
# in git, so they are public — which makes them exactly the values a real
# deployment must not keep. `_refuse_shipped_secrets` below turns "somebody
# forgot to set this" from a silent hole into a refusal to start.
_DEV_ONLY_SECRETS = {
    "jwt_secret": "dev-jwt-secret-change-before-deploy",
    "payment_ipn_secret": "dev-ipn-secret",
    "vapp_client_secret": "dev-secret",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Only "development" may run on the shipped secrets above. Anything
    # else has to supply its own — see the validator at the bottom.
    app_env: str = "development"

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

    jwt_secret: str = "dev-jwt-secret-change-before-deploy"
    jwt_ttl_seconds: int = 60 * 60 * 12

    @model_validator(mode="after")
    def _refuse_shipped_secrets(self) -> "Settings":
        """Outside development, refuse to boot on the repo's own secrets.

        A default is the right call for a secret nobody has set *locally* —
        it keeps `git clone` to `pytest` a single step. It is the wrong call
        in production, where a missing value would otherwise mean the app
        runs happily on a key anyone can read off GitHub. `jwt_secret` is
        the sharp one: knowing it is enough to mint a session for any user,
        ADMIN included, and no amount of care in the authorisation layer
        helps once tokens can be forged.
        """
        if self.app_env == "development":
            return self

        problems = [
            f"{name.upper()} is still the repo's development value"
            for name, dev in sorted(_DEV_ONLY_SECRETS.items())
            if getattr(self, name) == dev
        ]
        if not self.payment_verify_hash:
            problems.append(
                "PAYMENT_VERIFY_HASH is off, so IPN signatures are not "
                "checked and anyone can claim an order was paid"
            )
        if problems:
            raise ValueError(
                f"APP_ENV={self.app_env!r} refuses these: "
                + "; ".join(problems)
                + ". Set them in .env."
            )
        return self


settings = Settings()
