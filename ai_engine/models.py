
from django.conf import settings
from django.db import models


class AIRunLog(models.Model):
    """
    Audit trail of AI operations:
    resume parsing, matching, question generation,
    and answer analysis.
    """

    task = models.CharField(
        max_length=40,
        db_index=True
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+"
    )

    provider = models.CharField(
        max_length=30,
        default="heuristic"
    )

    input_ref = models.CharField(
        max_length=100,
        blank=True
    )

    output = models.JSONField(
        default=dict,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.task} ({self.provider}) "
            f"{self.created_at:%Y-%m-%d %H:%M}"
        )
