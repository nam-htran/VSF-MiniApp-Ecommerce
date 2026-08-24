import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

AI_SOURCE = Path(__file__).resolve().parents[2] / "ai-recommendation" / "src"
if str(AI_SOURCE) not in sys.path:
    sys.path.insert(0, str(AI_SOURCE))

from artifact_paths import rqvae_checkpoint, transformer_checkpoint  # noqa: E402


def _path_or_empty(path: Path | None) -> str:
    return str(path) if path is not None else ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 4000

    database_url: str = (
        "postgresql+asyncpg://vmarket:vmarket@127.0.0.1:5433/vmarket"
    )

    vapp_base_url: str = "http://127.0.0.1:4001"
    vapp_client_id: str = "v-market-dev"
    vapp_client_secret: str

    nominatim_base_url: str = "https://nominatim.openstreetmap.org"

    recommendation_checkpoint_path: str = _path_or_empty(transformer_checkpoint())
    semantic_rqvae_checkpoint_path: str = _path_or_empty(rqvae_checkpoint())
    semantic_embedding_model: str = (
        "jinaai/jina-embeddings-v5-text-nano-clustering"
    )
    semantic_embedding_revision: str = "1f2f45acee2315af5aba78cf0d09e920727978e0"
    semantic_batch_size: int = 8
    semantic_scan_interval_seconds: float = 60
    semantic_debounce_seconds: float = 1
    semantic_cpu_threads: int = 4

    payment_ipn_secret: str
    payment_verify_hash: bool = True
    order_hold_minutes: int = 15
    payment_grace_minutes: int = 30
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 60
    # The demo courier. There is no logistics feed behind this shop, so a
    # paid order walks CONFIRMED -> SHIPPING -> DELIVERED on a timer
    # instead. Switch it off and fulfilment is the seller's job alone.
    #
    # The two windows are the buyer's tracker read back in seconds: it
    # animates a 6-minute trip and starts "Đang giao" at 0.4 of it and
    # "Đã giao" at 0.99. Keeping the numbers in step is what stops the
    # widget from announcing a delivery the order rows know nothing about
    # (see OrderTrackingMap, which also refuses to run ahead of them).
    fulfilment_sim_enabled: bool = True
    fulfilment_ship_after_seconds: int = 144
    fulfilment_deliver_after_seconds: int = 356
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
