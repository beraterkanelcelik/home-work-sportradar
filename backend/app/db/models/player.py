"""
Player model for scouting report flow.
"""
import uuid
from django.db import models
from django.conf import settings


class Player(models.Model):
    """
    Represents a player item with identity, physical, and scouting attributes.

    MVP rules:
    - No existence check (always create new player row)
    - Optional fields: store only what is found, omit unknown
    """

    class Sport(models.TextChoices):
        NBA = 'nba', 'NBA'
        FOOTBALL = 'football', 'Football'
        UNKNOWN = 'unknown', 'Unknown'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Multi-tenancy: owner FK to User
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='players',
        db_index=True
    )

    # Identity (required)
    display_name = models.TextField()
    sport = models.CharField(
        max_length=20,
        choices=Sport.choices,
        default=Sport.UNKNOWN,
        db_index=True
    )

    # Identity (optional)
    positions = models.JSONField(null=True, blank=True)  # ["SG", "SF"] or ["QB"]
    teams = models.JSONField(null=True, blank=True)  # ["LAL"] or ["KC Chiefs"]
    league = models.CharField(max_length=50, null=True, blank=True)  # "NBA", "NFL"
    aliases = models.JSONField(null=True, blank=True)  # ["Steph Curry", "Wardell Curry"]

    # Physical (optional)
    height_cm = models.IntegerField(null=True, blank=True)
    weight_kg = models.IntegerField(null=True, blank=True)
    measurements = models.JSONField(null=True, blank=True)  # {"wingspan_cm": 208}

    # Scouting (optional)
    strengths = models.JSONField(null=True, blank=True)  # ["...", "..."]
    weaknesses = models.JSONField(null=True, blank=True)
    style_tags = models.JSONField(null=True, blank=True)  # ["3PT shooter", "POA defender"]
    risk_notes = models.JSONField(null=True, blank=True)
    role_projection = models.TextField(null=True, blank=True)

    # Latest report link (set after ScoutingReport is created)
    latest_report = models.ForeignKey(
        'ScoutingReport',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )

    class Meta:
        db_table = 'players'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', 'created_at'], name='players_owner_created_idx'),
            models.Index(fields=['display_name'], name='players_display_name_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(height_cm__gte=80, height_cm__lte=260) | models.Q(height_cm__isnull=True),
                name='players_height_cm_range'
            ),
            models.CheckConstraint(
                check=models.Q(weight_kg__gte=30, weight_kg__lte=200) | models.Q(weight_kg__isnull=True),
                name='players_weight_kg_range'
            ),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.sport})"
