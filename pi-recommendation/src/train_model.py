import json
import os
from collections import defaultdict
from datetime import datetime
from datetime import timezone

import gin
import pandas as pd
import polars as pl
import torch

from modules.distillation import QwenDistillationModel
from modules.utils import parse_config
from sid.contract import SID_COLUMNS
from sid.contract import add_sid_tokens
from sid.contract import validate_sid_table
from torch.optim import AdamW
from torch.utils.data import DataLoader
from tqdm import tqdm
from transformers import AutoModelForCausalLM
from transformers import AutoTokenizer


@gin.configurable
def train(
    iterations=2000,
    batch_size=1,
    gradient_accumulate_every=16,
    learning_rate=2e-5,
    weight_decay=0.01,
    preprocessed_folder="preprocessed",
    semantic_ids_path="output/rq-vae/semantic_ids.parquet",
    save_dir_root="output/model",
    model_name=gin.REQUIRED,
    codebook_sizes=gin.REQUIRED,
    request_keys=gin.REQUIRED,
    kd_weight=1.0,
    temperature=1.0,
    student_max_length=256,
    teacher_max_length=512,
    train_request_limit=10000,
    validation_request_limit=1000,
    recent_item_limit=20,
    history_request_limit=5,
    eval_every=500,
    save_model_every=2000,
    max_grad_norm=1.0,
    random_seed=2026,
    amp=True,
    wandb_logging=True,
    wandb_project="kuaisearch-privileged-distillation",
    wandb_run_name_prefix="qwen3-0.6b",
):
    from accelerate import Accelerator
    from accelerate.utils import set_seed

    if wandb_logging:
        import wandb

    set_seed(random_seed)
    accelerator = Accelerator(mixed_precision="fp16" if amp else "no")
    device = accelerator.device
    print(f"Device: {device}")

    ranking_path = os.path.join(preprocessed_folder, "ranking.parquet")
    requests_by_split = {}
    for split, limit in (
        ("train", train_request_limit),
        ("validation", validation_request_limit),
    ):
        requests = (
            pl.scan_parquet(ranking_path)
            .filter((pl.col("data_split") == split) & (pl.col("is_clicked") == 1))
            .group_by(request_keys)
            .agg(
                pl.col("target_item_id").unique().alias("clicked_target_ids"),
                pl.col("recently_clicked_item_ids").first(),
                pl.col("recently_purchased_item_ids").first(),
                pl.col("search_entrance").first(),
                pl.col("user_statistical_features").first(),
            )
            .sort(["user_id", "session_id", "time_index"])
        )
        if limit is not None:
            requests = requests.head(limit)
        requests_by_split[split] = requests.collect(
            engine="streaming"
        ).to_pandas()

    semantic_ids = pd.read_parquet(semantic_ids_path)
    suffix_size = validate_sid_table(semantic_ids, codebook_sizes)
    sid_by_product = {
        int(row.product_id): tuple(
            int(getattr(row, column)) for column in SID_COLUMNS
        )
        for row in semantic_ids.itertuples(index=False)
    }

    samples_by_split = {}
    for split, requests in requests_by_split.items():
        histories = defaultdict(list)
        samples = []
        for row in requests.itertuples(index=False):
            query = str(row.query).strip()
            clicked_ids = (
                []
                if row.clicked_target_ids is None
                else list(row.clicked_target_ids)
            )
            recent_clicked_ids = (
                []
                if row.recently_clicked_item_ids is None
                else list(row.recently_clicked_item_ids)
            )
            recent_purchased_ids = (
                []
                if row.recently_purchased_item_ids is None
                else list(row.recently_purchased_item_ids)
            )
            recent_clicks = " ".join(
                f"<a{sid[0]}><b{sid[1]}><c{sid[2]}><u{sid[3]}>"
                for product_id in recent_clicked_ids[-recent_item_limit:]
                if (sid := sid_by_product.get(int(product_id))) is not None
            )
            recent_purchases = " ".join(
                f"<a{sid[0]}><b{sid[1]}><c{sid[2]}><u{sid[3]}>"
                for product_id in recent_purchased_ids[-recent_item_limit:]
                if (sid := sid_by_product.get(int(product_id))) is not None
            )
            history_key = (row.user_id, row.session_id)
            history_text = "\n".join(
                f"{index + 1}. Query: {past_query}\n   Click: {past_clicks}"
                for index, (past_query, past_clicks) in enumerate(
                    histories[history_key][-history_request_limit:]
                )
            )
            privileged_information = (
                "\n<PI>"
                f"\nSearch_Entrance: {row.search_entrance}"
                f"\nUser_Stats: {row.user_statistical_features}"
                f"\nRecent_Clicks: {recent_clicks}"
                f"\nRecent_Purchases: {recent_purchases}"
            )

            request_clicks = []
            for product_id in clicked_ids:
                target_sid = sid_by_product.get(int(product_id))
                if target_sid is None:
                    continue
                request_clicks.append(
                    f"<a{target_sid[0]}><b{target_sid[1]}>"
                    f"<c{target_sid[2]}><u{target_sid[3]}>"
                )
                prompts = []
                if query:
                    prompts.append(f"<SEARCH>\nQuery: {query}\n<ANS>")
                if recent_clicks:
                    prompts.append(
                        f"<REC_CLICK>\nRecent_Clicks: {recent_clicks}\n<ANS>"
                    )
                if history_text:
                    prompts.append(f"<REC_HISTORY>\n{history_text}\n<ANS>")
                samples.extend(
                    {
                        "student_prompt": prompt,
                        "teacher_prompt": prompt + privileged_information,
                        "target_codes": target_sid,
                    }
                    for prompt in prompts
                )

            if query and request_clicks:
                histories[history_key].append((query, " ".join(request_clicks)))
        samples_by_split[split] = samples

    train_samples = samples_by_split["train"]
    validation_samples = samples_by_split["validation"]
    if not train_samples or not validation_samples:
        raise ValueError("Phase 3 sample construction returned an empty split")
    print(f"Train samples: {len(train_samples):,}")
    print(f"Validation samples: {len(validation_samples):,}")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    backbone = AutoModelForCausalLM.from_pretrained(
        model_name,
        dtype=torch.float32,
    )
    sid_token_ids = add_sid_tokens(
        tokenizer,
        backbone,
        codebook_sizes=codebook_sizes,
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

    def collate(samples):
        batch = {}
        for view, max_length in (
            ("student", student_max_length),
            ("teacher", teacher_max_length),
        ):
            sequences = []
            labels = []
            for sample in samples:
                prompt_ids = tokenizer.encode(
                    sample[f"{view}_prompt"], add_special_tokens=False
                )
                target_tokens = [
                    f"<{name}{code}>"
                    for name, code in zip(("a", "b", "c", "u"), sample["target_codes"])
                ]
                target_ids = tokenizer.convert_tokens_to_ids(target_tokens)
                if len(prompt_ids) + 4 > max_length:
                    raise ValueError(f"{view} prompt exceeds {max_length} tokens")
                sequences.append(prompt_ids + target_ids)
                labels.append([-100] * len(prompt_ids) + target_ids)

            width = max(len(sequence) for sequence in sequences)
            input_ids = torch.full(
                (len(samples), width), tokenizer.pad_token_id, dtype=torch.long
            )
            attention_mask = torch.zeros_like(input_ids)
            output_labels = torch.full_like(input_ids, -100)
            for row, (sequence, row_labels) in enumerate(zip(sequences, labels)):
                length = len(sequence)
                input_ids[row, :length] = torch.tensor(sequence)
                attention_mask[row, :length] = 1
                output_labels[row, :length] = torch.tensor(row_labels)
            batch[f"{view}_input_ids"] = input_ids
            batch[f"{view}_attention_mask"] = attention_mask
            batch[f"{view}_labels"] = output_labels

        batch["target_codes"] = torch.tensor(
            [sample["target_codes"] for sample in samples]
        )
        return batch

    train_loader = DataLoader(
        train_samples,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=collate,
    )
    validation_loader = DataLoader(
        validation_samples,
        batch_size=batch_size,
        shuffle=False,
        collate_fn=collate,
    )
    train_iterator = iter(train_loader)

    optimizer = AdamW(
        model.parameters(), lr=learning_rate, weight_decay=weight_decay
    )
    model, optimizer, validation_loader = accelerator.prepare(
        model, optimizer, validation_loader
    )

    if wandb_logging and accelerator.is_main_process:
        run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        wandb.login()
        wandb.init(
            project=wandb_project,
            name=f"{wandb_run_name_prefix}-{run_timestamp}",
            config={
                "model_name": model_name,
                "codebook_sizes": list(codebook_sizes),
                "iterations": iterations,
                "batch_size": batch_size,
                "gradient_accumulate_every": gradient_accumulate_every,
                "learning_rate": learning_rate,
                "weight_decay": weight_decay,
                "kd_weight": kd_weight,
                "temperature": temperature,
                "student_max_length": student_max_length,
                "teacher_max_length": teacher_max_length,
                "train_samples": len(train_samples),
                "validation_samples": len(validation_samples),
            },
        )

    save_dir_root = os.path.abspath(save_dir_root)
    os.makedirs(save_dir_root, exist_ok=True)
    best_validation_loss = float("inf")

    progress = tqdm(range(iterations), disable=not accelerator.is_main_process)
    for iteration in progress:
        model.train()
        optimizer.zero_grad(set_to_none=True)
        train_metrics = torch.zeros(6, device=device)

        for _ in range(gradient_accumulate_every):
            try:
                batch = next(train_iterator)
            except StopIteration:
                train_iterator = iter(train_loader)
                batch = next(train_iterator)
            batch = {name: value.to(device) for name, value in batch.items()}
            with accelerator.autocast():
                output = model(**batch)
                loss = output.loss / gradient_accumulate_every
            accelerator.backward(loss)
            train_metrics += torch.stack(
                [
                    output.loss.detach(),
                    output.ce_loss.detach(),
                    output.kd_loss.detach(),
                    output.teacher_ce_loss.detach(),
                    output.student_token_accuracy.detach(),
                    output.teacher_token_accuracy.detach(),
                ]
            ) / gradient_accumulate_every

        grad_norm = None
        if max_grad_norm is not None:
            grad_norm = accelerator.clip_grad_norm_(
                model.parameters(), max_grad_norm
            )
        optimizer.step()
        progress.set_postfix(loss=f"{train_metrics[0].item():.4f}")

        metrics = {
            "train/loss": train_metrics[0].item(),
            "train/ce_loss": train_metrics[1].item(),
            "train/kd_loss": train_metrics[2].item(),
            "train/teacher_ce_loss": train_metrics[3].item(),
            "train/student_token_accuracy": train_metrics[4].item(),
            "train/teacher_token_accuracy": train_metrics[5].item(),
            "train/learning_rate": optimizer.param_groups[0]["lr"],
        }
        if grad_norm is not None:
            metrics["train/grad_norm"] = grad_norm.item()
        should_eval = (iteration + 1) % eval_every == 0 or iteration + 1 == iterations
        if should_eval:
            model.eval()
            validation_metrics = torch.zeros(6, device=device)
            validation_batches = 0
            with torch.no_grad():
                for batch in validation_loader:
                    batch = {name: value.to(device) for name, value in batch.items()}
                    with accelerator.autocast():
                        output = model(**batch)
                    validation_metrics += torch.stack(
                        [
                            output.loss,
                            output.ce_loss,
                            output.kd_loss,
                            output.teacher_ce_loss,
                            output.student_token_accuracy,
                            output.teacher_token_accuracy,
                        ]
                    )
                    validation_batches += 1
            validation_metrics /= validation_batches
            validation_loss = validation_metrics[0].item()
            metrics.update(
                {
                    "validation/loss": validation_loss,
                    "validation/ce_loss": validation_metrics[1].item(),
                    "validation/kd_loss": validation_metrics[2].item(),
                    "validation/teacher_ce_loss": validation_metrics[3].item(),
                    "validation/student_token_accuracy": validation_metrics[
                        4
                    ].item(),
                    "validation/teacher_token_accuracy": validation_metrics[
                        5
                    ].item(),
                }
            )
            print(metrics)

            if validation_loss < best_validation_loss and accelerator.is_main_process:
                best_validation_loss = validation_loss
                torch.save(
                    {
                        "iter": iteration,
                        "model": accelerator.unwrap_model(model).state_dict(),
                        "optimizer": optimizer.state_dict(),
                        "validation_loss": validation_loss,
                    },
                    os.path.join(save_dir_root, "best_checkpoint.pt"),
                )
                tokenizer.save_pretrained(os.path.join(save_dir_root, "tokenizer"))

        if accelerator.is_main_process:
            if (iteration + 1) % save_model_every == 0 or iteration + 1 == iterations:
                torch.save(
                    {
                        "iter": iteration,
                        "model": accelerator.unwrap_model(model).state_dict(),
                        "optimizer": optimizer.state_dict(),
                    },
                    os.path.join(save_dir_root, f"checkpoint_{iteration}.pt"),
                )
                tokenizer.save_pretrained(os.path.join(save_dir_root, "tokenizer"))
            if wandb_logging:
                wandb.log(metrics, step=iteration + 1)

    if accelerator.is_main_process:
        with open(
            os.path.join(save_dir_root, "training_config.json"),
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                {
                    "model": model_name,
                    "semantic_ids_path": semantic_ids_path,
                    "best_validation_loss": best_validation_loss,
                    "iterations": iterations,
                },
                file,
                indent=2,
            )
    if wandb_logging:
        wandb.finish()


if __name__ == "__main__":
    parse_config()
    train()
