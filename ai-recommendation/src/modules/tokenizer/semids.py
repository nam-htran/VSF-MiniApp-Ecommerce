import torch
import pandas as pd

from data.processed import ItemData
from data.schemas import SeqBatch
from data.schemas import TokenizedSeqBatch
from data.utils import batch_to
from einops import rearrange
from modules.utils import eval_mode
from modules.rqvae import RqVae
from typing import List
from typing import Optional
from torch import nn
from torch import Tensor
from torch.utils.data import DataLoader

BATCH_SIZE = 16


class SemanticIdTokenizer(nn.Module):
    """
    Tokenizes a batch of sequences of item features into a batch of sequences of semantic ids.
    """

    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        hidden_dims: List[int],
        codebook_size: int,
        n_layers: int = 3,
        n_cat_feats: int = 18,
        commitment_weight: float = 0.25,
        rqvae_weights_path: Optional[str] = None,
        rqvae_codebook_normalize: bool = False,
        rqvae_sim_vq: bool = False,
    ) -> None:
        super().__init__()

        self.rq_vae = RqVae(
            input_dim=input_dim,
            embed_dim=output_dim,
            hidden_dims=hidden_dims,
            codebook_size=codebook_size,
            codebook_kmeans_init=False,
            codebook_normalize=rqvae_codebook_normalize,
            codebook_sim_vq=rqvae_sim_vq,
            n_layers=n_layers,
            n_cat_features=n_cat_feats,
            commitment_weight=commitment_weight,
        )

        if rqvae_weights_path is not None:
            self.rq_vae.load_pretrained(rqvae_weights_path)

        self.rq_vae.eval()

        self.codebook_size = codebook_size
        self.n_layers = n_layers
        self.reset()

    def reset(self):
        self.cached_ids = None

    @property
    def sem_ids_dim(self):
        return self.n_layers + 1

    @torch.no_grad
    @eval_mode
    def precompute_corpus_ids(self, item_dataset: ItemData) -> Tensor:
        """Encode the corpus and append a stable per-SID collision index.

        The previous implementation compared every new batch with every cached SID,
        which becomes quadratic for a global catalog. This implementation encodes
        linearly and computes collision ranks with a single group-by operation.
        """
        dataloader = DataLoader(
            item_dataset,
            batch_size=512,
            shuffle=False,
            pin_memory=torch.cuda.is_available(),
        )
        raw_id_parts = []
        for batch in dataloader:
            device_batch = batch_to(batch, self.rq_vae.device)
            raw_ids = self.rq_vae.get_semantic_ids(device_batch.x).sem_ids
            raw_id_parts.append(raw_ids.cpu())

        raw_ids = torch.cat(raw_id_parts, dim=0).to(torch.long)
        columns = [f"sid_{index}" for index in range(self.n_layers)]
        sid_frame = pd.DataFrame(raw_ids.numpy(), columns=columns)
        collision_index = torch.from_numpy(
            sid_frame.groupby(columns, sort=False).cumcount().to_numpy(dtype="int64")
        )
        self.cached_ids = torch.cat([raw_ids, collision_index.unsqueeze(1)], dim=1)

        return self.cached_ids

    def _tokenize_seq_batch_from_cached(self, ids: Tensor) -> Tensor:
        flat_ids = ids.flatten()
        if flat_ids.device != self.cached_ids.device:
            selected = self.cached_ids[flat_ids.cpu()].to(flat_ids.device)
        else:
            selected = self.cached_ids[flat_ids]
        return rearrange(
            selected, "(b n) d -> b (n d)", n=ids.shape[1]
        )

    @torch.no_grad
    @eval_mode
    def forward(self, batch: SeqBatch) -> TokenizedSeqBatch:
        # TODO: Handle output inconstency in If-else.
        # If block has to return 3-sized ids for use in precompute_corpus_ids
        # Else block has to return deduped 4-sized ids for use in decoder training.
        if self.cached_ids is None or batch.ids.max() >= self.cached_ids.shape[0]:
            B, N = batch.ids.shape
            sem_ids = self.rq_vae.get_semantic_ids(batch.x).sem_ids
            D = sem_ids.shape[-1]
            seq_mask, sem_ids_fut = None, None
        else:
            B, N = batch.ids.shape
            _, D = self.cached_ids.shape
            sem_ids = self._tokenize_seq_batch_from_cached(batch.ids)
            seq_mask = batch.seq_mask.repeat_interleave(D, dim=1)
            sem_ids[~seq_mask] = -1

            sem_ids_fut = self._tokenize_seq_batch_from_cached(batch.ids_fut)

        token_type_ids = torch.arange(D, device=sem_ids.device).repeat(B, N)
        token_type_ids_fut = torch.arange(D, device=sem_ids.device).repeat(B, 1)
        return TokenizedSeqBatch(
            user_ids=batch.user_ids,
            sem_ids=sem_ids,
            sem_ids_fut=sem_ids_fut,
            seq_mask=seq_mask,
            token_type_ids=token_type_ids,
            token_type_ids_fut=token_type_ids_fut,
        )
