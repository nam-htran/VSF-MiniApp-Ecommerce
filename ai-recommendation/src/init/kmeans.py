import numpy as np
import torch

from typing import NamedTuple


def kmeans_init_(
    tensor: torch.Tensor,
    x: torch.Tensor,
    balanced: bool = False,
    max_iters: int = 100,
):
    assert tensor.dim() == 2
    assert x.dim() == 2

    with torch.no_grad():
        k, _ = tensor.shape
        kmeans_out = Kmeans(k=k, max_iters=max_iters, balanced=balanced).run(x)
        tensor.data.copy_(kmeans_out.centroids)


class KmeansOutput(NamedTuple):
    centroids: torch.Tensor
    assignment: torch.Tensor


class Kmeans:
    def __init__(
        self,
        k: int,
        max_iters: int = None,
        stop_threshold: float = 1e-10,
        balanced: bool = False,
        balanced_max_rounds: int = 32,
    ) -> None:
        self.k = k
        self.iters = max_iters
        self.stop_threshold = stop_threshold
        self.balanced = balanced
        self.balanced_max_rounds = balanced_max_rounds
        self.centroids = None
        self.assignment = None

    def _init_centroids(self, x: torch.Tensor) -> None:
        B, _ = x.shape
        init_idx = np.random.choice(B, self.k, replace=B < self.k)
        self.centroids = x[init_idx, :].clone()
        self.assignment = None

    def _pairwise_sq_dist(self, x: torch.Tensor) -> torch.Tensor:
        """[B, K] squared L2 distances via the expanded square.

        Materialising the [B, K, D] difference instead costs D times the memory
        — 2.6 GB at B=20000, K=1024, D=32.
        """
        return (
            (x**2).sum(dim=1, keepdim=True)
            + (self.centroids**2).sum(dim=1).unsqueeze(0)
            - 2 * x @ self.centroids.T
        ).clamp_min_(0)

    def _balanced_assign(self, dist: torch.Tensor) -> torch.Tensor:
        """Capacity-constrained assignment: no centroid takes more than ceil(B/K).

        Round-based greedy, fully vectorised. Each round every unassigned point
        bids for its nearest centroid that still has room; each centroid keeps
        the closest bidders it can fit and rejects the rest, who bid again next
        round. Approximates the globally-sorted greedy without its B*K Python
        loop.
        """
        B, K = dist.shape
        cap = (B + K - 1) // K
        assignment = torch.full((B,), -1, dtype=torch.long, device=dist.device)
        remaining = torch.full((K,), cap, dtype=torch.long, device=dist.device)
        work = dist.clone()

        for _ in range(self.balanced_max_rounds):
            free_rows = (assignment < 0).nonzero(as_tuple=True)[0]
            if free_rows.numel() == 0:
                break

            work[:, remaining <= 0] = float("inf")
            bid = work[free_rows].argmin(dim=1)
            cost = work[free_rows, bid]

            # Group bids by centroid, ascending cost within each group: sort by
            # cost, then stable-sort by centroid so the cost order survives.
            by_cost = torch.argsort(cost)
            order = by_cost[torch.argsort(bid[by_cost], stable=True)]
            grouped = bid[order]

            counts = torch.bincount(grouped, minlength=K)
            starts = torch.cumsum(counts, dim=0) - counts
            rank_in_group = (
                torch.arange(grouped.numel(), device=dist.device) - starts[grouped]
            )
            accepted = rank_in_group < remaining[grouped]
            if not accepted.any():
                break

            winners = free_rows[order[accepted]]
            assignment[winners] = grouped[accepted]
            remaining -= torch.bincount(grouped[accepted], minlength=K)

        stragglers = (assignment < 0).nonzero(as_tuple=True)[0]
        if stragglers.numel() > 0:
            work[:, remaining <= 0] = float("inf")
            assignment[stragglers] = work[stragglers].argmin(dim=1)
        return assignment

    def _update_centroids(self, x: torch.Tensor) -> None:
        dist = self._pairwise_sq_dist(x)
        if self.balanced and x.size(0) >= self.k:
            centroid_idx = self._balanced_assign(dist)
        else:
            centroid_idx = dist.argmin(dim=1)

        sums = torch.zeros_like(self.centroids).index_add_(0, centroid_idx, x)
        counts = torch.bincount(centroid_idx, minlength=self.k)
        self.centroids = sums / counts.clamp_min(1).unsqueeze(1).to(sums.dtype)

        # Re-seed centroids nobody claimed, otherwise they stay dead forever.
        dead = counts == 0
        num_dead = int(dead.sum())
        if num_dead > 0:
            if x.size(0) == 0:
                raise ValueError("Can not choose random element from x, x is empty")
            reseed = torch.randint(0, x.size(0), (num_dead,), device=x.device)
            self.centroids[dead] = x[reseed]

        self.assignment = centroid_idx

    def run(self, x):
        self._init_centroids(x)

        i = 0
        while self.iters is None or i < self.iters:
            old_c = self.centroids.clone()
            self._update_centroids(x)
            if torch.norm(self.centroids - old_c, dim=1).max() < self.stop_threshold:
                break
            i += 1

        return KmeansOutput(centroids=self.centroids, assignment=self.assignment)
