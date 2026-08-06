# V-Market RQ-VAE

This directory adapts the RQ-VAE implementation from
`EdoardoBotta/RQ-VAE-Recommender` to the global V-Market catalog.

## Input contract

The trainer reads the artifacts produced by `02_alignment_and_embedding.ipynb`:

- `global_product_embeddings.f16.npy`: row-major 256-dimensional embeddings.
- `global_embedding_index.parquet`: stable `product_index` to `product_id` mapping.

Legacy Amazon Reviews and MovieLens loaders are intentionally excluded. Locale and
raw price are not part of the RQ-VAE input or semantic-ID namespace.

The three residual codebooks contain `128`, `64`, and `32` entries. Their full
three-token namespace has `262,144` possible cluster SIDs; no item-level collision
suffix is appended.

## Training on Kaggle

By default, `configs/rqvae_vmarket.gin` expects notebook 02 output under
`/kaggle/working/vmarket_phase2_embeddings`.

```bash
pip install -r requirements.txt
python train_rqvae.py configs/rqvae_vmarket.gin
```

Change `train.dataset_folder` in the Gin config if the artifacts are mounted at a
different path.

Notebooks 03 and 04 support Weights & Biases through a Kaggle Secret named
`WANDB_API_KEY`. Project, entity, and run name are configurable in the notebooks
and are passed to the trainers through Gin; the API key is never written to a
config or output artifact.

The same notebooks clone the current training source from
`nam-htran/VSF-MiniApp-Ecommerce` by reading a Kaggle Secret named `GITHUB_TOKEN`.
Authentication is passed through a temporary `GIT_ASKPASS` helper, so the token is
not embedded in the repository URL, command output, or Git configuration.

## Output contract

Training writes checkpoints and these final artifacts:

- `semantic_ids.parquet`: `product_index`, `product_id`, `sid_0`, `sid_1`, `sid_2`.
- `semantic_id_metrics.json`: collision, entropy, and per-codebook usage metrics.

`train_decoder.py` trains the T5 Encoder-Decoder Transformer from the fixed
`semantic_ids.parquet` artifact and the session Parquet files produced by notebook
01. Use `configs/transformer_vmarket.gin` as its base configuration. Its evaluation
metrics are cluster-SID retrieval metrics; cluster-to-item expansion and item-level
ranking are a later stage.
