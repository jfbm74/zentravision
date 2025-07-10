# apps/core/migrations/0002_add_batch_support.py

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        # Agregar nuevos campos a GlosaDocument
        migrations.AddField(
            model_name='glosadocument',
            name='parent_document',
            field=models.ForeignKey(
                blank=True, 
                null=True, 
                on_delete=django.db.models.deletion.CASCADE, 
                related_name='child_documents', 
                to='core.glosadocument'
            ),
        ),
        migrations.AddField(
            model_name='glosadocument',
            name='is_master_document',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='glosadocument',
            name='patient_section_number',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='glosadocument',
            name='total_sections',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        
        # Crear el modelo ProcessingBatch
        migrations.CreateModel(
            name='ProcessingBatch',
            fields=[
                ('id', models.UUIDField(
                    default=uuid.uuid4, 
                    editable=False, 
                    primary_key=True, 
                    serialize=False
                )),
                ('total_documents', models.PositiveIntegerField()),
                ('completed_documents', models.PositiveIntegerField(default=0)),
                ('failed_documents', models.PositiveIntegerField(default=0)),
                ('batch_status', models.CharField(
                    choices=[
                        ('splitting', 'Dividiendo PDF'),
                        ('processing', 'Procesando'),
                        ('completed', 'Completado'),
                        ('error', 'Error'),
                        ('partial_error', 'Completado con errores'),
                    ],
                    default='splitting',
                    max_length=20
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('master_document', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='processing_batch',
                    to='core.glosadocument'
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        
        # Actualizar el orden de GlosaDocument para incluir patient_section_number
        migrations.AlterModelOptions(
            name='glosadocument',
            options={'ordering': ['-created_at', 'patient_section_number']},
        ),
    ]