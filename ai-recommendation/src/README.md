# V-Market RQ-VAE

This directory adapts the RQ-VAE implementation from
`EdoardoBotta/RQ-VAE-Recommender` to the global V-Market catalog.

## Input contract

The trainer reads the artifacts produced by `02_alignment_and_embedding.ipynb`:

- `global_product_embeddings.f16.npy`: row-major 256-dimensional embeddings.
- `global_embedding_index.parquet`: stable `product_index` to `product_id` mapping.

Legacy Amazon Reviews and MovieLens loaders are intentionally excluded. Locale and
raw price are not part of the RQ-VAE input or semantic-ID namespace.

## Training on Kaggle

By default, `configs/rqvae_vmarket.gin` expects notebook 02 output under
`/kaggle/working/vmarket_phase2_embeddings`.

```bash
pip install -r requirements.txt
python train_rqvae.py configs/rqvae_vmarket.gin
```

Change `train.dataset_folder` in the Gin config if the artifacts are mounted at a
different path.

## Output contract

Training writes checkpoints and these final artifacts:

- `semantic_ids.parquet`: `product_index`, `product_id`, `sid_0`, `sid_1`, `sid_2`, `collision_index`.
- `semantic_id_metrics.json`: collision, entropy, and per-codebook usage metrics.

`train_decoder.py` is intentionally blocked until the V-Market session adapter and
the SID collision policy are finalized from the RQ-VAE results.
