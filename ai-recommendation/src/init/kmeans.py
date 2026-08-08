import numpy as np
import torch

from einops import rearrange
from typing import NamedTuple


def kmeans_init_(tensor: torch.Tensor, x: torch.Tensor, balanced: bool = False):
    assert tensor.dim() == 2
    assert x.dim() == 2

    with torch.no_grad():
        k, _ = tensor.shape
        kmeans_out = Kmeans(k=k, balanced=balanced).run(x)
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
    ) -> None:
        self.k = k
        self.iters = max_iters
        self.stop_threshold = stop_threshold
        self.balanced = balanced
        self.centroids = None
        self.assignment = None

    def _init_centroids(self, x: torch.Tensor) -> None:
        B, D = x.shape
        replace = B < self.k
        init_idx = np.random.choice(B, self.k, replace=replace)
        self.centroids = x[init_idx, :].clone()
        self.assignment = None

    def _update_centroids(self, x, balanced: bool = False) -> torch.Tensor:
        squared_pw_dist = (
            rearrange(x, "b d -> b 1 d") - rearrange(self.centroids, "b d -> 1 b d")
        ) ** 2
        dist = squared_pw_dist.sum(axis=2)  # [B, K]

        if balanced and x.size(0) >= self.k:
            centroid_idx = self._balanced_assign(dist)
        else:
            centroid_idx = dist.min(axis=1).indices

        assigned = (
            rearrange(torch.arange(self.k, device=x.device), "d -> d 1") == centroid_idx
        )

        for cluster in range(self.k):
            is_assigned_to_c = assigned[cluster]
            if not is_assigned_to_c.any():
                if x.size(0) > 0:
                    self.centroids[cluster, :] = x[
                        torch.randint(0, x.size(0), (1,))
                    ].squeeze(0)
                else:
                    raise ValueError("Can not choose random element from x, x is empty")
            else:
                self.centroids[cluster, :] = x[is_assigned_to_c, :].mean(axis=0)
        self.assignment = centroid_idx

    def _balanced_assign(self, dist: torch.Tensor) -> torch.Tensor:
        """Greedy balanced assignment: each centroid gets at most ceil(N/K) points."""
        B, K = dist.shape
        cap = (B + K - 1) // K
        assignment = torch.full((B,), -1, dtype=torch.long, device=dist.device)
        counts = torch.zeros(K, dtype=torch.long, device=dist.device)
        flat_idx = dist.argsort(dim=None)
        for idx in flat_idx:
            i = idx // K
            j = idx % K
            if assignment[i] >= 0:
                continue
            if counts[j] >= cap:
                continue
            assignment[i] = j
            counts[j] += 1
            if (assignment >= 0).all():
                break
        remaining = (assignment < 0).nonzero(as_tuple=True)[0]
        for i in remaining:
            j = dist[i].argmin()
            assignment[i] = j
        return assignment

    def run(self, x):
        self._init_centroids(x)

        i = 0
        while self.iters is None or i < self.iters:
            old_c = self.centroids.clone()
            self._update_centroids(x, balanced=self.balanced)
            if torch.norm(self.centroids - old_c, dim=1).max() < self.stop_threshold:
                break
            i += 1

        return KmeansOutput(centroids=self.centroids, assignment=self.assignment)
