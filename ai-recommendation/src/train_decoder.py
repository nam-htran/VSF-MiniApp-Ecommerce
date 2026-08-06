import json
from pathlib import Path

import gin
import numpy as np
import pandas as pd
import torch
import wandb
from accelerate import Accelerator
from torch.optim import AdamW
from torch.utils.data import DataLoader
from tqdm import tqdm

from data.processed import SeqData
from data.utils import batch_to, cycle
from data.vmarket import prepare_vmarket_session_cache
from evaluate.metrics import TopKAccumulator
from modules.model import EncoderDecoderRetrievalModel
from modules.scheduler.inv_sqrt import InverseSquareRootScheduler
from modules.tokenizer.semids import CachedSemanticIdTokenizer
from modules.utils import parse_config


def load_corpus_sids(semantic_ids_path: str, codebook_sizes) -> torch.Tensor:
    codebook_sizes = tuple(int(size) for size in codebook_sizes)
    sid_columns = [f"sid_{layer}" for layer in range(len(codebook_sizes))]
    frame = pd.read_parquet(
        semantic_ids_path,
        columns=["product_index", "product_id", *sid_columns],
    )
    expected_indices = np.arange(len(frame), dtype=frame["product_index"].dtype)
    if not np.array_equal(frame["product_index"].to_numpy(), expected_indices):
        raise ValueError("semantic_ids product_index must be contiguous and row-aligned")
    if frame["product_id"].isna().any() or not frame["product_id"].is_unique:
        raise ValueError("semantic_ids must contain unique, non-null product IDs")

    sid_values = frame[sid_columns].to_numpy(dtype=np.int64, copy=True)
    for layer, codebook_size in enumerate(codebook_sizes):
        minimum = int(sid_values[:, layer].min())
        maximum = int(sid_values[:, layer].max())
        if minimum < 0 or maximum >= codebook_size:
            raise ValueError(
                f"sid_{layer} outside [0, {codebook_size - 1}]: {minimum}..{maximum}"
            )
    return torch.from_numpy(sid_values)


@gin.configurable
def train(
    iterations=100_000,
    batch_size=256,
    learning_rate=0.001,
    weight_decay=0.01,
    session_root="preprocessed",
    semantic_ids_path="vmarket_rqvae/semantic_ids.parquet",
    session_cache_root="vmarket_transformer_session_cache",
    save_dir_root="out/transformer/vmarket",
    codebook_sizes=(128, 64, 32),
    max_sequence_length=20,
    force_session_cache=False,
    num_workers=2,
    amp=True,
    mixed_precision_type="fp16",
    gradient_accumulate_every=1,
    save_model_every=10_000,
    eval_every=2_000,
    full_eval_every=10_000,
    max_eval_batches=200,
    warmup_steps=10_000,
    pretrained_decoder_path=None,
    wandb_logging=False,
    max_grad_norm=1.0,
    t5_d_model=128,
    t5_num_heads=4,
    t5_d_ff=512,
    t5_num_layers=4,
    top_k_for_generation=10,
    should_add_sep_token=True,
    num_user_bins=None,
    top_k_eval_list=(1, 5, 10),
    seed=2026,
):
    codebook_sizes = tuple(int(size) for size in codebook_sizes)
    if not codebook_sizes or any(size <= 0 for size in codebook_sizes):
        raise ValueError("codebook_sizes must contain positive integers")
    if gradient_accumulate_every <= 0:
        raise ValueError("gradient_accumulate_every must be positive")
    for name, value in {
        "iterations": iterations,
        "batch_size": batch_size,
        "save_model_every": save_model_every,
        "eval_every": eval_every,
        "full_eval_every": full_eval_every,
    }.items():
        if value <= 0:
            raise ValueError(f"{name} must be positive")

    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    semantic_ids_path = Path(semantic_ids_path).expanduser().resolve()
    session_root = Path(session_root).expanduser().resolve()
    session_cache_root = Path(session_cache_root).expanduser().resolve()
    output_dir = Path(save_dir_root).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not semantic_ids_path.is_file():
        raise FileNotFoundError(semantic_ids_path)

    cache_manifest_path = prepare_vmarket_session_cache(
        session_root=session_root,
        catalog_index_path=semantic_ids_path,
        cache_root=session_cache_root,
        max_sequence_length=max_sequence_length,
        force=force_session_cache,
    )
    train_dataset = SeqData(cache_root=session_cache_root, split="train")
    validation_dataset = SeqData(cache_root=session_cache_root, split="validation")
    print(f"Train sessions: {len(train_dataset):,}")
    print(f"Validation sessions: {len(validation_dataset):,}")
    print("Session cache manifest:", cache_manifest_path)

    loader_kwargs = {
        "batch_size": batch_size,
        "num_workers": num_workers,
        "pin_memory": torch.cuda.is_available(),
        "persistent_workers": num_workers > 0,
    }
    train_dataloader = DataLoader(train_dataset, shuffle=True, **loader_kwargs)
    validation_dataloader = DataLoader(
        validation_dataset,
        shuffle=False,
        **loader_kwargs,
    )

    corpus_ids = load_corpus_sids(semantic_ids_path, codebook_sizes)
    occupied_cluster_sids = torch.unique(corpus_ids, dim=0)
    print(f"Products in SID table: {len(corpus_ids):,}")
    print(f"Occupied cluster SIDs: {len(occupied_cluster_sids):,}")

    model = EncoderDecoderRetrievalModel(
        codebooks=occupied_cluster_sids,
        codebook_sizes=codebook_sizes,
        t5_d_model=t5_d_model,
        t5_num_heads=t5_num_heads,
        t5_d_ff=t5_d_ff,
        t5_num_layers=t5_num_layers,
        top_k_for_generation=top_k_for_generation,
        should_add_sep_token=should_add_sep_token,
        num_user_bins=num_user_bins,
    )
    optimizer = AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    scheduler = InverseSquareRootScheduler(optimizer, warmup_steps=warmup_steps)

    start_iteration = 0
    if pretrained_decoder_path is not None:
        checkpoint = torch.load(
            pretrained_decoder_path,
            map_location="cpu",
            weights_only=False,
        )
        model.load_state_dict(checkpoint["model"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        scheduler.load_state_dict(checkpoint["scheduler"])
        start_iteration = int(checkpoint["iter"]) + 1
        print(f"Resuming from iteration {start_iteration:,}")

    accelerator = Accelerator(
        mixed_precision=mixed_precision_type if amp else "no",
    )
    device = accelerator.device
    model, optimizer, scheduler, train_dataloader, validation_dataloader = (
        accelerator.prepare(
            model,
            optimizer,
            scheduler,
            train_dataloader,
            validation_dataloader,
        )
    )
    tokenizer = CachedSemanticIdTokenizer(corpus_ids).to(device)
    train_iterator = cycle(train_dataloader)
    metrics_accumulator = TopKAccumulator(ks=list(top_k_eval_list))

    if wandb_logging and accelerator.is_main_process:
        wandb.login()
        wandb.init(
            project="vmarket-transformer-training",
            config={
                "iterations": iterations,
                "batch_size": batch_size,
                "learning_rate": learning_rate,
                "codebook_sizes": list(codebook_sizes),
                "max_sequence_length": max_sequence_length,
                "occupied_cluster_sids": len(occupied_cluster_sids),
            },
        )

    def validation_loss():
        model.eval()
        losses = []
        with torch.no_grad():
            for batch_index, batch in enumerate(validation_dataloader):
                if max_eval_batches is not None and batch_index >= max_eval_batches:
                    break
                tokenized = tokenizer(batch_to(batch, device))
                losses.append(model(tokenized).loss.detach().float().item())
        return float(np.mean(losses))

    def validation_sid_metrics():
        model.eval()
        metrics_accumulator.reset()
        with torch.no_grad():
            for batch_index, batch in enumerate(validation_dataloader):
                if max_eval_batches is not None and batch_index >= max_eval_batches:
                    break
                tokenized = tokenizer(batch_to(batch, device))
                generated = model.generate_next_sem_id(tokenized)
                metrics_accumulator.accumulate(
                    actual=tokenized.sem_ids_fut,
                    top_k=generated.sem_ids,
                )
        return metrics_accumulator.reduce()

    end_iteration = start_iteration + iterations
    latest_metrics = {}
    with tqdm(
        range(start_iteration, end_iteration),
        disable=not accelerator.is_main_process,
    ) as progress:
        for iteration in progress:
            model.train()
            optimizer.zero_grad()
            total_loss = 0.0
            level_losses = None

            for _ in range(gradient_accumulate_every):
                batch = batch_to(next(train_iterator), device)
                tokenized = tokenizer(batch)
                with accelerator.autocast():
                    output = model(tokenized)
                    loss = output.loss / gradient_accumulate_every
                accelerator.backward(loss)
                total_loss += loss.detach().float().item()
                level_losses = output.loss_d.detach().float().cpu().tolist()

            if max_grad_norm is not None:
                accelerator.clip_grad_norm_(model.parameters(), max_grad_norm)
            optimizer.step()
            scheduler.step()
            progress.set_description(f"loss: {total_loss:.4f}")

            completed_iteration = iteration + 1
            log_values = {
                "train_loss": total_loss,
                "learning_rate": optimizer.param_groups[0]["lr"],
                **{
                    f"train_loss_sid_{layer}": value
                    for layer, value in enumerate(level_losses)
                },
            }

            if completed_iteration % eval_every == 0:
                log_values["validation_loss"] = validation_loss()

            if completed_iteration % full_eval_every == 0:
                latest_metrics = validation_sid_metrics()
                log_values.update(latest_metrics)
                if accelerator.is_main_process:
                    print(json.dumps(latest_metrics, indent=2))

            if wandb_logging and accelerator.is_main_process:
                wandb.log(log_values, step=completed_iteration)

            should_save = (
                completed_iteration % save_model_every == 0
                or completed_iteration == end_iteration
            )
            if should_save:
                accelerator.wait_for_everyone()
                if accelerator.is_main_process:
                    unwrapped_model = accelerator.unwrap_model(model)
                    state = {
                        "iter": iteration,
                        "model": unwrapped_model.state_dict(),
                        "optimizer": optimizer.state_dict(),
                        "scheduler": scheduler.state_dict(),
                        "model_config": {
                            "codebook_sizes": list(codebook_sizes),
                            "t5_d_model": t5_d_model,
                            "t5_num_heads": t5_num_heads,
                            "t5_d_ff": t5_d_ff,
                            "t5_num_layers": t5_num_layers,
                            "top_k_for_generation": top_k_for_generation,
                            "should_add_sep_token": should_add_sep_token,
                            "num_user_bins": num_user_bins,
                        },
                    }
                    torch.save(
                        state,
                        output_dir / f"checkpoint_{completed_iteration}.pt",
                    )

    if not latest_metrics:
        latest_metrics = validation_sid_metrics()
    if accelerator.is_main_process:
        (output_dir / "transformer_metrics.json").write_text(
            json.dumps(latest_metrics, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(latest_metrics, indent=2))
        print("Transformer outputs written to:", output_dir)
        if wandb_logging:
            wandb.finish()


if __name__ == "__main__":
    parse_config()
    train()
