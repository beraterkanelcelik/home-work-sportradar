# Generated for Player and ScoutingReport models (tables already exist)

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0007_message_sender_type"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Player",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("display_name", models.TextField()),
                (
                    "sport",
                    models.CharField(
                        choices=[
                            ("nba", "NBA"),
                            ("football", "Football"),
                            ("unknown", "Unknown"),
                        ],
                        db_index=True,
                        default="unknown",
                        max_length=20,
                    ),
                ),
                ("positions", models.JSONField(blank=True, null=True)),
                ("teams", models.JSONField(blank=True, null=True)),
                ("league", models.CharField(blank=True, max_length=50, null=True)),
                ("aliases", models.JSONField(blank=True, null=True)),
                ("height_cm", models.IntegerField(blank=True, null=True)),
                ("weight_kg", models.IntegerField(blank=True, null=True)),
                ("measurements", models.JSONField(blank=True, null=True)),
                ("strengths", models.JSONField(blank=True, null=True)),
                ("weaknesses", models.JSONField(blank=True, null=True)),
                ("style_tags", models.JSONField(blank=True, null=True)),
                ("risk_notes", models.JSONField(blank=True, null=True)),
                ("role_projection", models.TextField(blank=True, null=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="players",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "players",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ScoutingReport",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("run_id", models.CharField(blank=True, max_length=255, null=True)),
                ("request_text", models.TextField(blank=True, null=True)),
                ("report_text", models.TextField()),
                ("report_summary", models.JSONField(blank=True, null=True)),
                ("coverage", models.JSONField(blank=True, null=True)),
                ("source_doc_ids", models.JSONField(blank=True, null=True)),
                (
                    "player",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scouting_reports",
                        to="db.player",
                    ),
                ),
            ],
            options={
                "db_table": "scouting_reports",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="player",
            name="latest_report",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="db.scoutingreport",
            ),
        ),
        migrations.AddIndex(
            model_name="scoutingreport",
            index=models.Index(
                fields=["player", "created_at"], name="scouting_reports_player_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="scoutingreport",
            index=models.Index(
                fields=["created_at"], name="scouting_reports_created_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="player",
            index=models.Index(
                fields=["owner", "created_at"], name="players_owner_created_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="player",
            index=models.Index(
                fields=["display_name"], name="players_display_name_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="player",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(("height_cm__gte", 80), ("height_cm__lte", 260)),
                    ("height_cm__isnull", True),
                    _connector="OR",
                ),
                name="players_height_cm_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="player",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(("weight_kg__gte", 30), ("weight_kg__lte", 200)),
                    ("weight_kg__isnull", True),
                    _connector="OR",
                ),
                name="players_weight_kg_range",
            ),
        ),
    ]
