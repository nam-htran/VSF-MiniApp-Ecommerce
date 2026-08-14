from typing import NamedTuple

from torch import Tensor


class SeqBatch(NamedTuple):
    ids: Tensor
    ids_fut: Tensor
    x: Tensor
    x_fut: Tensor
    seq_mask: Tensor
