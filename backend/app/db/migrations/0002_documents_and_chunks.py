# Generated migration for documents and chunks models
# Run: python manage.py makemigrations to generate proper migration

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import pgvector.django


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Enable pgvector extension
        pgvector.django.VectorExtension(),
        
        # Create Document model
        migrations.CreateModel(
            name='Document',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('source_type', models.CharField(choices=[('upload', 'Upload'), ('url', 'URL')], default='upload', max_length=20)),
                ('file', models.FileField(blank=True, null=True, upload_to='documents/%Y/%m/%d/')),
                ('mime_type', models.CharField(max_length=100)),
                ('size_bytes', models.BigIntegerField()),
                ('checksum', models.CharField(db_index=True, max_length=64)),
                ('status', models.CharField(choices=[('UPLOADED', 'Uploaded'), ('EXTRACTED', 'Extracted'), ('INDEXING', 'Indexing'), ('READY', 'Ready'), ('FAILED', 'Failed')], db_index=True, default='UPLOADED', max_length=20)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('chunks_count', models.IntegerField(default=0)),
                ('tokens_estimate', models.BigIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'documents',
                'ordering': ['-created_at'],
            },
        ),
        
        # Create DocumentText model
        migrations.CreateModel(
            name='DocumentText',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField()),
                ('page_map', models.JSONField(blank=True, default=dict)),
                ('language', models.CharField(blank=True, default='en', max_length=10)),
                ('extracted_at', models.DateTimeField(auto_now_add=True)),
                ('document', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='extracted_text', to='db.document')),
            ],
            options={
                'db_table': 'document_texts',
            },
        ),
        
        # Create DocumentChunk model
        migrations.CreateModel(
            name='DocumentChunk',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('chunk_index', models.IntegerField(db_index=True)),
                ('content', models.TextField()),
                ('content_hash', models.CharField(db_index=True, max_length=64)),
                ('start_offset', models.IntegerField(blank=True, null=True)),
                ('end_offset', models.IntegerField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('document', models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, related_name='chunks', to='db.document')),
            ],
            options={
                'db_table': 'document_chunks',
                'ordering': ['document', 'chunk_index'],
            },
        ),
        
        # Create ChunkEmbedding model with VectorField
        migrations.CreateModel(
            name='ChunkEmbedding',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('embedding', pgvector.django.VectorField(dimensions=1536, null=True)),
                ('embedding_model', models.CharField(db_index=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('chunk', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='embedding', to='db.documentchunk')),
            ],
            options={
                'db_table': 'chunk_embeddings',
            },
        ),
        
        # Create indexes
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['owner', 'created_at'], name='documents_owner_created_idx'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['owner', 'status'], name='documents_owner_status_idx'),
        ),
        migrations.AddIndex(
            model_name='documentchunk',
            index=models.Index(fields=['document', 'chunk_index'], name='chunks_doc_chunk_idx'),
        ),
        migrations.AddIndex(
            model_name='documentchunk',
            index=models.Index(fields=['document', 'content_hash'], name='chunks_doc_hash_idx'),
        ),
        
        # Add unique constraint
        migrations.AlterUniqueTogether(
            name='documentchunk',
            unique_together={('document', 'chunk_index')},
        ),
        
        # Create HNSW index on embedding field (if pgvector supports it)
        # Note: This may need to be done via raw SQL if Django migration doesn't support it
        migrations.RunSQL(
            sql="CREATE INDEX IF NOT EXISTS chunk_embedding_hnsw_idx ON chunk_embeddings USING hnsw (embedding vector_l2_ops) WITH (m = 16, ef_construction = 64);",
            reverse_sql="DROP INDEX IF EXISTS chunk_embedding_hnsw_idx;",
        ),
    ]
