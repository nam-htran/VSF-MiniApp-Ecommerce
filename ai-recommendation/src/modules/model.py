import torch
import torch.nn as nn
import torch.nn.functional as F

from data.schemas import TokenizedSeqBatch
from typing import NamedTuple, Optional, Sequence
from torch import Tensor
from transformers import T5EncoderModel
from transformers.models.t5.modeling_t5 import T5Config, T5Stack
from transformers.cache_utils import DynamicCache, EncoderDecoderCache

torch.set_float32_matmul_precision("high")


class ModelOutput(NamedTuple):
    loss: Tensor
    logits: Tensor
    loss_d: Tensor


class GenerationOutput(NamedTuple):
    sem_ids: Tensor
    log_probas: Tensor


class EncoderDecoderRetrievalModel(nn.Module):
    """HuggingFace T5 encoder-decoder for sequential recommendation.

    Uses T5EncoderModel for encoding and T5Stack for decoding. Per-hierarchy
    linear output heads project decoder hidden states to codebook logits.
    Beam search uses deterministic top candidates with log-probability accumulation
    and a float("-inf") mask for invalid SID prefixes.
    """

    def __init__(
        self,
        codebooks: torch.Tensor,
        codebook_sizes: Sequence[int],
        t5_d_model: int = 128,
        t5_num_heads: int = 6,
        t5_d_ff: int = 1024,
        t5_num_layers: int = 4,
        top_k_for_generation: int = 10,
        should_add_sep_token: bool = True,
        num_user_bins: Optional[int] = None,
    ):
        super().__init__()

        self.codebook_sizes = tuple(int(size) for size in codebook_sizes)
        if not self.codebook_sizes or any(size <= 0 for size in self.codebook_sizes):
            raise ValueError("codebook_sizes must contain positive integers")
        self.num_hierarchies = len(self.codebook_sizes)
        if codebooks.ndim != 2 or codebooks.shape[1] != self.num_hierarchies:
            raise ValueError(
                f"Expected codebooks with shape [N, {self.num_hierarchies}]"
            )
        self.top_k_for_generation = top_k_for_generation
        self.register_buffer("codebooks", codebooks)
        for hierarchy, codebook_size in enumerate(self.codebook_sizes):
            values = codebooks[:, hierarchy]
            if values.min().item() < 0 or values.max().item() >= codebook_size:
                raise ValueError(
                    f"Hierarchy {hierarchy} contains IDs outside [0, {codebook_size - 1}]"
                )
        for prefix_length in range(1, self.num_hierarchies + 1):
            prefix_keys = self._encode_prefix(codebooks[:, :prefix_length])
            self.register_buffer(
                f"valid_prefix_keys_{prefix_length}",
                torch.unique(prefix_keys, sorted=True),
                persistent=False,
            )

        hierarchy_offsets = [0]
        for size in self.codebook_sizes[:-1]:
            hierarchy_offsets.append(hierarchy_offsets[-1] + size)
        self.register_buffer(
            "hierarchy_offsets",
            torch.tensor(hierarchy_offsets, dtype=torch.long),
            persistent=False,
        )
        vocabulary_size = sum(self.codebook_sizes)

        encoder_config = T5Config(
            vocab_size=vocabulary_size,
            d_model=t5_d_model,
            num_heads=t5_num_heads,
            d_ff=t5_d_ff,
            num_layers=t5_num_layers,
            is_decoder=False,
        )
        self.encoder = T5EncoderModel(encoder_config)

        decoder_config = T5Config(
            vocab_size=vocabulary_size,
            d_model=t5_d_model,
            num_heads=t5_num_heads,
            d_ff=t5_d_ff,
            num_layers=t5_num_layers,
            is_decoder=True,
            is_encoder_decoder=False,
        )
        self.t5_decoder = T5Stack(decoder_config)
        self.bos_token = nn.Parameter(torch.randn(1, t5_d_model), requires_grad=True)
        self.decoder_mlp = nn.ModuleList(
            [
                nn.Linear(t5_d_model, codebook_size, bias=False)
                for codebook_size in self.codebook_sizes
            ]
        )

        # Each hierarchy occupies a non-overlapping range in one shared token table.
        self.item_sid_embedding_table = nn.Embedding(
            num_embeddings=vocabulary_size,
            embedding_dim=t5_d_model,
        )

        self.user_embedding = (
            nn.Embedding(num_user_bins, t5_d_model) if num_user_bins else None
        )
        self.sep_token = (
            nn.Parameter(torch.randn(1, t5_d_model), requires_grad=True)
            if should_add_sep_token
            else None
        )

    @property
    def device(self) -> torch.device:
        return next(self.parameters()).device

    def _is_cache_valid(self, kv) -> bool:
        if isinstance(kv, (EncoderDecoderCache, DynamicCache)):
            return len(kv) > 0
        return isinstance(kv, tuple)

    def _add_repeating_offset_to_rows(
        self,
        input_sids: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """Add per-hierarchy offsets so a single embedding table covers all hierarchies."""
        if input_sids.ndim != 2:
            raise ValueError("Input tensor must be 2-dimensional.")
        _, num_cols = input_sids.shape
        offsets = self.hierarchy_offsets.to(input_sids.device)
        num_repeats = (num_cols + self.num_hierarchies - 1) // self.num_hierarchies
        repeated_offsets = offsets.repeat(num_repeats)[:num_cols]
        result = input_sids + repeated_offsets
        if attention_mask is not None:
            result = torch.where(attention_mask.bool(), result, torch.zeros_like(result))
        return result

    def _inject_sep_token_between_sids(
        self,
        id_embeddings: torch.Tensor,
        attention_mask: torch.Tensor,
        sep_token: torch.Tensor,
        num_hierarchies: int,
    ):
        """Inject a separator embedding after each item's token group."""
        batch_size, seq_len, emb_dim = id_embeddings.size()
        item_count = seq_len // num_hierarchies
        reshaped_emb = id_embeddings.view(batch_size, item_count, num_hierarchies, -1)
        reshaped_mask = attention_mask.view(batch_size, item_count, num_hierarchies)
        sep = sep_token.unsqueeze(0).expand(batch_size, item_count, -1).unsqueeze(-2)
        id_embeddings = torch.cat([reshaped_emb, sep], dim=-2)
        attention_mask = torch.cat([reshaped_mask, reshaped_mask[:, :, [-1]]], dim=-1)
        return id_embeddings.reshape(batch_size, -1, emb_dim), attention_mask.reshape(
            batch_size, -1
        )

    def _encode_prefix(self, prefix: torch.Tensor) -> torch.Tensor:
        if prefix.ndim != 2 or not 1 <= prefix.shape[1] <= self.num_hierarchies:
            raise ValueError("Invalid SID prefix shape")
        keys = torch.zeros(prefix.shape[0], dtype=torch.long, device=prefix.device)
        for hierarchy in range(prefix.shape[1]):
            keys = keys * self.codebook_sizes[hierarchy] + prefix[:, hierarchy].long()
        return keys

    def _check_valid_prefix(self, prefix: torch.Tensor) -> torch.Tensor:
        """Return whether each mixed-radix SID prefix occurs in the catalog."""
        valid_keys = getattr(self, f"valid_prefix_keys_{prefix.shape[1]}")
        query_keys = self._encode_prefix(prefix)
        positions = torch.searchsorted(valid_keys, query_keys)
        in_bounds = positions < len(valid_keys)
        safe_positions = positions.clamp_max(len(valid_keys) - 1)
        return in_bounds & valid_keys[safe_positions].eq(query_keys)

    def encoder_forward_pass(self, attention_mask, input_ids, user_id=None):
        shifted = self._add_repeating_offset_to_rows(
            input_sids=input_ids,
            attention_mask=attention_mask,
        )
        inputs_embeds = self.item_sid_embedding_table(shifted)

        if self.sep_token is not None:
            inputs_embeds, attention_mask = self._inject_sep_token_between_sids(
                id_embeddings=inputs_embeds,
                attention_mask=attention_mask,
                sep_token=self.sep_token,
                num_hierarchies=self.num_hierarchies,
            )

        if user_id is not None and self.user_embedding is not None:
            user_embeds = self.user_embedding(
                torch.remainder(user_id[:, 0], self.user_embedding.num_embeddings)
            )
            inputs_embeds = torch.cat([user_embeds.unsqueeze(1), inputs_embeds], dim=1)
            attention_mask = torch.cat(
                [
                    torch.ones(attention_mask.size(0), 1, device=attention_mask.device),
                    attention_mask,
                ],
                dim=1,
            )

        encoder_output = self.encoder(
            inputs_embeds=inputs_embeds,
            attention_mask=attention_mask,
        ).last_hidden_state
        return encoder_output, attention_mask

    def decoder_forward_pass(
        self,
        attention_mask=None,
        future_ids=None,
        encoder_output=None,
        attention_mask_for_encoder=None,
        use_cache=False,
        past_key_values=None,
    ):
        if future_ids is not None:
            shifted = self._add_repeating_offset_to_rows(
                input_sids=future_ids,
                attention_mask=torch.ones_like(future_ids)
                if attention_mask is None
                else attention_mask,
            )
            inputs_embeds = self.item_sid_embedding_table(shifted)

            if not self._is_cache_valid(past_key_values):
                bos = self.bos_token.unsqueeze(0).expand(future_ids.size(0), 1, -1)
                inputs_embeds = torch.cat([bos, inputs_embeds], dim=1)
                if attention_mask is not None:
                    attention_mask = torch.cat(
                        [
                            torch.ones(future_ids.size(0), 1, device=future_ids.device),
                            attention_mask,
                        ],
                        dim=1,
                    )
            else:
                inputs_embeds = inputs_embeds[:, -1:, :]
        else:
            inputs_embeds = self.bos_token.unsqueeze(0).expand(
                encoder_output.size(0), 1, -1
            )

        out = self.t5_decoder(
            inputs_embeds=inputs_embeds,
            attention_mask=attention_mask,
            encoder_hidden_states=encoder_output,
            encoder_attention_mask=attention_mask_for_encoder,
            use_cache=use_cache,
            past_key_values=past_key_values,
        )
        if use_cache:
            return out.last_hidden_state, out.past_key_values
        return out.last_hidden_state

    def forward(self, batch: TokenizedSeqBatch) -> ModelOutput:
        input_ids = batch.sem_ids
        attention_mask = batch.seq_mask.long()
        fut_ids = batch.sem_ids_fut

        encoder_output, attention_mask_for_encoder = self.encoder_forward_pass(
            attention_mask=attention_mask,
            input_ids=input_ids,
            user_id=batch.user_ids,
        )
        decoder_output = self.decoder_forward_pass(
            future_ids=fut_ids,
            encoder_output=encoder_output,
            attention_mask_for_encoder=attention_mask_for_encoder,
            use_cache=False,
        )[:, :-1]  # [B, num_hierarchies, d_model]

        total_loss = torch.tensor(0.0, device=decoder_output.device)
        loss_d = []
        for h in range(self.num_hierarchies):
            logits = self.decoder_mlp[h](decoder_output[:, h])
            h_loss = F.cross_entropy(logits, fut_ids[:, h].long())
            total_loss = total_loss + h_loss
            loss_d.append(h_loss.detach())

        return ModelOutput(loss=total_loss, logits=None, loss_d=torch.stack(loss_d))

    @torch.no_grad()
    def generate(self, attention_mask, input_ids, user_id=None):
        """Generate top-k semantic IDs using constrained beam search.

        For each hierarchy level, selects the highest-probability candidate tokens,
        scores them using cumulative log-probabilities with a float("-inf") mask for
        invalid SID prefixes, and keeps the top-k highest-scoring candidates.

        Returns:
            generated_ids: [B, top_k, num_hierarchies]
            log_probas:    [B, top_k]
        """
        B = input_ids.size(0)
        k = self.top_k_for_generation

        enc_out, enc_mask = self.encoder_forward_pass(
            attention_mask=attention_mask,
            input_ids=input_ids,
            user_id=user_id,
        )
        rep_enc = enc_out.repeat_interleave(k, dim=0)
        rep_mask = enc_mask.repeat_interleave(k, dim=0)

        generated = None  # [B, k, h] grows with each hierarchy step
        log_probas = 0
        past_kv = EncoderDecoderCache(DynamicCache(), DynamicCache())

        for h in range(self.num_hierarchies):
            n_cands = self.codebook_sizes[h]
            if generated is not None:
                cur_enc, cur_mask = rep_enc, rep_mask
                squeezed = generated.reshape(-1, h)
            else:
                cur_enc, cur_mask = enc_out, enc_mask
                squeezed = None

            dec_out, past_kv = self.decoder_forward_pass(
                future_ids=squeezed,
                encoder_output=cur_enc,
                attention_mask_for_encoder=cur_mask,
                use_cache=True,
                past_key_values=past_kv,
            )

            probas = F.softmax(self.decoder_mlp[h](dec_out[:, -1, :]), dim=-1)
            samples = torch.topk(probas, k=n_cands, dim=-1).indices
            samp_log_p = torch.log(torch.gather(probas, 1, samples))

            if generated is None:
                is_valid = self._check_valid_prefix(samples.reshape(-1, 1)).reshape(
                    B, n_cands
                )
                scores, idx = samp_log_p.masked_fill(~is_valid, float("-inf")).sort(
                    -1, descending=True
                )
                top_k_idx = idx[:, :k]
                generated = torch.gather(samples, 1, top_k_idx).unsqueeze(
                    -1
                )  # [B, k, 1]
                log_probas = scores[:, :k]
                past_kv = EncoderDecoderCache(DynamicCache(), DynamicCache())
            else:
                prev = generated.reshape(-1, h).repeat_interleave(n_cands, dim=0)
                prefix = torch.cat([prev, samples.reshape(-1, 1)], dim=1)
                is_valid = self._check_valid_prefix(prefix).reshape(B, k * n_cands)
                scores, idx = (
                    (
                        samp_log_p.reshape(B, k * n_cands)
                        + log_probas.repeat_interleave(n_cands, dim=1)
                    )
                    .masked_fill(~is_valid, float("-inf"))
                    .sort(-1, descending=True)
                )

                top_k_idx = idx[:, :k]
                parent_beam_idx = top_k_idx // n_cands
                parent_global = (
                    parent_beam_idx
                    + torch.arange(B, device=parent_beam_idx.device).unsqueeze(1) * k
                ).flatten()
                past_kv.reorder_cache(parent_global)

                parent_ids = torch.gather(
                    generated, 1, parent_beam_idx.unsqueeze(-1).expand(-1, -1, h)
                )
                new_ids = torch.gather(
                    samples.reshape(B, k * n_cands), 1, top_k_idx
                ).unsqueeze(-1)
                generated = torch.cat([parent_ids, new_ids], dim=-1)  # [B, k, h+1]
                log_probas = scores[:, :k]

        return generated, log_probas

    @torch.no_grad()
    def generate_next_sem_id(
        self,
        batch: TokenizedSeqBatch,
        top_k: bool = True,
        temperature: int = 1,
    ) -> GenerationOutput:
        input_ids = batch.sem_ids
        attention_mask = batch.seq_mask.long()
        generated_ids, log_probas = self.generate(
            attention_mask=attention_mask,
            input_ids=input_ids,
            user_id=batch.user_ids,
        )
        return GenerationOutput(sem_ids=generated_ids, log_probas=log_probas)
