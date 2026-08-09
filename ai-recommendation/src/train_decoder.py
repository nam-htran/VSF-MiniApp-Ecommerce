import os

import gin
import numpy as np
import pandas as pd
import torch
import wandb

from accelerate import Accelerator
from datetime import datetime
from datetime import timezone
from data.processed import RecDataset
from data.processed import SeqData
from data.utils import batch_to
from data.utils import cycle
from data.utils import next_batch
from evaluate.metrics import TopKAccumulator
from modules.model import EncoderDecoderRetrievalModel
from modules.tokenizer.semids import PrecomputedSemanticIdTokenizer
from modules.utils import parse_config
from torch.optim import AdamW
from torch.utils.data import DataLoader
from torch.utils.data import Subset
from tqdm import tqdm
from transformers import get_inverse_sqrt_schedule


@gin.configurable
def train(
    iterations=500000,
    batch_size=64,
    learning_rate=0.001,
    warmup_steps=10000,
    weight_decay=0.01,
    semantic_ids_path="output/rq-vae/semantic_ids.parquet",
    session_folder=None,
    save_dir_root="out/",
    dataset=RecDataset.VMARKET,
    pretrained_decoder_path=None,
    split_batches=True,
    amp=False,
    wandb_logging=False,
    wandb_project="gen-retrieval-decoder-training",
    wandb_run_name_prefix="transformer",
    mixed_precision_type="fp16",
    gradient_accumulate_every=1,
    save_model_every=1000000,
    eval_every=20000,
    eval_subset_size=20000,
    eval_subset_seed=2026,
    vae_codebook_sizes=[128, 64, 32],
    max_grad_norm=None,
    t5_d_model=128,
    t5_num_heads=6,
    t5_d_ff=1024,
    t5_num_layers=4,
    top_k_for_generation=10,
    should_add_sep_token=True,
    top_k_eval_list=[1, 5, 10],
):
    vae_n_layers = len(vae_codebook_sizes)
    if wandb_logging:
        params = locals()

    accelerator = Accelerator(
        split_batches=split_batches,
        mixed_precision=mixed_precision_type if amp else "no",
    )
    device = accelerator.device

    if wandb_logging and accelerator.is_main_process:
        wandb.login()
        run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        wandb.init(
            project=wandb_project,
            name=f"{wandb_run_name_prefix}-{run_timestamp}",
            config=params,
        )

    semantic_ids = pd.read_parquet(semantic_ids_path)
    sid_columns = [f"sid_{index}" for index in range(vae_n_layers)]
    if not np.array_equal(
        semantic_ids["product_index"].to_numpy(),
        np.arange(len(semantic_ids)),
    ):
        raise ValueError("product_index must match the Semantic ID row order")
    codebooks = torch.from_numpy(
        semantic_ids[sid_columns].to_numpy(dtype=np.int16, copy=True)
    )
    for layer, size in enumerate(vae_codebook_sizes):
        if codebooks[:, layer].min() < 0 or codebooks[:, layer].max() >= size:
            raise ValueError(
                f"sid_{layer} contains values outside its codebook range [0, {size})"
            )
    del semantic_ids

    train_dataset = SeqData(
        root=session_folder,
        index_path=semantic_ids_path,
        session_root=session_folder,
        dataset=dataset,
        is_train=True,
    )
    eval_dataset = SeqData(
        root=session_folder,
        index_path=semantic_ids_path,
        session_root=session_folder,
        dataset=dataset,
        is_train=False,
    )

    train_dataloader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    train_dataloader = cycle(train_dataloader)
    eval_dataloader = DataLoader(eval_dataset, batch_size=batch_size, shuffle=False)

    # Beam search across all 360k validation sessions takes 42 minutes a pass.
    # Ten of those was 6.32 of the last 200k run's 7.06 hours — 89% of the wall
    # clock — against 44 minutes for the 200k training steps themselves. The
    # periodic evals exist to show the shape of a curve, and 20k sessions puts
    # the standard error on a rate near 0.49 at 0.0035, an order below the
    # differences those curves get read for. The final eval still sweeps the
    # whole set, so the number that gets reported is measured as it always was.
    if eval_subset_size is not None and eval_subset_size < len(eval_dataset):
        subset_rows = np.random.default_rng(eval_subset_seed).choice(
            len(eval_dataset), size=eval_subset_size, replace=False
        )
        quick_eval_dataloader = DataLoader(
            Subset(eval_dataset, subset_rows.tolist()),
            batch_size=batch_size,
            shuffle=False,
        )
    else:
        quick_eval_dataloader = eval_dataloader

    train_dataloader, eval_dataloader, quick_eval_dataloader = accelerator.prepare(
        train_dataloader, eval_dataloader, quick_eval_dataloader
    )

    tokenizer = PrecomputedSemanticIdTokenizer(codebooks)
    tokenizer = accelerator.prepare(tokenizer)

    model = EncoderDecoderRetrievalModel(
        codebooks=codebooks,
        codebook_sizes=vae_codebook_sizes,
        t5_d_model=t5_d_model,
        t5_num_heads=t5_num_heads,
        t5_d_ff=t5_d_ff,
        t5_num_layers=t5_num_layers,
        top_k_for_generation=top_k_for_generation,
        should_add_sep_token=should_add_sep_token,
    )
    model = torch.compile(model)

    optimizer = AdamW(
        params=model.parameters(), lr=learning_rate, weight_decay=weight_decay
    )
    lr_scheduler = get_inverse_sqrt_schedule(
        optimizer,
        num_warmup_steps=warmup_steps,
    )

    start_iter = 0
    best_ndcg = float("-inf")
    if pretrained_decoder_path is not None:
        checkpoint = torch.load(
            pretrained_decoder_path, map_location=device, weights_only=False
        )
        model.load_state_dict(checkpoint["model"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        if "scheduler" in checkpoint:
            lr_scheduler.load_state_dict(checkpoint["scheduler"])
        start_iter = checkpoint["iter"] + 1
        best_ndcg = checkpoint.get("best_ndcg", best_ndcg)

    model, optimizer, lr_scheduler = accelerator.prepare(model, optimizer, lr_scheduler)

    metrics_accumulator = TopKAccumulator(ks=top_k_eval_list)
    num_params = sum(p.numel() for p in model.parameters())
    print(f"Device: {device}, Num Parameters: {num_params}")

    with tqdm(
        initial=start_iter,
        total=start_iter + iterations,
        disable=not accelerator.is_main_process,
    ) as pbar:
        for iter in range(iterations):
            model.train()
            total_loss = 0.0
            is_best_checkpoint = False
            optimizer.zero_grad()
            train_layer_loss = torch.zeros(vae_n_layers)

            for _ in range(gradient_accumulate_every):
                data = next_batch(train_dataloader, device)
                tokenized_data = tokenizer(data)

                with accelerator.autocast():
                    model_output = model(tokenized_data)
                    loss = model_output.loss / gradient_accumulate_every

                total_loss += loss.detach().item()
                train_layer_loss += model_output.loss_d.cpu()

                accelerator.backward(loss)

            assert model.item_sid_embedding_table.weight.grad is not None
            pbar.set_description(f"loss: {total_loss:.4f}")

            accelerator.wait_for_everyone()

            if max_grad_norm is not None:
                accelerator.clip_grad_norm_(model.parameters(), max_grad_norm)
            optimizer.step()
            lr_scheduler.step()

            accelerator.wait_for_everyone()

            step_metrics = {
                f"loss_sid_{layer}": (
                    train_layer_loss[layer].item() / gradient_accumulate_every
                )
                for layer in range(vae_n_layers)
            }

            if (iter + 1) % eval_every == 0 or iter + 1 == iterations:
                model.eval()
                eval_loss_sum = 0.0
                eval_layer_loss_sum = torch.zeros(vae_n_layers)
                eval_examples = 0
                is_final_eval = iter + 1 == iterations
                eval_loader = eval_dataloader if is_final_eval else quick_eval_dataloader
                with tqdm(
                    eval_loader,
                    desc=f"Eval {iter + 1}" + ("" if is_final_eval else " [subset]"),
                    disable=not accelerator.is_main_process,
                ) as pbar_eval:
                    for batch in pbar_eval:
                        data = batch_to(batch, device)
                        tokenized_data = tokenizer(data)

                        with torch.no_grad():
                            eval_output = model(tokenized_data)
                            generated = model.generate_next_sem_id(tokenized_data)

                        eval_batch_size = tokenized_data.sem_ids_fut.shape[0]
                        eval_loss_sum += eval_output.loss.item() * eval_batch_size
                        eval_layer_loss_sum += (
                            eval_output.loss_d.cpu() * eval_batch_size
                        )
                        eval_examples += eval_batch_size

                        actual = tokenized_data.sem_ids_fut[:, :vae_n_layers]
                        metrics_accumulator.accumulate(
                            actual=actual, top_k=generated.sem_ids
                        )

                step_metrics["eval_loss"] = eval_loss_sum / eval_examples
                for layer in range(vae_n_layers):
                    step_metrics[f"eval_loss_sid_{layer}"] = (
                        eval_layer_loss_sum[layer].item() / eval_examples
                    )

                eval_metrics = metrics_accumulator.reduce()
                print(eval_metrics)
                step_metrics.update(eval_metrics)
                metrics_accumulator.reset()

                if eval_metrics["ndcg"] > best_ndcg:
                    best_ndcg = eval_metrics["ndcg"]
                    is_best_checkpoint = True
                step_metrics["best_ndcg"] = best_ndcg

            if accelerator.is_main_process:
                should_save = (
                    (iter + 1) % save_model_every == 0
                    or iter + 1 == iterations
                    or is_best_checkpoint
                )
                if should_save:
                    state = {
                        "iter": iter,
                        "model": model.state_dict(),
                        "optimizer": optimizer.state_dict(),
                        "scheduler": lr_scheduler.state_dict(),
                        "best_ndcg": best_ndcg,
                    }

                    if not os.path.exists(save_dir_root):
                        os.makedirs(save_dir_root)

                    if (iter + 1) % save_model_every == 0 or iter + 1 == iterations:
                        torch.save(state, save_dir_root + f"checkpoint_{iter}.pt")
                    if is_best_checkpoint:
                        torch.save(state, save_dir_root + "best_checkpoint.pt")

                if wandb_logging:
                    wandb.log(
                        {
                            "learning_rate": optimizer.param_groups[0]["lr"],
                            "total_loss": total_loss,
                            **step_metrics,
                        },
                        step=iter + 1,
                    )

            pbar.update(1)

    if wandb_logging:
        wandb.finish()


if __name__ == "__main__":
    parse_config()
    train()
