import torch

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
        codebook_sizes: List[int],
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
            codebook_sizes=codebook_sizes,
            codebook_kmeans_init=False,
            codebook_normalize=rqvae_codebook_normalize,
            codebook_sim_vq=rqvae_sim_vq,
            n_cat_features=n_cat_feats,
            commitment_weight=commitment_weight,
        )

        if rqvae_weights_path is not None:
            self.rq_vae.load_pretrained(rqvae_weights_path)

        self.rq_vae.eval()

        self.codebook_sizes = tuple(int(size) for size in codebook_sizes)
        self.n_layers = len(self.codebook_sizes)
        self.reset()

    def reset(self):
        self.cached_ids = None

    @property
    def sem_ids_dim(self):
        return self.n_layers

    @torch.no_grad
    @eval_mode
    def precompute_corpus_ids(self, item_dataset: ItemData) -> Tensor:
        """Encode the corpus into cluster SIDs without an item-level suffix."""
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

        self.cached_ids = torch.cat(raw_id_parts, dim=0).to(torch.long)

        return self.cached_ids

    def _tokenize_seq_batch_from_cached(self, ids: Tensor) -> Tensor:
        flat_ids = ids.flatten()
        safe_flat_ids = flat_ids.clamp_min(0)
        if flat_ids.device != self.cached_ids.device:
            selected = self.cached_ids[safe_flat_ids.cpu()].to(flat_ids.device)
        else:
            selected = self.cached_ids[safe_flat_ids]
        return rearrange(
            selected, "(b n) d -> b (n d)", n=ids.shape[1]
        )

    @torch.no_grad
    @eval_mode
    def forward(self, batch: SeqBatch) -> TokenizedSeqBatch:
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


class CachedSemanticIdTokenizer(nn.Module):
    """Tokenize product-index sessions from a fixed corpus SID table."""

    def __init__(self, corpus_ids: Tensor) -> None:
        super().__init__()
        if corpus_ids.ndim != 2 or corpus_ids.shape[1] == 0:
            raise ValueError("corpus_ids must have shape [num_products, num_hierarchies]")
        if corpus_ids.min().item() < 0:
            raise ValueError("corpus_ids cannot contain negative values")
        self.register_buffer("cached_ids", corpus_ids.to(torch.long), persistent=False)
        self.n_layers = corpus_ids.shape[1]

    def _tokenize(self, ids: Tensor) -> Tensor:
        flat_ids = ids.flatten()
        if flat_ids.max().item() >= len(self.cached_ids):
            raise IndexError("Session product index exceeds the corpus SID table")
        safe_ids = flat_ids.clamp_min(0)
        selected = self.cached_ids[safe_ids]
        return rearrange(selected, "(b n) d -> b (n d)", n=ids.shape[1])

    @torch.no_grad
    def forward(self, batch: SeqBatch) -> TokenizedSeqBatch:
        batch_size, sequence_length = batch.ids.shape
        sem_ids = self._tokenize(batch.ids)
        seq_mask = batch.seq_mask.repeat_interleave(self.n_layers, dim=1)
        sem_ids = sem_ids.masked_fill(~seq_mask, -1)
        sem_ids_fut = self._tokenize(batch.ids_fut)
        token_types = torch.arange(self.n_layers, device=sem_ids.device)
        return TokenizedSeqBatch(
            user_ids=batch.user_ids,
            sem_ids=sem_ids,
            sem_ids_fut=sem_ids_fut,
            seq_mask=seq_mask,
            token_type_ids=token_types.repeat(batch_size, sequence_length),
            token_type_ids_fut=token_types.repeat(batch_size, 1),
        )
