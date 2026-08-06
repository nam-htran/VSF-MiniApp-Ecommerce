from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence, Union

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import torch
from torch import Tensor
from torch.utils.data import Dataset

from data.schemas import SeqBatch


IndexLike = Union[int, Sequence[int], np.ndarray, Tensor]
SESSION_CACHE_VERSION = "vmarket-session-indices-v1"


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


def prepare_vmarket_session_cache(
    session_root: str,
    catalog_index_path: str,
    cache_root: str,
    max_sequence_length: int = 20,
    force: bool = False,
    batch_size: int = 100_000,
) -> Path:
    """Map product IDs in session Parquet files to fixed-width product indices."""
    session_root = Path(session_root).expanduser().resolve()
    catalog_index_path = Path(catalog_index_path).expanduser().resolve()
    cache_root = Path(cache_root).expanduser().resolve()
    manifest_path = cache_root / "session_cache_manifest.json"

    if max_sequence_length <= 0:
        raise ValueError("max_sequence_length must be positive")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    source_paths = {
        "train": session_root / "model_sessions_train.parquet",
        "validation": session_root / "model_sessions_validation.parquet",
    }
    for path in [catalog_index_path, *source_paths.values()]:
        if not path.is_file():
            raise FileNotFoundError(path)

    expected_rows = {
        split: pq.ParquetFile(path).metadata.num_rows
        for split, path in source_paths.items()
    }
    expected_manifest = {
        "contract_version": SESSION_CACHE_VERSION,
        "max_sequence_length": max_sequence_length,
        "catalog_rows": pq.ParquetFile(catalog_index_path).metadata.num_rows,
        "catalog_size_bytes": catalog_index_path.stat().st_size,
        "session_rows": expected_rows,
        "session_size_bytes": {
            split: path.stat().st_size for split, path in source_paths.items()
        },
    }

    if manifest_path.is_file() and not force:
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if all(existing_manifest.get(key) == value for key, value in expected_manifest.items()):
            for split, rows in expected_rows.items():
                ids = np.load(cache_root / f"{split}_session_ids.i32.npy", mmap_mode="r")
                targets = np.load(cache_root / f"{split}_session_targets.i32.npy", mmap_mode="r")
                if ids.shape != (rows, max_sequence_length) or targets.shape != (rows,):
                    raise ValueError(f"Invalid cached session shapes for {split}")
            return manifest_path

    cache_root.mkdir(parents=True, exist_ok=True)
    catalog = pd.read_parquet(
        catalog_index_path,
        columns=["product_index", "product_id"],
    )
    if catalog["product_id"].isna().any() or not catalog["product_id"].is_unique:
        raise ValueError("Catalog index must contain unique, non-null product IDs")
    expected_indices = np.arange(len(catalog), dtype=catalog["product_index"].dtype)
    if not np.array_equal(catalog["product_index"].to_numpy(), expected_indices):
        raise ValueError("product_index must be contiguous and match catalog row order")
    product_to_index = dict(
        zip(catalog["product_id"].astype(str), catalog["product_index"].astype(int))
    )

    truncation_counts = {}
    for split, source_path in source_paths.items():
        parquet_file = pq.ParquetFile(source_path)
        rows = parquet_file.metadata.num_rows
        print(f"Preparing {split} session cache: {rows:,} rows")
        ids_path = cache_root / f"{split}_session_ids.i32.npy"
        targets_path = cache_root / f"{split}_session_targets.i32.npy"
        session_ids = np.lib.format.open_memmap(
            ids_path,
            mode="w+",
            dtype=np.int32,
            shape=(rows, max_sequence_length),
        )
        session_targets = np.lib.format.open_memmap(
            targets_path,
            mode="w+",
            dtype=np.int32,
            shape=(rows,),
        )

        offset = 0
        truncated = 0
        for record_batch in parquet_file.iter_batches(
            batch_size=batch_size,
            columns=["prev_items", "next_item"],
        ):
            prev_items = record_batch.column(0).to_pylist()
            next_items = record_batch.column(1).to_pylist()
            batch_rows = len(prev_items)
            batch_ids = np.full(
                (batch_rows, max_sequence_length),
                -1,
                dtype=np.int32,
            )
            batch_targets = np.empty(batch_rows, dtype=np.int32)

            for row, (history, target) in enumerate(zip(prev_items, next_items)):
                if not history:
                    raise ValueError(f"Empty session history in {source_path} at row {offset + row}")
                retained_history = history[-max_sequence_length:]
                truncated += int(len(history) > max_sequence_length)
                try:
                    mapped_history = [product_to_index[item] for item in retained_history]
                    mapped_target = product_to_index[target]
                except KeyError as error:
                    raise ValueError(
                        f"Unknown product ID {error.args[0]!r} in {source_path} at row {offset + row}"
                    ) from error
                batch_ids[row, -len(mapped_history) :] = mapped_history
                batch_targets[row] = mapped_target

            session_ids[offset : offset + batch_rows] = batch_ids
            session_targets[offset : offset + batch_rows] = batch_targets
            offset += batch_rows
            if offset % (batch_size * 10) < batch_rows:
                print(f"  mapped {offset:,}/{rows:,} rows")

        if offset != rows:
            raise ValueError(f"Session row mismatch for {split}: {offset} != {rows}")
        session_ids.flush()
        session_targets.flush()
        truncation_counts[split] = truncated
        print(f"Completed {split} session cache; truncated histories: {truncated:,}")

    manifest = {
        **expected_manifest,
        "truncated_sessions": truncation_counts,
        "padding_side": "left",
        "truncation_side": "left_keep_most_recent",
        "files": {
            split: {
                "ids": str(cache_root / f"{split}_session_ids.i32.npy"),
                "targets": str(cache_root / f"{split}_session_targets.i32.npy"),
            }
            for split in source_paths
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


class VMarketSeqData(Dataset):
    """Fixed-width session indices prepared by prepare_vmarket_session_cache."""

    def __init__(self, cache_root: str, split: str) -> None:
        if split not in {"train", "validation"}:
            raise ValueError("split must be either 'train' or 'validation'")
        self.cache_root = Path(cache_root).expanduser().resolve()
        manifest_path = self.cache_root / "session_cache_manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"Session cache manifest not found: {manifest_path}")
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if self.manifest.get("contract_version") != SESSION_CACHE_VERSION:
            raise ValueError("Unsupported session cache contract")
        self.ids = np.load(
            self.cache_root / f"{split}_session_ids.i32.npy",
            mmap_mode="r",
        )
        self.targets = np.load(
            self.cache_root / f"{split}_session_targets.i32.npy",
            mmap_mode="r",
        )
        if len(self.ids) != len(self.targets):
            raise ValueError("Session IDs and targets have different row counts")

    def __len__(self) -> int:
        return len(self.targets)

    def __getitem__(self, index: int) -> SeqBatch:
        item_ids = torch.from_numpy(
            np.array(self.ids[index], dtype=np.int64, copy=True)
        )
        target = torch.tensor([int(self.targets[index])], dtype=torch.long)
        return SeqBatch(
            user_ids=torch.tensor([-1], dtype=torch.long),
            ids=item_ids,
            ids_fut=target,
            x=torch.empty(0, dtype=torch.float32),
            x_fut=torch.empty(0, dtype=torch.float32),
            seq_mask=item_ids.ge(0),
        )
