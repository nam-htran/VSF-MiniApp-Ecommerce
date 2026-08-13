"""Locate local serving artifacts produced by the training notebooks."""

import re
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = AI_ROOT / "output"
TRANSFORMER_OUTPUT = OUTPUT_ROOT / "transformer"
RQVAE_OUTPUT = OUTPUT_ROOT / "rq-vae"
CHECKPOINT_NAME = re.compile(r"checkpoint_(\d+)\.pt")


def _latest_checkpoint(folder: Path) -> Path | None:
    numbered = []
    for path in folder.glob("checkpoint_*.pt"):
        match = CHECKPOINT_NAME.fullmatch(path.name)
        if match:
            numbered.append((int(match.group(1)), path))
    return max(numbered, default=(None, None), key=lambda item: item[0])[1]


def transformer_checkpoint() -> Path | None:
    best = TRANSFORMER_OUTPUT / "best_checkpoint.pt"
    return best if best.is_file() else _latest_checkpoint(TRANSFORMER_OUTPUT)


def rqvae_checkpoint() -> Path | None:
    return _latest_checkpoint(RQVAE_OUTPUT)
