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
    VMARKET = 1


class ItemData(Dataset):
    def __init__(
        self,
        root: str,
        dataset: RecDataset = RecDataset.VMARKET,
        train_test_split: str = "all",
        eval_fraction: float = 0.05,
        split_seed: int = 2026,
        embedding_filename: str = "global_product_embeddings.f16.npy",
        index_filename: str = "global_embedding_index.parquet",
        **_,
    ) -> None:
        if dataset is not RecDataset.VMARKET:
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
            user_ids=torch.full_like(item_ids, -1),
            ids=item_ids,
            ids_fut=torch.full_like(item_ids, -1),
            x=x,
            x_fut=torch.full_like(x, -1),
            seq_mask=torch.ones_like(item_ids, dtype=torch.bool),
        )
        return SeqBatch(*(value[0] for value in batch)) if scalar else batch


class SeqData(Dataset):
    def __init__(
        self,
        root: str,
        dataset: RecDataset = RecDataset.VMARKET,
        is_train: bool = True,
        max_seq_len: int = 20,
        session_root: str | None = None,
        index_path: str | None = None,
        index_filename: str = "global_embedding_index.parquet",
        **_,
    ) -> None:
        if dataset is not RecDataset.VMARKET:
            raise ValueError(f"Unsupported dataset: {dataset}")

        root = Path(root)
        session_root = Path(session_root) if session_root else root
        session_filename = (
            "model_sessions_train.parquet"
            if is_train
            else "model_sessions_validation.parquet"
        )

        index_path = Path(index_path) if index_path else root / index_filename
        index = pd.read_parquet(
            index_path,
            columns=["product_index", "product_id"],
        )
        product_to_index = dict(
            zip(index["product_id"].astype(str), index["product_index"])
        )
        sessions = pd.read_parquet(
            session_root / session_filename,
            columns=["prev_items", "next_item"],
        )

        self.ids = np.full((len(sessions), max_seq_len), -1, dtype=np.int32)
        self.targets = np.empty(len(sessions), dtype=np.int32)

        for row, (history, target) in enumerate(
            sessions.itertuples(index=False, name=None)
        ):
            history_ids = [product_to_index[str(item)] for item in history[-max_seq_len:]]
            self.ids[row, -len(history_ids) :] = history_ids
            self.targets[row] = product_to_index[str(target)]

    def __len__(self):
        return len(self.targets)

    def __getitem__(self, index):
        item_ids = torch.from_numpy(self.ids[index].astype(np.int64))
        target = torch.tensor([self.targets[index]], dtype=torch.long)
        return SeqBatch(
            user_ids=torch.tensor(-1, dtype=torch.long),
            ids=item_ids,
            ids_fut=target,
            x=torch.empty(0),
            x_fut=torch.empty(0),
            seq_mask=item_ids >= 0,
        )
