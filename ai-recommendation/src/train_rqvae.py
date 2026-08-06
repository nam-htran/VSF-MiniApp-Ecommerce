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

from data.processed import ItemData, RecDataset
from data.utils import batch_to, cycle, next_batch
from modules.quantize import QuantizeForwardMode
from modules.rqvae import RqVae
from modules.tokenizer.semids import SemanticIdTokenizer
from modules.utils import parse_config


def semantic_id_metrics(corpus_ids: torch.Tensor, codebook_sizes):
    codebook_sizes = tuple(int(size) for size in codebook_sizes)
    n_layers = len(codebook_sizes)
    if corpus_ids.ndim != 2 or corpus_ids.shape[1] != n_layers:
        raise ValueError(f"Expected cluster SIDs with shape [N, {n_layers}]")
    raw_ids = corpus_ids
    unique_ids, counts = torch.unique(raw_ids, dim=0, return_counts=True)
    probabilities = counts.to(torch.float64) / len(raw_ids)
    colliding_counts = counts[counts > 1]

    metrics = {
        "products": len(raw_ids),
        "unique_raw_sids": len(unique_ids),
        "duplicate_excess_count": len(raw_ids) - len(unique_ids),
        "duplicate_excess_rate": (len(raw_ids) - len(unique_ids)) / len(raw_ids),
        "products_in_collision_buckets": int(colliding_counts.sum().item())
        if len(colliding_counts)
        else 0,
        "products_in_collision_buckets_rate": float(colliding_counts.sum().item())
        / len(raw_ids)
        if len(colliding_counts)
        else 0.0,
        "max_collision_bucket_size": int(counts.max().item()),
        "sid_entropy": float((-(probabilities * torch.log(probabilities))).sum().item()),
    }
    for layer, codebook_size in enumerate(codebook_sizes):
        metrics[f"codebook_usage_{layer}"] = (
            torch.unique(raw_ids[:, layer]).numel() / codebook_size
        )
    return metrics


def export_semantic_ids(
    corpus_ids: torch.Tensor,
    item_dataset: ItemData,
    output_path: Path,
    n_layers: int,
):
    if len(corpus_ids) != len(item_dataset.index_frame):
        raise ValueError("Semantic IDs and the global product index have different row counts")
    if corpus_ids.ndim != 2 or corpus_ids.shape[1] != n_layers:
        raise ValueError(f"Expected cluster SIDs with shape [N, {n_layers}]")

    output = item_dataset.index_frame[["product_index", "product_id"]].copy()
    ids = corpus_ids.cpu().numpy()
    for layer in range(n_layers):
        output[f"sid_{layer}"] = ids[:, layer].astype(np.int16)
    output.to_parquet(output_path, index=False, compression="zstd")
    return output


@gin.configurable
def train(
    iterations=50_000,
    batch_size=1_024,
    learning_rate=0.001,
    weight_decay=0.0001,
    dataset_folder="vmarket_phase2_embeddings",
    dataset=RecDataset.VMARKET,
    pretrained_rqvae_path=None,
    save_dir_root="out/rqvae/vmarket",
    use_kmeans_init=True,
    amp=True,
    wandb_logging=False,
    wandb_project="vmarket-rqvae-training",
    wandb_entity=None,
    wandb_run_name=None,
    do_eval=True,
    mixed_precision_type="fp16",
    gradient_accumulate_every=1,
    save_model_every=5_000,
    eval_every=2_500,
    commitment_weight=0.25,
    vae_n_cat_feats=0,
    vae_input_dim=256,
    vae_embed_dim=32,
    vae_hidden_dims=(256, 128, 64),
    vae_codebook_sizes=(128, 64, 32),
    vae_codebook_normalize=False,
    vae_codebook_mode=QuantizeForwardMode.STE,
    vae_sim_vq=False,
    eval_fraction=0.05,
    split_seed=2026,
    embedding_filename="global_product_embeddings.f16.npy",
    index_filename="global_embedding_index.parquet",
    semantic_ids_filename="semantic_ids.parquet",
):
    vae_codebook_sizes = tuple(int(size) for size in vae_codebook_sizes)
    if not vae_codebook_sizes or any(size <= 0 for size in vae_codebook_sizes):
        raise ValueError("vae_codebook_sizes must contain positive integers")
    vae_n_layers = len(vae_codebook_sizes)

    np.random.seed(split_seed)
    torch.manual_seed(split_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(split_seed)

    accelerator = Accelerator(
        mixed_precision=mixed_precision_type if amp else "no",
    )
    device = accelerator.device
    print(f"Device: {device}")

    dataset_kwargs = {
        "root": dataset_folder,
        "dataset": dataset,
        "eval_fraction": eval_fraction,
        "split_seed": split_seed,
        "embedding_filename": embedding_filename,
        "index_filename": index_filename,
        "expected_input_dim": vae_input_dim,
    }
    train_dataset = ItemData(
        **dataset_kwargs,
        train_test_split="train" if do_eval else "all",
    )
    train_dataloader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        pin_memory=torch.cuda.is_available(),
    )
    train_dataloader = cycle(train_dataloader)

    eval_dataset = None
    eval_dataloader = None
    if do_eval:
        eval_dataset = ItemData(**dataset_kwargs, train_test_split="eval")
        eval_dataloader = DataLoader(
            eval_dataset,
            batch_size=batch_size,
            shuffle=False,
            pin_memory=torch.cuda.is_available(),
        )

    index_dataset = ItemData(**dataset_kwargs, train_test_split="all")
    print(f"Train products: {len(train_dataset):,}")
    if eval_dataset is not None:
        print(f"Evaluation products: {len(eval_dataset):,}")
    print(f"Global products: {len(index_dataset):,}")

    model = RqVae(
        input_dim=vae_input_dim,
        embed_dim=vae_embed_dim,
        hidden_dims=list(vae_hidden_dims),
        codebook_sizes=list(vae_codebook_sizes),
        codebook_kmeans_init=use_kmeans_init and pretrained_rqvae_path is None,
        codebook_normalize=vae_codebook_normalize,
        codebook_sim_vq=vae_sim_vq,
        codebook_mode=vae_codebook_mode,
        n_cat_features=vae_n_cat_feats,
        commitment_weight=commitment_weight,
    )
    optimizer = AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)

    start_iter = 0
    if pretrained_rqvae_path is not None:
        state = torch.load(pretrained_rqvae_path, map_location=device, weights_only=False)
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        start_iter = state["iter"] + 1

    if wandb_logging and accelerator.is_main_process:
        wandb.login()
        wandb.init(
            project=wandb_project,
            entity=wandb_entity,
            name=wandb_run_name,
            config={
                "iterations": iterations,
                "batch_size": batch_size,
                "learning_rate": learning_rate,
                "weight_decay": weight_decay,
                "input_dim": vae_input_dim,
                "hidden_dims": list(vae_hidden_dims),
                "embed_dim": vae_embed_dim,
                "codebook_sizes": list(vae_codebook_sizes),
                "n_layers": vae_n_layers,
                "commitment_weight": commitment_weight,
                "eval_fraction": eval_fraction,
                "split_seed": split_seed,
            },
        )

    model, optimizer = accelerator.prepare(model, optimizer)

    if start_iter == 0 and use_kmeans_init and pretrained_rqvae_path is None:
        generator = torch.Generator().manual_seed(split_seed)
        sample_size = min(20_000, len(train_dataset))
        sample_indices = torch.randperm(len(train_dataset), generator=generator)[:sample_size]
        kmeans_batch = batch_to(train_dataset[sample_indices], device)
        with accelerator.autocast():
            accelerator.unwrap_model(model).initialize_codebooks(kmeans_batch.x)
        print(f"K-means initialized from {sample_size:,} randomly sampled products.")

    output_dir = Path(save_dir_root).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    end_iter = start_iter + iterations
    losses = [[], [], []]

    with tqdm(
        initial=start_iter,
        total=end_iter,
        disable=not accelerator.is_main_process,
    ) as progress:
        for iteration in range(start_iter, end_iter):
            model.train()
            optimizer.zero_grad()
            total_loss = 0.0

            for _ in range(gradient_accumulate_every):
                data = next_batch(train_dataloader, device)
                with accelerator.autocast():
                    model_output = model(data, gumbel_t=0.2)
                    loss = model_output.loss / gradient_accumulate_every
                total_loss = total_loss + loss

            accelerator.backward(total_loss)
            optimizer.step()

            losses[0].append(total_loss.detach().cpu().item())
            losses[1].append(model_output.reconstruction_loss.detach().cpu().item())
            losses[2].append(model_output.rqvae_loss.detach().cpu().item())
            losses = [values[-1_000:] for values in losses]
            progress.set_description(
                f"loss: {np.mean(losses[0]):.4f}, "
                f"rl: {np.mean(losses[1]):.4f}, "
                f"vl: {np.mean(losses[2]):.4f}"
            )

            step = iteration + 1
            log_values = {
                "learning_rate": optimizer.param_groups[0]["lr"],
                "total_loss": losses[0][-1],
                "reconstruction_loss": losses[1][-1],
                "rqvae_loss": losses[2][-1],
                "p_unique_ids_batch": model_output.p_unique_ids.detach().cpu().item(),
            }

            if do_eval and (step % eval_every == 0 or step == end_iter):
                model.eval()
                eval_losses = [[], [], []]
                with torch.no_grad():
                    for batch in eval_dataloader:
                        eval_output = model(batch_to(batch, device), gumbel_t=0.2)
                        eval_losses[0].append(eval_output.loss.cpu().item())
                        eval_losses[1].append(eval_output.reconstruction_loss.cpu().item())
                        eval_losses[2].append(eval_output.rqvae_loss.cpu().item())
                eval_means = np.asarray(eval_losses).mean(axis=1)
                log_values.update(
                    eval_total_loss=float(eval_means[0]),
                    eval_reconstruction_loss=float(eval_means[1]),
                    eval_rqvae_loss=float(eval_means[2]),
                )

            if accelerator.is_main_process and (
                step % save_model_every == 0 or step == end_iter
            ):
                unwrapped_model = accelerator.unwrap_model(model)
                state = {
                    "iter": iteration,
                    "model": unwrapped_model.state_dict(),
                    "optimizer": optimizer.state_dict(),
                    "model_config": {
                        "input_dim": vae_input_dim,
                        "embed_dim": vae_embed_dim,
                        "hidden_dims": list(vae_hidden_dims),
                        "codebook_sizes": list(vae_codebook_sizes),
                        "codebook_normalize": vae_codebook_normalize,
                        "codebook_sim_vq": vae_sim_vq,
                        "codebook_mode": vae_codebook_mode.name,
                        "n_layers": vae_n_layers,
                        "n_cat_features": vae_n_cat_feats,
                        "commitment_weight": commitment_weight,
                    },
                }
                torch.save(state, output_dir / f"checkpoint_{iteration}.pt")

            if wandb_logging and accelerator.is_main_process:
                wandb.log(log_values, step=step)
            progress.update(1)

    accelerator.wait_for_everyone()
    if accelerator.is_main_process:
        unwrapped_model = accelerator.unwrap_model(model)
        tokenizer = SemanticIdTokenizer(
            input_dim=vae_input_dim,
            hidden_dims=list(vae_hidden_dims),
            output_dim=vae_embed_dim,
            codebook_sizes=list(vae_codebook_sizes),
            n_cat_feats=vae_n_cat_feats,
            rqvae_codebook_normalize=vae_codebook_normalize,
            rqvae_sim_vq=vae_sim_vq,
        )
        tokenizer.rq_vae = unwrapped_model
        tokenizer.rq_vae.eval()
        corpus_ids = tokenizer.precompute_corpus_ids(index_dataset)

        metrics = semantic_id_metrics(corpus_ids, vae_codebook_sizes)
        semantic_ids_path = output_dir / semantic_ids_filename
        export_semantic_ids(corpus_ids, index_dataset, semantic_ids_path, vae_n_layers)
        (output_dir / "semantic_id_metrics.json").write_text(
            json.dumps(metrics, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(metrics, indent=2))
        print("Semantic IDs written:", semantic_ids_path)
        if wandb_logging:
            wandb.log(metrics, step=end_iter)

    accelerator.wait_for_everyone()
    if wandb_logging and accelerator.is_main_process:
        wandb.finish()


if __name__ == "__main__":
    parse_config()
    train()
