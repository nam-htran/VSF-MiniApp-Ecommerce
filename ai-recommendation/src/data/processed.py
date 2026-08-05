from enum import Enum

import gin

from data.vmarket import VMarketItemData


@gin.constants_from_enum
class RecDataset(Enum):
    VMARKET = 1


class ItemData(VMarketItemData):
    """Compatibility wrapper used by the RQ-VAE tokenizer and trainer."""

    def __init__(self, *args, dataset: RecDataset = RecDataset.VMARKET, **kwargs):
        if dataset is not RecDataset.VMARKET:
            raise ValueError(f"Unsupported dataset: {dataset}")
        super().__init__(*args, **kwargs)


class SeqData:
    """Reserved for the V-Market generative-retrieval stage."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "V-Market session loading belongs to the decoder stage and is not implemented yet."
        )
