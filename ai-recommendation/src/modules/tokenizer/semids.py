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
from torch.utils.data import BatchSampler
from torch.utils.data import DataLoader
from torch.utils.data import SequentialSampler

BATCH_SIZE = 16


class PrecomputedSemanticIdTokenizer(nn.Module):
    def __init__(self, corpus_ids: Tensor) -> None:
        super().__init__()
        self.register_buffer("cached_ids", corpus_ids)

    @torch.no_grad
    def forward(self, batch: SeqBatch) -> TokenizedSeqBatch:
        batch_size, sequence_length = batch.ids.shape
        num_layers = self.cached_ids.shape[1]

        sem_ids = self.cached_ids[batch.ids.clamp_min(0)].reshape(
            batch_size, -1
        ).long()
        seq_mask = batch.seq_mask.repeat_interleave(num_layers, dim=1)
        sem_ids[~seq_mask] = -1
        sem_ids_fut = self.cached_ids[batch.ids_fut].reshape(batch_size, -1).long()

        token_types = torch.arange(num_layers, device=batch.ids.device)
        return TokenizedSeqBatch(
            sem_ids=sem_ids,
            sem_ids_fut=sem_ids_fut,
            seq_mask=seq_mask,
            token_type_ids=token_types.repeat(batch_size, sequence_length),
            token_type_ids_fut=token_types.repeat(batch_size, 1),
        )


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

        self.codebook_sizes = list(codebook_sizes)
        self.n_layers = len(self.codebook_sizes)
        self.reset()

    def reset(self):
        self.cached_ids = None

    @torch.no_grad
    @eval_mode
    def precompute_corpus_ids(self, movie_dataset: ItemData) -> Tensor:
        cached_ids = []
        sampler = BatchSampler(
            SequentialSampler(range(len(movie_dataset))),
            batch_size=512,
            drop_last=False,
        )
        dataloader = DataLoader(
            movie_dataset,
            sampler=sampler,
            shuffle=False,
            collate_fn=lambda batch: batch[0],
        )
        for batch in dataloader:
            batch_ids = self.forward(batch_to(batch, self.rq_vae.device)).sem_ids
            cached_ids.append(batch_ids)
        self.cached_ids = torch.cat(cached_ids, dim=0)

        return self.cached_ids

    def _tokenize_seq_batch_from_cached(self, ids: Tensor) -> Tensor:
        return rearrange(
            self.cached_ids[ids.flatten(), :], "(b n) d -> b (n d)", n=ids.shape[1]
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
            sem_ids=sem_ids,
            sem_ids_fut=sem_ids_fut,
            seq_mask=seq_mask,
            token_type_ids=token_type_ids,
            token_type_ids_fut=token_type_ids_fut,
        )
