import torch

from data.processed import ItemData
from data.utils import batch_to
from modules.utils import eval_mode
from modules.rqvae import RqVae
from typing import List
from typing import Optional
from torch import nn
from torch import Tensor
from torch.utils.data import BatchSampler
from torch.utils.data import DataLoader
from torch.utils.data import SequentialSampler


class SemanticIdTokenizer(nn.Module):
    """Encode the item corpus with the trained RQ-VAE."""

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
            batch = batch_to(batch, self.rq_vae.device)
            batch_ids = self.rq_vae.get_semantic_ids(batch.x).sem_ids
            cached_ids.append(batch_ids)
        self.cached_ids = torch.cat(cached_ids, dim=0)

        return self.cached_ids
