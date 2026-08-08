import gin
import os
import torch
import numpy as np
import wandb

from accelerate import Accelerator
from datetime import datetime
from datetime import timezone
from data.processed import ItemData
from data.processed import RecDataset
from data.utils import batch_to
from data.utils import cycle
from data.utils import next_batch
from modules.rqvae import RqVae
from modules.quantize import QuantizeForwardMode
from modules.tokenizer.semids import SemanticIdTokenizer
from modules.utils import parse_config
from torch.optim import AdamW
from torch.utils.data import BatchSampler
from torch.utils.data import DataLoader
from torch.utils.data import RandomSampler
from tqdm import tqdm


@gin.configurable
def train(
    iterations=50000,
    batch_size=64,
    learning_rate=0.0001,
    weight_decay=0.01,
    dataset_folder="dataset/vmarket",
    dataset=RecDataset.VMARKET,
    pretrained_rqvae_path=None,
    save_dir_root="out/",
    use_kmeans_init=True,
    split_batches=True,
    amp=False,
    wandb_logging=False,
    wandb_project="rq-vae-training",
    wandb_run_name_prefix="rqvae",
    do_eval=True,
    mixed_precision_type="fp16",
    gradient_accumulate_every=1,
    save_model_every=1000000,
    eval_every=50000,
    commitment_weight=0.25,
    vae_n_cat_feats=18,
    vae_input_dim=18,
    vae_embed_dim=16,
    vae_hidden_dims=[18, 18],
    vae_codebook_sizes=[128, 64, 32],
    vae_codebook_normalize=False,
    vae_codebook_mode=QuantizeForwardMode.GUMBEL_SOFTMAX,
    vae_sim_vq=False,
    vae_balanced_kmeans=False,
    vae_entropy_weight=0.0,
    vae_entropy_temperature=1.0,
):
    vae_n_layers = len(vae_codebook_sizes)
    if wandb_logging:
        params = locals()

    if not torch.cuda.is_available() and torch.backends.mps.is_available():
        os.environ.setdefault("ACCELERATE_USE_MPS_DEVICE", "True")
        if amp:
            print(
                "Warning: MPS does not support mixed precision training. Disabling amp."
            )
            amp = False

    accelerator = Accelerator(
        split_batches=split_batches,
        mixed_precision=mixed_precision_type if amp else "no",
    )

    device = accelerator.device
    print(f"Device: {device}")

    train_dataset = ItemData(
        root=dataset_folder,
        dataset=dataset,
        train_test_split="train" if do_eval else "all",
    )
    train_sampler = BatchSampler(RandomSampler(train_dataset), batch_size, False)
    train_dataloader = DataLoader(
        train_dataset,
        sampler=train_sampler,
        batch_size=None,
        collate_fn=lambda batch: batch,
    )
    train_dataloader = cycle(train_dataloader)

    if do_eval:
        eval_dataset = ItemData(
            root=dataset_folder,
            dataset=dataset,
            train_test_split="eval",
        )
        eval_sampler = BatchSampler(RandomSampler(eval_dataset), batch_size, False)
        eval_dataloader = DataLoader(
            eval_dataset,
            sampler=eval_sampler,
            batch_size=None,
            collate_fn=lambda batch: batch,
        )

    index_dataset = (
        ItemData(
            root=dataset_folder,
            dataset=dataset,
            train_test_split="all",
        )
        if do_eval
        else train_dataset
    )

    # train_dataloader = accelerator.prepare(train_dataloader)
    # TODO: Investigate bug with prepare eval_dataloader

    model = RqVae(
        input_dim=vae_input_dim,
        embed_dim=vae_embed_dim,
        hidden_dims=vae_hidden_dims,
        codebook_sizes=vae_codebook_sizes,
        codebook_kmeans_init=use_kmeans_init and pretrained_rqvae_path is None,
        codebook_balanced_kmeans=vae_balanced_kmeans,
        codebook_normalize=vae_codebook_normalize,
        codebook_sim_vq=vae_sim_vq,
        codebook_mode=vae_codebook_mode,
        n_cat_features=vae_n_cat_feats,
        commitment_weight=commitment_weight,
        entropy_weight=vae_entropy_weight,
        entropy_temperature=vae_entropy_temperature,
    )

    optimizer = AdamW(
        params=model.parameters(), lr=learning_rate, weight_decay=weight_decay
    )

    if wandb_logging and accelerator.is_main_process:
        wandb.login()
        run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        wandb.init(
            project=wandb_project,
            name=f"{wandb_run_name_prefix}-{run_timestamp}",
            config=params,
        )

    start_iter = 0
    if pretrained_rqvae_path is not None:
        model.load_pretrained(pretrained_rqvae_path)
        state = torch.load(
            pretrained_rqvae_path, map_location=device, weights_only=False
        )
        optimizer.load_state_dict(state["optimizer"])
        start_iter = state["iter"] + 1

    model, optimizer = accelerator.prepare(model, optimizer)

    tokenizer = SemanticIdTokenizer(
        input_dim=vae_input_dim,
        hidden_dims=vae_hidden_dims,
        output_dim=vae_embed_dim,
        codebook_sizes=vae_codebook_sizes,
        n_cat_feats=vae_n_cat_feats,
        rqvae_weights_path=pretrained_rqvae_path,
        rqvae_codebook_normalize=vae_codebook_normalize,
        rqvae_sim_vq=vae_sim_vq,
    )
    tokenizer.rq_vae = model

    end_iter = start_iter + iterations

    with tqdm(
        initial=start_iter,
        total=end_iter,
        disable=not accelerator.is_main_process,
    ) as pbar:
        losses = [[], [], []]
        for iter in range(start_iter, end_iter):
            model.train()
            total_loss = 0
            t = 0.2
            if iter == 0 and use_kmeans_init:
                kmeans_init_data = batch_to(
                    train_dataset[torch.arange(min(20000, len(train_dataset)))], device
                )
                with accelerator.autocast():
                    model(kmeans_init_data, t)

            optimizer.zero_grad()
            for _ in range(gradient_accumulate_every):
                data = next_batch(train_dataloader, device)

                with accelerator.autocast():
                    model_output = model(data, gumbel_t=t)
                    loss = model_output.loss
                    loss = loss / gradient_accumulate_every
                    total_loss += loss

            accelerator.backward(total_loss)

            losses[0].append(total_loss.cpu().item())
            losses[1].append(model_output.reconstruction_loss.cpu().item())
            losses[2].append(model_output.rqvae_loss.cpu().item())
            losses[0] = losses[0][-1000:]
            losses[1] = losses[1][-1000:]
            losses[2] = losses[2][-1000:]
            if iter % 100 == 0:
                print_loss = np.mean(losses[0])
                print_rec_loss = np.mean(losses[1])
                print_vae_loss = np.mean(losses[2])

            pbar.set_description(
                f"loss: {print_loss:.4f}, rl: {print_rec_loss:.4f}, vl: {print_vae_loss:.4f}"
            )

            accelerator.wait_for_everyone()

            optimizer.step()

            accelerator.wait_for_everyone()

            id_diversity_log = {}
            if accelerator.is_main_process and wandb_logging:
                # Compute logs depending on training model_output here to avoid cuda graph overwrite from eval graph.
                emb_norms_avg = model_output.embs_norm.mean(axis=0)
                emb_norms_avg_log = {
                    f"emb_avg_norm_{i}": emb_norms_avg[i].cpu().item()
                    for i in range(vae_n_layers)
                }
                train_log = {
                    "learning_rate": optimizer.param_groups[0]["lr"],
                    "total_loss": total_loss.cpu().item(),
                    "reconstruction_loss": model_output.reconstruction_loss.cpu().item(),
                    "rqvae_loss": model_output.rqvae_loss.cpu().item(),
                    "temperature": t,
                    "batch_unique_sid_rate": model_output.p_unique_ids.cpu().item(),
                    **emb_norms_avg_log,
                }

            if do_eval and ((iter + 1) % eval_every == 0 or iter + 1 == end_iter):
                model.eval()
                with tqdm(
                    eval_dataloader, desc=f"Eval {iter + 1}", disable=True
                ) as pbar_eval:
                    eval_losses = [[], [], []]
                    for batch in pbar_eval:
                        data = batch_to(batch, device)
                        with torch.no_grad():
                            eval_model_output = model(data, gumbel_t=t)

                        eval_losses[0].append(eval_model_output.loss.cpu().item())
                        eval_losses[1].append(
                            eval_model_output.reconstruction_loss.cpu().item()
                        )
                        eval_losses[2].append(eval_model_output.rqvae_loss.cpu().item())

                    eval_losses = np.array(eval_losses).mean(axis=-1)
                    id_diversity_log["eval_total_loss"] = eval_losses[0]
                    id_diversity_log["eval_reconstruction_loss"] = eval_losses[1]
                    id_diversity_log["eval_rqvae_loss"] = eval_losses[2]

            if accelerator.is_main_process:
                if (iter + 1) % save_model_every == 0 or iter + 1 == end_iter:
                    state = {
                        "iter": iter,
                        "model": model.state_dict(),
                        "model_config": model.config,
                        "optimizer": optimizer.state_dict(),
                    }

                    if not os.path.exists(save_dir_root):
                        os.makedirs(save_dir_root)

                    torch.save(state, save_dir_root + f"checkpoint_{iter}.pt")

                if (iter + 1) % eval_every == 0 or iter + 1 == end_iter:
                    tokenizer.reset()
                    model.eval()

                    corpus_ids = tokenizer.precompute_corpus_ids(index_dataset)
                    _, sid_counts = torch.unique(
                        corpus_ids, dim=0, return_counts=True
                    )
                    p = sid_counts / corpus_ids.shape[0]
                    rqvae_entropy = -(p * torch.log(p)).sum()

                    for cid in range(vae_n_layers):
                        _, layer_counts = torch.unique(
                            corpus_ids[:, cid], return_counts=True
                        )
                        id_diversity_log[f"codebook_usage_{cid}"] = (
                            len(layer_counts) / vae_codebook_sizes[cid]
                        )

                    id_diversity_log["rqvae_entropy"] = rqvae_entropy.cpu().item()

                    if iter + 1 == end_iter:
                        semantic_ids = index_dataset.index[
                            ["product_index", "product_id"]
                        ].copy()
                        corpus_ids = corpus_ids.cpu().numpy()
                        for cid in range(vae_n_layers):
                            semantic_ids[f"sid_{cid}"] = corpus_ids[:, cid].astype(
                                np.int16
                            )
                        semantic_ids_path = os.path.join(
                            save_dir_root, "semantic_ids.parquet"
                        )
                        semantic_ids.to_parquet(semantic_ids_path, index=False)
                        print(f"Semantic IDs saved to {semantic_ids_path}")

                if wandb_logging:
                    wandb.log({**train_log, **id_diversity_log})

            pbar.update(1)

    if wandb_logging:
        wandb.finish()


if __name__ == "__main__":
    parse_config()
    train()
