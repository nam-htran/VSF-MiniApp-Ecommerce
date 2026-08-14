from enum import Enum
from pathlib import Path

import gin
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset

from data.schemas import SeqBatch


@gin.constants_from_enum
class RecDataset(Enum):
    KUAISEARCH = 1


class ItemData(Dataset):
    def __init__(
        self,
        root: str,
        dataset: RecDataset = RecDataset.KUAISEARCH,
        train_test_split: str = "all",
        eval_fraction: float = 0.05,
        split_seed: int = 2026,
        embedding_filename: str = "global_product_embeddings.f16.npy",
        index_filename: str = "global_embedding_index.parquet",
        **_,
    ) -> None:
        if dataset is not RecDataset.KUAISEARCH:
            raise ValueError(f"Unsupported dataset: {dataset}")

        root = Path(root)
        self.embeddings = np.load(root / embedding_filename, mmap_mode="r")
        self.index = pd.read_parquet(
            root / index_filename,
            columns=["product_index", "product_id"],
        )

        if len(self.embeddings) != len(self.index):
            raise ValueError("Embedding matrix and product index have different lengths")
        if self.embeddings.ndim != 2:
            raise ValueError("Expected a 2D embedding matrix")
        if not np.array_equal(
            self.index["product_index"].to_numpy(),
            np.arange(len(self.index)),
        ):
            raise ValueError("product_index must match the embedding row order")

        rows = np.arange(len(self.index))
        if train_test_split != "all":
            shuffled = np.random.default_rng(split_seed).permutation(rows)
            eval_size = max(1, int(len(rows) * eval_fraction))
            rows = (
                shuffled[eval_size:]
                if train_test_split == "train"
                else shuffled[:eval_size]
            )
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        if isinstance(index, torch.Tensor):
            index = index.cpu().numpy()
        index = np.asarray(index)
        scalar = index.ndim == 0
        row_ids = self.rows[np.atleast_1d(index).astype(np.int64)]

        item_ids = torch.from_numpy(row_ids.astype(np.int64)).unsqueeze(-1)
        x = torch.from_numpy(
            np.asarray(self.embeddings[row_ids], dtype=np.float32).copy()
        )
        batch = SeqBatch(
            ids=item_ids,
            ids_fut=torch.full_like(item_ids, -1),
            x=x,
            x_fut=torch.full_like(x, -1),
            seq_mask=torch.ones_like(item_ids, dtype=torch.bool),
        )
        return SeqBatch(*(value[0] for value in batch)) if scalar else batch
