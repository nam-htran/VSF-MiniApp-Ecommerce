from typing import NamedTuple

import torch
import torch.nn.functional as F
from torch import Tensor, nn


class DistillationOutput(NamedTuple):
    loss: Tensor
    ce_loss: Tensor
    kd_loss: Tensor


class QwenDistillationModel(nn.Module):
    """Two context views, one shared causal-LM backbone."""

    def __init__(
        self,
        backbone: nn.Module,
        sid_token_ids,
        kd_weight: float = 1.0,
        temperature: float = 1.0,
    ) -> None:
        super().__init__()
        if len(sid_token_ids) != 4:
            raise ValueError("Expected three semantic token spaces and one suffix space")
        if temperature <= 0:
            raise ValueError("temperature must be positive")

        self.backbone = backbone
        self.kd_weight = kd_weight
        self.temperature = temperature
        for level, token_ids in enumerate(sid_token_ids):
            self.register_buffer(
                f"sid_token_ids_{level}",
                torch.as_tensor(token_ids, dtype=torch.long),
            )

    def _target_logits(self, input_ids, attention_mask, labels):
        output = self.backbone(
            input_ids=input_ids,
            attention_mask=attention_mask,
            use_cache=False,
            return_dict=True,
        )
        # Causal logits at position t predict the label at position t + 1.
        logits = output.logits[:, :-1]
        target_mask = labels[:, 1:] != -100
        target_counts = target_mask.sum(dim=1)
        if not torch.all(target_counts == 4):
            raise ValueError("Each view must supervise exactly four SID tokens")
        return logits[target_mask].reshape(logits.shape[0], 4, logits.shape[-1])

    def forward(
        self,
        student_input_ids,
        student_attention_mask,
        student_labels,
        teacher_input_ids,
        teacher_attention_mask,
        teacher_labels,
        target_codes,
    ) -> DistillationOutput:
        if target_codes.ndim != 2 or target_codes.shape[1] != 4:
            raise ValueError("target_codes must have shape [batch, 4]")

        # Teacher and student are two passes through these same weights.
        with torch.no_grad():
            teacher_logits = self._target_logits(
                teacher_input_ids,
                teacher_attention_mask,
                teacher_labels,
            )
        student_logits = self._target_logits(
            student_input_ids,
            student_attention_mask,
            student_labels,
        )

        ce_losses = []
        kd_losses = []
        for level in range(4):
            valid_token_ids = getattr(self, f"sid_token_ids_{level}")
            level_student = student_logits[:, level].index_select(
                dim=-1, index=valid_token_ids
            ).float()
            ce_losses.append(
                F.cross_entropy(level_student, target_codes[:, level].long())
            )

            # The collision suffix identifies the item but carries no semantics.
            if level < 3:
                level_teacher = teacher_logits[:, level].index_select(
                    dim=-1, index=valid_token_ids
                ).float()
                temperature = self.temperature
                kd_losses.append(
                    F.kl_div(
                        F.log_softmax(level_student / temperature, dim=-1),
                        F.softmax(level_teacher / temperature, dim=-1),
                        reduction="batchmean",
                    )
                    * temperature**2
                )

        ce_loss = torch.stack(ce_losses).mean()
        kd_loss = torch.stack(kd_losses).mean()
        loss = ce_loss + self.kd_weight * kd_loss
        return DistillationOutput(loss=loss, ce_loss=ce_loss, kd_loss=kd_loss)
