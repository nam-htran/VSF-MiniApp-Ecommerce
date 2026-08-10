"""The trained decoder, loaded once and called away from the async loop."""

import asyncio
import logging
import math
import sys
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

CODEBOOK_SIZES = [128, 64, 32]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Prediction:
    semantic_id: tuple[int, int, int]
    score: float


_model = None
_torch = None
_lock = asyncio.Semaphore(1)


def load() -> None:
    """Load the optional model. Configured paths are treated as required."""
    global _model, _torch
    if not settings.recommendation_checkpoint_path:
        return
    if not settings.recommendation_semantic_ids_path:
        raise RuntimeError(
            "RECOMMENDATION_SEMANTIC_IDS_PATH is required with a checkpoint"
        )

    ai_source = Path(__file__).resolve().parents[3] / "ai-recommendation" / "src"
    sys.path.insert(0, str(ai_source))

    import numpy as np
    import pyarrow.parquet as pq
    import torch
    from modules.model import EncoderDecoderRetrievalModel

    table = pq.read_table(
        settings.recommendation_semantic_ids_path,
        columns=["sid_0", "sid_1", "sid_2"],
    )
    codebooks = torch.from_numpy(
        np.column_stack(
            [
                table[column].combine_chunks().to_numpy(zero_copy_only=False)
                for column in table.column_names
            ]
        )
    ).long()
    model = EncoderDecoderRetrievalModel(
        codebooks=codebooks,
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
