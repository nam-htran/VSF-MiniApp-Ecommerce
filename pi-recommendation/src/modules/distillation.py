from typing import NamedTuple

import torch
import torch.nn.functional as F
from torch import Tensor, nn


class DistillationOutput(NamedTuple):
    loss: Tensor
    ce_loss: Tensor
    kd_loss: Tensor
    teacher_ce_loss: Tensor
    student_token_accuracy: Tensor
    teacher_token_accuracy: Tensor


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

    def _target_logits(self, input_ids, attention_mask):
        hidden_states = self.backbone.get_decoder()(
            input_ids=input_ids,
            attention_mask=attention_mask,
            use_cache=False,
            return_dict=True,
        ).last_hidden_state
        # Four target tokens end each row, and position t predicts t + 1.
        starts = attention_mask.sum(dim=1) - 5
        offsets = torch.arange(4, device=hidden_states.device)
        positions = starts.unsqueeze(1) + offsets
        target_states = hidden_states.gather(
            1, positions.unsqueeze(-1).expand(-1, -1, hidden_states.shape[-1])
        )
        return self.backbone.get_output_embeddings()(target_states)

    def forward(
        self,
        student_input_ids,
        student_attention_mask,
        teacher_input_ids,
        teacher_attention_mask,
        target_codes,
    ) -> DistillationOutput:
        if target_codes.ndim != 2 or target_codes.shape[1] != 4:
            raise ValueError("target_codes must have shape [batch, 4]")

        # Teacher and student are two passes through these same weights.
        with torch.no_grad():
            teacher_logits = self._target_logits(
                teacher_input_ids,
                teacher_attention_mask,
            )
        student_logits = self._target_logits(
            student_input_ids,
            student_attention_mask,
        )

        ce_losses = []
        kd_losses = []
        teacher_ce_losses = []
        student_accuracies = []
        teacher_accuracies = []
        for level in range(4):
            valid_token_ids = getattr(self, f"sid_token_ids_{level}")
            level_student = student_logits[:, level].index_select(
                dim=-1, index=valid_token_ids
            ).float()
            level_teacher = teacher_logits[:, level].index_select(
                dim=-1, index=valid_token_ids
            ).float()
            targets = target_codes[:, level].long()
            ce_losses.append(
                F.cross_entropy(level_student, targets)
            )
            teacher_ce_losses.append(F.cross_entropy(level_teacher, targets))
            student_accuracies.append(
                (level_student.argmax(dim=-1) == targets).float()
            )
            teacher_accuracies.append(
                (level_teacher.argmax(dim=-1) == targets).float()
            )

            # The collision suffix identifies the item but carries no semantics.
            if level < 3:
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
        teacher_ce_loss = torch.stack(teacher_ce_losses).mean()
        student_token_accuracy = torch.stack(student_accuracies).mean()
        teacher_token_accuracy = torch.stack(teacher_accuracies).mean()
        loss = ce_loss + self.kd_weight * kd_loss
        return DistillationOutput(
            loss=loss,
            ce_loss=ce_loss,
            kd_loss=kd_loss,
            teacher_ce_loss=teacher_ce_loss,
            student_token_accuracy=student_token_accuracy,
            teacher_token_accuracy=teacher_token_accuracy,
        )
