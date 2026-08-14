import pandas as pd
import torch


SID_COLUMNS = ["sid_0", "sid_1", "sid_2", "sid_suffix"]
CONTROL_TOKENS = [
    "<SEARCH>",
    "<REC_CLICK>",
    "<REC_HISTORY>",
    "<ANS>",
    "<PI>",
]


def validate_sid_table(
    semantic_ids: pd.DataFrame,
    codebook_sizes=(128, 64, 32),
) -> int:
    """Validate the frozen RQ-VAE mapping and return the suffix vocabulary size."""
    missing = set(SID_COLUMNS) - set(semantic_ids.columns)
    if missing:
        raise ValueError(f"Missing SID columns: {sorted(missing)}")
    if semantic_ids.empty:
        raise ValueError("Semantic ID table is empty")
    if semantic_ids[SID_COLUMNS].isnull().any().any():
        raise ValueError("Semantic ID table contains null values")
    if semantic_ids.duplicated(SID_COLUMNS).any():
        raise ValueError("Full Semantic IDs must be unique")

    for column, size in zip(SID_COLUMNS[:3], codebook_sizes):
        values = semantic_ids[column]
        if values.min() < 0 or values.max() >= size:
            raise ValueError(f"{column} contains values outside [0, {size})")

    suffix = semantic_ids["sid_suffix"]
    if suffix.min() < 0:
        raise ValueError("sid_suffix must be non-negative")
    return int(suffix.max()) + 1


def add_sid_tokens(
    tokenizer,
    model,
    codebook_sizes=(128, 64, 32),
    suffix_size=1,
):
    """Add four disjoint SID token spaces and return their tokenizer IDs."""
    level_names = ("a", "b", "c", "u")
    level_sizes = (*codebook_sizes, suffix_size)
    tokens_by_level = [
        [f"<{name}{index}>" for index in range(size)]
        for name, size in zip(level_names, level_sizes)
    ]
    tokenizer.add_special_tokens(
        {
            "additional_special_tokens": [
                *CONTROL_TOKENS,
                *(token for level in tokens_by_level for token in level),
            ]
        }
    )
    model.resize_token_embeddings(len(tokenizer))

    token_ids_by_level = []
    for tokens in tokens_by_level:
        token_ids = tokenizer.convert_tokens_to_ids(tokens)
        token_ids_by_level.append(torch.tensor(token_ids, dtype=torch.long))
    return token_ids_by_level
