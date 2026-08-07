import torch
import torch.nn as nn
import torch.nn.functional as F

from data.schemas import TokenizedSeqBatch
from typing import NamedTuple, Optional
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
    """HuggingFace T5 encoder-decoder for session-based recommendation.

    Uses T5EncoderModel for encoding and T5Stack for decoding. Per-hierarchy
    linear output heads project decoder hidden states to codebook logits —
    one head per level rather than a single softmax over the whole vocabulary,
    because only codebook h's tokens are legal at step h. Decoding is
    constrained beam search: cumulative log-probabilities over the full
    codebook with a float("-inf") mask for SID prefixes no item uses.

    Session-based, not sequential: there is no user embedding. TIGER hashes a
    user id into 2000 buckets and prepends it to the input, but Amazon-M2
    sessions carry no identity to hash, and TIGER's own ablation (Table 8)
    puts the gain at +0.015% Recall@10 — smaller than the seed-to-seed spread
    in their Table 9. Whose history gets fed in is what personalises the
    result, not a per-user parameter.
    """

    def __init__(
        self,
        codebooks: torch.Tensor,
        num_hierarchies: int,
        num_embeddings_per_hierarchy: int,
        t5_d_model: int = 128,
        t5_num_heads: int = 6,
        t5_d_ff: int = 1024,
        t5_num_layers: int = 4,
        top_k_for_generation: int = 10,
        should_add_sep_token: bool = True,
    ):
        super().__init__()

        self.num_hierarchies = num_hierarchies
        self.num_embeddings_per_hierarchy = num_embeddings_per_hierarchy
        self.top_k_for_generation = top_k_for_generation

        codebooks = codebooks.long()
        for depth in range(1, num_hierarchies + 1):
            keys = self._encode_prefix(codebooks[:, :depth])
            self.register_buffer(
                f"valid_prefix_keys_{depth}",
                torch.unique(keys, sorted=True),
                persistent=False,
            )

        encoder_config = T5Config(
            vocab_size=num_embeddings_per_hierarchy * num_hierarchies,
            d_model=t5_d_model,
            num_heads=t5_num_heads,
            d_ff=t5_d_ff,
            num_layers=t5_num_layers,
            is_decoder=False,
        )
        self.encoder = T5EncoderModel(encoder_config)

        decoder_config = T5Config(
            vocab_size=num_embeddings_per_hierarchy * num_hierarchies,
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
                nn.Linear(t5_d_model, num_embeddings_per_hierarchy, bias=False)
                for _ in range(num_hierarchies)
            ]
        )

        # Shared embedding table; hierarchy h, token t maps to index h * codebook_size + t.
        self.item_sid_embedding_table = nn.Embedding(
            num_embeddings=num_embeddings_per_hierarchy * num_hierarchies,
            embedding_dim=t5_d_model,
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
        codebook_size: int,
        num_hierarchies: int,
        attention_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """Add per-hierarchy offsets so a single embedding table covers all hierarchies."""
        if input_sids.ndim != 2:
            raise ValueError("Input tensor must be 2-dimensional.")
        _, num_cols = input_sids.shape
        offsets = (
            torch.arange(num_hierarchies, device=input_sids.device) * codebook_size
        )
        num_repeats = (num_cols + num_hierarchies - 1) // num_hierarchies
        repeated_offsets = offsets.repeat(num_repeats)[:num_cols]
        result = input_sids + repeated_offsets
        if attention_mask is not None:
            result = result * attention_mask
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
        depth = prefix.shape[1]
        powers = torch.arange(depth - 1, -1, -1, device=prefix.device)
        multipliers = self.num_embeddings_per_hierarchy**powers
        return (prefix.long() * multipliers).sum(dim=1)

    def _check_valid_prefix(self, prefix: torch.Tensor) -> torch.Tensor:
        """Return a boolean mask indicating which prefixes exist in the corpus."""
        valid_keys = getattr(self, f"valid_prefix_keys_{prefix.shape[1]}")
        keys = self._encode_prefix(prefix)
        positions = torch.searchsorted(valid_keys, keys)
        in_range = positions < len(valid_keys)
        positions = positions.clamp_max(len(valid_keys) - 1)
        return in_range & (valid_keys[positions] == keys)

    def encoder_forward_pass(self, attention_mask, input_ids):
        shifted = self._add_repeating_offset_to_rows(
            input_sids=input_ids,
            codebook_size=self.num_embeddings_per_hierarchy,
            num_hierarchies=self.num_hierarchies,
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
                codebook_size=self.num_embeddings_per_hierarchy,
                num_hierarchies=self.num_hierarchies,
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
        fut_ids = batch.sem_ids_fut[:, : self.num_hierarchies]

        encoder_output, attention_mask_for_encoder = self.encoder_forward_pass(
            attention_mask=attention_mask,
            input_ids=input_ids,
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
    def generate(self, attention_mask, input_ids, temperature: float = 1.0):
        """Generate top-k semantic IDs using constrained beam search.

        Every code in the codebook is scored at every level, prefixes no
        catalogue item uses are masked to float("-inf"), and the k beams with
        the highest cumulative log-probability survive. Scoring the full
        codebook instead of a preselected subset costs nothing extra — the
        per-hierarchy head already emits all V logits — and it is what makes
        the deepest level work: only ~4% of codes continue a real 2-prefix, so
        preselecting by probability before the validity mask discards exactly
        the rare continuations the mask would have promoted.

        Returns:
            generated_ids: [B, top_k, num_hierarchies]
            log_probas:    [B, top_k]
        """
        B = input_ids.size(0)
        k = self.top_k_for_generation
        V = self.num_embeddings_per_hierarchy

        enc_out, enc_mask = self.encoder_forward_pass(
            attention_mask=attention_mask,
            input_ids=input_ids,
        )
        rep_enc = enc_out.repeat_interleave(k, dim=0)
        rep_mask = enc_mask.repeat_interleave(k, dim=0)

        generated = None  # [B, k, h] grows with each hierarchy step
        log_probas = 0
        past_kv = EncoderDecoderCache(DynamicCache(), DynamicCache())

        for h in range(self.num_hierarchies):
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

            # float32 keeps the -inf mask distinct from fp16 underflow and keeps
            # the log-probas comparable once they are summed across hierarchies.
            logits = self.decoder_mlp[h](dec_out[:, -1, :]).float()
            log_p = F.log_softmax(logits / temperature, dim=-1)
            codes = torch.arange(V, device=log_p.device)

            if generated is None:
                is_valid = self._check_valid_prefix(
                    codes.repeat(B).unsqueeze(-1)
                ).reshape(B, V)
                scores = log_p.masked_fill(~is_valid, float("-inf"))
                # Column index is the code id, so topk returns the codes directly.
                log_probas, top_idx = scores.topk(k, dim=-1)
                generated = top_idx.unsqueeze(-1)  # [B, k, 1]
                past_kv = EncoderDecoderCache(DynamicCache(), DynamicCache())
            else:
                # Row b*k*V + beam*V + code: every surviving beam times every code.
                prev = generated.reshape(-1, h).repeat_interleave(V, dim=0)
                prefix = torch.cat([prev, codes.repeat(B * k).unsqueeze(-1)], dim=1)
                is_valid = self._check_valid_prefix(prefix).reshape(B, k * V)

                scores = (
                    log_p.reshape(B, k * V) + log_probas.repeat_interleave(V, dim=1)
                ).masked_fill(~is_valid, float("-inf"))
                log_probas, top_idx = scores.topk(k, dim=-1)

                parent_beam_idx = top_idx // V
                parent_global = (
                    parent_beam_idx
                    + torch.arange(B, device=parent_beam_idx.device).unsqueeze(1) * k
                ).flatten()
                past_kv.reorder_cache(parent_global)

                parent_ids = torch.gather(
                    generated, 1, parent_beam_idx.unsqueeze(-1).expand(-1, -1, h)
                )
                new_ids = (top_idx % V).unsqueeze(-1)
                generated = torch.cat([parent_ids, new_ids], dim=-1)  # [B, k, h+1]

        return generated, log_probas

    @torch.no_grad()
    def generate_next_sem_id(
        self,
        batch: TokenizedSeqBatch,
        temperature: float = 1.0,
    ) -> GenerationOutput:
        input_ids = batch.sem_ids
        attention_mask = batch.seq_mask.long()
        generated_ids, log_probas = self.generate(
            attention_mask=attention_mask,
            input_ids=input_ids,
            temperature=temperature,
        )
        return GenerationOutput(sem_ids=generated_ids, log_probas=log_probas)
