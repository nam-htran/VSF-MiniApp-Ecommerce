from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

import numpy as np
import pandas as pd
import torch
from torch import Tensor
from torch.utils.data import Dataset

from data.schemas import SeqBatch


IndexLike = Union[int, Sequence[int], np.ndarray, Tensor]


class VMarketItemData(Dataset):
    """Item embeddings and their stable global product indices."""

    def __init__(
        self,
        root: str,
        train_test_split: str = "all",
        eval_fraction: float = 0.05,
        split_seed: int = 2026,
        embedding_filename: str = "global_product_embeddings.f16.npy",
        index_filename: str = "global_embedding_index.parquet",
        expected_input_dim: int | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.embedding_path = self.root / embedding_filename
        self.index_path = self.root / index_filename

        if not self.embedding_path.is_file():
            raise FileNotFoundError(f"Embedding matrix not found: {self.embedding_path}")
        if not self.index_path.is_file():
            raise FileNotFoundError(f"Embedding index not found: {self.index_path}")
        if train_test_split not in {"train", "eval", "all"}:
            raise ValueError("train_test_split must be one of: train, eval, all")
        if not 0.0 < eval_fraction < 1.0:
            raise ValueError("eval_fraction must be between 0 and 1")

        self._embeddings = np.load(self.embedding_path, mmap_mode="r")
        if self._embeddings.ndim != 2:
            raise ValueError(
                f"Expected a 2D embedding matrix, found shape {self._embeddings.shape}"
            )
        if expected_input_dim is not None and self._embeddings.shape[1] != expected_input_dim:
            raise ValueError(
                f"Expected embedding dimension {expected_input_dim}, "
                f"found {self._embeddings.shape[1]}"
            )

        self.index_frame = pd.read_parquet(
            self.index_path,
            columns=["product_index", "product_id"],
        )
        if len(self.index_frame) != len(self._embeddings):
            raise ValueError(
                "Embedding matrix and index have different row counts: "
                f"{len(self._embeddings)} != {len(self.index_frame)}"
            )
        if self.index_frame["product_id"].isna().any():
            raise ValueError("Embedding index contains null product_id values")
        if not self.index_frame["product_id"].is_unique:
            raise ValueError("Embedding index contains duplicate product_id values")

        product_indices = self.index_frame["product_index"].to_numpy()
        expected_indices = np.arange(len(self.index_frame), dtype=product_indices.dtype)
        if not np.array_equal(product_indices, expected_indices):
            raise ValueError("product_index must be contiguous and match embedding row order")

        num_items = len(self._embeddings)
        if num_items < 2 and train_test_split != "all":
            raise ValueError("At least two products are required for a train/eval split")

        if train_test_split == "all":
            self._row_indices = np.arange(num_items, dtype=np.int64)
        else:
            generator = np.random.default_rng(split_seed)
            permutation = generator.permutation(num_items)
            eval_size = min(num_items - 1, max(1, int(np.ceil(num_items * eval_fraction))))
            self._row_indices = (
                permutation[eval_size:]
                if train_test_split == "train"
                else permutation[:eval_size]
            )

        self.train_test_split = train_test_split
        self.input_dim = int(self._embeddings.shape[1])

    def __len__(self) -> int:
        return len(self._row_indices)

    @staticmethod
    def _to_numpy_indices(index: IndexLike) -> tuple[np.ndarray, bool]:
        if isinstance(index, Tensor):
            index = index.detach().cpu().numpy()
        array = np.asarray(index)
        is_scalar = array.ndim == 0
        return np.atleast_1d(array).astype(np.int64, copy=False), is_scalar

    def __getitem__(self, index: IndexLike) -> SeqBatch:
        local_indices, is_scalar = self._to_numpy_indices(index)
        row_indices = self._row_indices[local_indices]
        embeddings = np.array(
            self._embeddings[row_indices],
            dtype=np.float32,
            copy=True,
        )

        item_ids = torch.from_numpy(row_indices.astype(np.int64, copy=False)).unsqueeze(-1)
        x = torch.from_numpy(embeddings)
        batch = SeqBatch(
            user_ids=torch.full_like(item_ids, -1),
            ids=item_ids,
            ids_fut=torch.full_like(item_ids, -1),
            x=x,
            x_fut=torch.full_like(x, -1),
            seq_mask=torch.ones_like(item_ids, dtype=torch.bool),
        )

        if not is_scalar:
            return batch
        return SeqBatch(*(value[0] for value in batch))
