"""The trained decoder, loaded once and called away from the async loop."""

import asyncio
import logging
import math
from dataclasses import dataclass

from app.config import settings

CODEBOOK_SIZES = [128, 64, 32]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Prediction:
    semantic_id: tuple[int, int, int]
    score: float


_model = None
_torch = None
_catalogue_size = 0
_lock = asyncio.Semaphore(1)


async def _active_catalogue_sids() -> list[tuple[int, int, int]]:
    from app.db import SessionFactory
    from app.products import store as products

    async with SessionFactory() as session:
        return await products.active_semantic_ids(session)


def configured() -> bool:
    return bool(settings.recommendation_checkpoint_path)


async def load() -> None:
    """Load the optional model with a mask from the live catalogue."""
    global _model, _torch, _catalogue_size
    if not configured():
        return
    if ready():
        await refresh_catalogue()
        return

    import torch
    from modules.model import EncoderDecoderRetrievalModel

    sids = await _active_catalogue_sids()
    _catalogue_size = len(sids)
    catalogue_sids = torch.tensor(sids, dtype=torch.long).reshape(
        -1, len(CODEBOOK_SIZES)
    )
    model = EncoderDecoderRetrievalModel(
        codebooks=catalogue_sids,
        codebook_sizes=CODEBOOK_SIZES,
        t5_d_model=384,
        t5_num_heads=6,
        t5_d_ff=1024,
        t5_num_layers=4,
        top_k_for_generation=10,
        should_add_sep_token=True,
    )
    checkpoint = torch.load(
        settings.recommendation_checkpoint_path,
        map_location="cpu",
        weights_only=False,
    )
    state = {_plain_key(key): value for key, value in checkpoint["model"].items()}
    model.load_state_dict(state)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _model = model.to(device).eval()
    _torch = torch


def catalogue_size() -> int:
    """How many distinct Semantic IDs the current beam mask was built from.

    Beam search can only generate a prefix the mask holds, so a mask built
    from a catalogue that has since changed does not fail — it quietly
    generates confident answers from the wrong set of clusters.
    """
    return _catalogue_size


async def refresh_catalogue() -> None:
    """Atomically rebuild beam constraints from ACTIVE products in Postgres."""
    global _catalogue_size
    if not ready():
        return
    async with _lock:
        sids = await _active_catalogue_sids()
        catalogue_sids = _torch.tensor(sids, dtype=_torch.long).reshape(
            -1, len(CODEBOOK_SIZES)
        )
        _model.set_catalogue_sids(catalogue_sids)
        _catalogue_size = len(sids)


def _plain_key(key: str) -> str:
    prefixes = ("module.", "_orig_mod.")
    while key.startswith(prefixes):
        key = next(
            key[len(prefix) :] for prefix in prefixes if key.startswith(prefix)
        )
    return key


def ready() -> bool:
    return _model is not None


def _predict(history: list[tuple[int, int, int]]) -> list[Prediction]:
    input_ids = _torch.tensor(history, device=_model.device).reshape(1, -1)
    attention_mask = _torch.ones_like(input_ids)
    with _torch.inference_mode(), _torch.autocast(
        device_type=_model.device.type,
        dtype=_torch.float16,
        enabled=_model.device.type == "cuda",
    ):
        semantic_ids, scores = _model.generate(attention_mask, input_ids)
    predictions = [
        Prediction(tuple(semantic_id), float(score))
        for semantic_id, score in zip(
            semantic_ids[0].tolist(), scores[0].tolist()
        )
    ]
    return predictions if all(math.isfinite(item.score) for item in predictions) else []


async def predict(history: list[tuple[int, int, int]]) -> list[Prediction]:
    if not ready() or not history:
        return []
    async with _lock:
        try:
            return await asyncio.to_thread(_predict, history)
        except Exception:
            logger.exception("Recommendation inference failed")
            return []
