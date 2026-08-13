from typing import NamedTuple
from torch import Tensor

FUT_SUFFIX = "_fut"


# No user field. Amazon-M2 sessions are anonymous — sessions_train.csv holds
# only prev_items, next_item and locale — so there is no identity to carry.
# This makes the task session-based recommendation rather than sequential
# recommendation: the collaborative signal comes from patterns across many
# sessions, not from a per-user parameter.


class SeqBatch(NamedTuple):
    ids: Tensor
    ids_fut: Tensor
    x: Tensor
    x_fut: Tensor
    seq_mask: Tensor


class TokenizedSeqBatch(NamedTuple):
    sem_ids: Tensor
    sem_ids_fut: Tensor
    seq_mask: Tensor
    token_type_ids: Tensor
    token_type_ids_fut: Tensor
