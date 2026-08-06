import torch

from data.schemas import SeqBatch
from einops import rearrange
from functools import cached_property
from modules.encoder import MLP
from modules.loss import CategoricalReconstuctionLoss
from modules.loss import ReconstructionLoss
from modules.loss import QuantizeLoss
from modules.normalize import l2norm
from modules.quantize import Quantize
from modules.quantize import QuantizeForwardMode
from huggingface_hub import PyTorchModelHubMixin
from typing import List
from typing import NamedTuple
from torch import nn
from torch import Tensor

torch.set_float32_matmul_precision("high")


class RqVaeOutput(NamedTuple):
    embeddings: Tensor
    residuals: Tensor
    sem_ids: Tensor
    quantize_loss: Tensor
    quantize_loss_per_layer: Tensor


class RqVaeComputedLosses(NamedTuple):
    loss: Tensor
    reconstruction_loss: Tensor
    rqvae_loss: Tensor
    quantize_loss_per_layer: Tensor
    residual_norm_per_layer: Tensor
    selected_code_norm_per_layer: Tensor
    codebook_norm_per_layer: Tensor
    p_unique_ids: Tensor


class RqVae(nn.Module, PyTorchModelHubMixin):
    def __init__(
        self,
        input_dim: int,
        embed_dim: int,
        hidden_dims: List[int],
        codebook_sizes: List[int],
        codebook_kmeans_init: bool = True,
        codebook_normalize: bool = False,
        codebook_sim_vq: bool = False,
        codebook_mode: QuantizeForwardMode = QuantizeForwardMode.GUMBEL_SOFTMAX,
        commitment_weight: float = 0.25,
        n_cat_features: int = 18,
    ) -> None:
        self._config = locals()

        super().__init__()

        self.input_dim = input_dim
        self.embed_dim = embed_dim
        self.hidden_dims = hidden_dims
        self.codebook_sizes = tuple(int(size) for size in codebook_sizes)
        if not self.codebook_sizes or any(size <= 0 for size in self.codebook_sizes):
            raise ValueError("codebook_sizes must contain positive integers")
        self.n_layers = len(self.codebook_sizes)
        self.commitment_weight = commitment_weight
        self.n_cat_feats = n_cat_features

        self.layers = nn.ModuleList(
            modules=[
                Quantize(
                    embed_dim=embed_dim,
                    n_embed=codebook_size,
                    forward_mode=codebook_mode,
                    do_kmeans_init=codebook_kmeans_init,
                    codebook_normalize=i == 0 and codebook_normalize,
                    sim_vq=codebook_sim_vq,
                    commitment_weight=commitment_weight,
                )
                for i, codebook_size in enumerate(self.codebook_sizes)
            ]
        )

        self.encoder = MLP(
            input_dim=input_dim,
            hidden_dims=hidden_dims,
            out_dim=embed_dim,
            normalize=codebook_normalize,
        )

        self.decoder = MLP(
            input_dim=embed_dim,
            hidden_dims=hidden_dims[-1::-1],
            out_dim=input_dim,
            normalize=False,
        )

        self.reconstruction_loss = (
            CategoricalReconstuctionLoss(n_cat_features)
            if n_cat_features != 0
            else ReconstructionLoss()
        )

    @cached_property
    def config(self) -> dict:
        return self._config

    @property
    def device(self) -> torch.device:
        return next(self.encoder.parameters()).device

    def load_pretrained(self, path: str) -> None:
        state = torch.load(path, map_location=self.device, weights_only=False)
        self.load_state_dict(state["model"])
        print(f"---Loaded RQVAE Iter {state['iter']}---")

    def encode(self, x: Tensor) -> Tensor:
        return self.encoder(x)

    def decode(self, x: Tensor) -> Tensor:
        return self.decoder(x)

    @torch.no_grad()
    def initialize_codebooks(self, x: Tensor) -> None:
        """Initialize every residual codebook without building the training loss graph."""
        x = x.to(next(self.encoder.parameters()).dtype)
        residual = self.encode(x)
        was_training = self.training
        self.eval()
        for layer in self.layers:
            layer._kmeans_init(residual)
            quantized = layer(residual, temperature=0.2)
            residual = residual - quantized.embeddings
        self.train(was_training)

    def get_semantic_ids(self, x: Tensor, gumbel_t: float = 0.001) -> RqVaeOutput:
        x = x.to(next(self.encoder.parameters()).dtype)
        res = self.encode(x)

        quantize_loss = 0
        embs, residuals, sem_ids, quantize_losses = [], [], [], []

        for layer in self.layers:
            residuals.append(res)
            quantized = layer(res, temperature=gumbel_t)
            quantize_loss += quantized.loss
            quantize_losses.append(quantized.loss)
            emb, id = quantized.embeddings, quantized.ids
            res = res - emb
            sem_ids.append(id)
            embs.append(emb)

        quantize_loss_per_layer = torch.stack(quantize_losses, dim=-1)
        return RqVaeOutput(
            embeddings=rearrange(embs, "b h d -> h d b"),
            residuals=rearrange(residuals, "b h d -> h d b"),
            sem_ids=rearrange(sem_ids, "b d -> d b"),
            quantize_loss=quantize_loss,
            quantize_loss_per_layer=quantize_loss_per_layer,
        )

    @torch.compile(mode="reduce-overhead")
    def forward(self, batch: SeqBatch, gumbel_t: float) -> RqVaeComputedLosses:
        x = batch.x
        quantized = self.get_semantic_ids(x, gumbel_t)
        embs, residuals = quantized.embeddings, quantized.residuals
        x_hat = self.decode(embs.sum(axis=-1))
        x_hat = torch.cat(
            [l2norm(x_hat[..., : -self.n_cat_feats]), x_hat[..., -self.n_cat_feats :]],
            axis=-1,
        )

        reconstuction_loss = self.reconstruction_loss(x_hat, x)
        rqvae_loss = quantized.quantize_loss
        loss = (reconstuction_loss + rqvae_loss).mean()

        with torch.no_grad():
            quantize_loss_per_layer = quantized.quantize_loss_per_layer.mean(dim=0)
            residual_norm_per_layer = residuals.norm(dim=1).mean(dim=0)
            selected_code_norm_per_layer = embs.norm(dim=1).mean(dim=0)
            codebook_norm_per_layer = torch.stack(
                [
                    layer.out_proj(layer.embedding.weight).norm(dim=1).mean()
                    for layer in self.layers
                ]
            )
            p_unique_ids = (
                ~torch.triu(
                    (
                        rearrange(quantized.sem_ids, "b d -> b 1 d")
                        == rearrange(quantized.sem_ids, "b d -> 1 b d")
                    ).all(axis=-1),
                    diagonal=1,
                )
            ).all(axis=1).sum() / quantized.sem_ids.shape[0]

        return RqVaeComputedLosses(
            loss=loss,
            reconstruction_loss=reconstuction_loss.mean(),
            rqvae_loss=rqvae_loss.mean(),
            quantize_loss_per_layer=quantize_loss_per_layer,
            residual_norm_per_layer=residual_norm_per_layer,
            selected_code_norm_per_layer=selected_code_norm_per_layer,
            codebook_norm_per_layer=codebook_norm_per_layer,
            p_unique_ids=p_unique_ids,
        )
