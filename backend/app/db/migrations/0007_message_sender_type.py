# Generated manually for adding sender_type to Message model

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0006_alter_document_status_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="sender_type",
            field=models.CharField(
                choices=[("llm", "LLM Context"), ("ui", "UI Only")],
                default="llm",
                help_text="Determines if message is included in LLM context or UI-only",
                max_length=10,
            ),
        ),
        migrations.AddIndex(
            model_name="message",
            index=models.Index(
                fields=["session", "sender_type", "-created_at"],
                name="messages_session_7d05cd_idx",
            ),
        ),
    ]
