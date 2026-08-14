import pandas as pd
import torch

from modules.distillation import QwenDistillationModel
from sid.contract import add_sid_tokens
from sid.contract import validate_sid_table
from transformers import AutoModelForCausalLM
from transformers import AutoTokenizer


MODEL_NAME = "Qwen/Qwen3-0.6B-Base"
CODEBOOK_SIZES = (128, 64, 32)


def build_model(
    semantic_ids_path,
    model_name=MODEL_NAME,
    kd_weight=1.0,
    temperature=1.0,
    dtype=torch.float16,
):
    semantic_ids = pd.read_parquet(semantic_ids_path)
    suffix_size = validate_sid_table(semantic_ids, CODEBOOK_SIZES)

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    backbone = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=dtype,
    )
    sid_token_ids = add_sid_tokens(
        tokenizer,
        backbone,
        codebook_sizes=CODEBOOK_SIZES,
        suffix_size=suffix_size,
    )
    backbone.config.use_cache = False
    backbone.gradient_checkpointing_enable()

    model = QwenDistillationModel(
        backbone=backbone,
        sid_token_ids=sid_token_ids,
        kd_weight=kd_weight,
        temperature=temperature,
    )
    return model, tokenizer


def train_step(model, batch, optimizer, max_grad_norm=1.0):
    """Run one Phase 3 optimizer step on an already-tokenized batch."""
    model.train()
    optimizer.zero_grad(set_to_none=True)
    output = model(**batch)
    output.loss.backward()
    if max_grad_norm is not None:
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
    optimizer.step()
    return {
        "loss": output.loss.detach().item(),
        "ce_loss": output.ce_loss.detach().item(),
        "kd_loss": output.kd_loss.detach().item(),
    }
