"""
Scouting Report model for player analysis reports.
"""
import uuid
from django.db import models


class ScoutingReport(models.Model):
    """
    Represents a generated scouting report linked to a player.

    Contains the report text, summary bullets, coverage metadata,
    and source document references for audit trail.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    player = models.ForeignKey(
        'Player',
        on_delete=models.CASCADE,
        related_name='scouting_reports'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Audit/correlation fields
    run_id = models.CharField(max_length=255, null=True, blank=True)  # workflow/run correlation
    request_text = models.TextField(null=True, blank=True)  # original user request

    # Report content
    report_text = models.TextField()  # Full scouting report text
    report_summary = models.JSONField(null=True, blank=True)  # ["bullet1", "bullet2", ...]

    # Coverage metadata
    coverage = models.JSONField(null=True, blank=True)  # {"found": [...], "missing": [...]}

    # Source tracking (internal)
    source_doc_ids = models.JSONField(null=True, blank=True)  # ["doc_a", "doc_b"]

    class Meta:
        db_table = 'scouting_reports'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['player', 'created_at'], name='scouting_reports_player_idx'),
            models.Index(fields=['created_at'], name='scouting_reports_created_idx'),
        ]

    def __str__(self):
        return f"Report for {self.player.display_name} ({self.created_at})"
