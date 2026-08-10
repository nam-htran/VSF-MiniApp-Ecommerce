"""Continuously assign frozen RQ-VAE Semantic IDs to catalogue products."""

import asyncio
import logging
import re
import unicodedata
from pathlib import Path

from app.config import settings
from app.db import SessionFactory
from app.products import store as products
from app.recommendations import predictor

CODEBOOK_SIZES = [128, 64, 32]
EMBEDDING_DIM = 256
WHITESPACE = re.compile(r"\s+")
logger = logging.getLogger(__name__)

_text_model = None
_rqvae = None
_torch = None
_wake_event: asyncio.Event | None = None
_task: asyncio.Task | None = None


def build_product_text(name: str, description: str) -> str:
    def clean(value: str) -> str:
        return WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip()

    return f"title: {clean(name)} | description: {clean(description)}"


def load() -> None:
    """Eagerly load the configured encoder and frozen RQ-VAE on CPU."""
    global _text_model, _rqvae, _torch
    if not settings.semantic_rqvae_checkpoint_path or _rqvae is not None:
        return
    if settings.semantic_batch_size < 1:
        raise RuntimeError("SEMANTIC_BATCH_SIZE must be at least 1")
    if settings.semantic_cpu_threads < 1:
        raise RuntimeError("SEMANTIC_CPU_THREADS must be at least 1")
    if settings.semantic_scan_interval_seconds <= 0:
        raise RuntimeError("SEMANTIC_SCAN_INTERVAL_SECONDS must be positive")
    if settings.semantic_debounce_seconds < 0:
        raise RuntimeError("SEMANTIC_DEBOUNCE_SECONDS cannot be negative")

    checkpoint_path = Path(settings.semantic_rqvae_checkpoint_path)
    if not checkpoint_path.is_file():
        raise RuntimeError(f"RQ-VAE checkpoint not found: {checkpoint_path}")

    import numpy as np
    import torch
    from modules.quantize import QuantizeForwardMode
    from modules.rqvae import RqVae
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(settings.semantic_cpu_threads)
    rqvae = RqVae(
        input_dim=EMBEDDING_DIM,
        embed_dim=32,
        hidden_dims=[256, 128, 64],
        codebook_sizes=CODEBOOK_SIZES,
        codebook_kmeans_init=False,
        codebook_normalize=False,
        codebook_sim_vq=False,
        codebook_mode=QuantizeForwardMode.ROTATION_TRICK,
        n_cat_features=0,
        commitment_weight=0.25,
    )
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    state = {_plain_key(key): value for key, value in checkpoint["model"].items()}
    rqvae.load_state_dict(state)
    rqvae.eval()

    text_model = SentenceTransformer(
        settings.semantic_embedding_model,
        trust_remote_code=True,
        device="cpu",
    )

    smoke = text_model.encode(
        ["title: smoke test | description: startup validation"],
        batch_size=1,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
        truncate_dim=EMBEDDING_DIM,
        device="cpu",
    )
    smoke = np.asarray(smoke, dtype=np.float32)
    _validate_embeddings(smoke, 1, np)
    with torch.inference_mode():
        semantic_ids = rqvae.get_semantic_ids(torch.from_numpy(smoke)).sem_ids
    _validate_semantic_ids(semantic_ids, 1)

    _text_model = text_model
    _rqvae = rqvae
    _torch = torch
    logger.info("Semantic indexer models loaded on CPU")


def _plain_key(key: str) -> str:
    prefixes = ("module.", "_orig_mod.")
    while key.startswith(prefixes):
        key = next(
            key[len(prefix) :] for prefix in prefixes if key.startswith(prefix)
        )
    return key


def _validate_embeddings(embeddings, expected: int, np) -> None:
    if embeddings.shape != (expected, EMBEDDING_DIM):
        raise RuntimeError(f"Unexpected Jina embedding shape: {embeddings.shape}")
    if not np.isfinite(embeddings).all():
        raise RuntimeError("Jina returned NaN or Inf")


def _validate_semantic_ids(semantic_ids, expected: int) -> None:
    if tuple(semantic_ids.shape) != (expected, len(CODEBOOK_SIZES)):
        raise RuntimeError(f"Unexpected RQ-VAE SID shape: {semantic_ids.shape}")
    for level, size in enumerate(CODEBOOK_SIZES):
        values = semantic_ids[:, level]
        if ((values < 0) | (values >= size)).any().item():
            raise RuntimeError(f"RQ-VAE produced an invalid SID at level {level}")


def ready() -> bool:
    return _rqvae is not None


def _infer(batch: list[products.PendingSemanticProduct]) -> list[tuple[int, int, int]]:
    import numpy as np

    texts = [build_product_text(item.name, item.description) for item in batch]
    embeddings = _text_model.encode(
        texts,
        batch_size=len(texts),
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
        truncate_dim=EMBEDDING_DIM,
        device="cpu",
    )
    embeddings = np.asarray(embeddings, dtype=np.float32)
    _validate_embeddings(embeddings, len(batch), np)

    with _torch.inference_mode():
        semantic_ids = _rqvae.get_semantic_ids(
            _torch.from_numpy(embeddings)
        ).sem_ids
    _validate_semantic_ids(semantic_ids, len(batch))
    return [tuple(row) for row in semantic_ids.cpu().tolist()]


async def _index_one_batch() -> int:
    async with SessionFactory() as session:
        pending = await products.pending_semantic_products(
            session, settings.semantic_batch_size
        )
    if not pending:
        return 0

    semantic_ids = await asyncio.to_thread(_infer, pending)
    async with SessionFactory() as session:
        written = await products.write_semantic_ids(
            session, list(zip(pending, semantic_ids))
        )
    logger.info("Semantic indexer wrote %s/%s products", written, len(pending))
    if written:
        await predictor.refresh_catalogue()
    return len(pending)


async def _run() -> None:
    first_scan = True
    while True:
        try:
            if not first_scan:
                try:
                    await asyncio.wait_for(
                        _wake_event.wait(),
                        timeout=settings.semantic_scan_interval_seconds,
                    )
                except TimeoutError:
                    pass
                else:
                    _wake_event.clear()
                    await asyncio.sleep(settings.semantic_debounce_seconds)
            first_scan = False

            while await _index_one_batch() == settings.semantic_batch_size:
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Semantic indexing batch failed; it will be retried")
            await asyncio.sleep(5)
            first_scan = True


def start() -> asyncio.Task | None:
    global _task, _wake_event
    if not ready():
        return None
    if _task is None or _task.done():
        _wake_event = asyncio.Event()
        _task = asyncio.create_task(_run(), name="semantic-indexer")
    return _task


def wake() -> None:
    if _wake_event is not None:
        _wake_event.set()


async def stop() -> None:
    global _task, _wake_event
    if _task is not None:
        _task.cancel()
        await asyncio.gather(_task, return_exceptions=True)
    _task = None
    _wake_event = None
