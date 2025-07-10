
# ==========================================
# apps/core/management/commands/cleanup_batches.py - NUEVO COMANDO
# ==========================================

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.core.models import ProcessingBatch, GlosaDocument
import os

class Command(BaseCommand):
    help = 'Limpia batches antiguos y archivos huérfanos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Días de antigüedad para considerar batches como antiguos'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se haría sin ejecutar'
        )
        parser.add_argument(
            '--cleanup-files',
            action='store_true',
            help='También limpiar archivos huérfanos'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        cleanup_files = options['cleanup_files']

        cutoff_date = timezone.now() - timedelta(days=days)

        self.stdout.write(f'Buscando batches anteriores a: {cutoff_date}')

        # Encontrar batches antiguos completados
        old_batches = ProcessingBatch.objects.filter(
            completed_at__lt=cutoff_date,
            batch_status__in=['completed', 'partial_error']
        )

        self.stdout.write(f'Encontrados {old_batches.count()} batches antiguos')

        if dry_run:
            self.stdout.write(self.style.WARNING('MODO DRY-RUN: No se eliminarán datos'))
            
            for batch in old_batches:
                self.stdout.write(f'  - {batch.id}: {batch.master_document.original_filename}')
        else:
            # Eliminar batches antiguos
            deleted_count = 0
            for batch in old_batches:
                try:
                    filename = batch.master_document.original_filename
                    batch.delete()  # Esto también eliminará el documento maestro y sus hijos
                    deleted_count += 1
                    self.stdout.write(f'✓ Eliminado: {filename}')
                except Exception as e:
                    self.stdout.write(f'✗ Error eliminando {batch.id}: {e}')

            self.stdout.write(
                self.style.SUCCESS(f'Eliminados {deleted_count} batches antiguos')
            )

        # Limpiar archivos huérfanos si se solicita
        if cleanup_files:
            self.stdout.write('\nBuscando archivos huérfanos...')
            
            orphaned_files = []
            
            # Buscar documentos con archivos faltantes
            for glosa in GlosaDocument.objects.all():
                if glosa.original_file:
                    if not os.path.exists(glosa.original_file.path):
                        orphaned_files.append(glosa.id)
            
            if orphaned_files:
                self.stdout.write(f'Encontrados {len(orphaned_files)} documentos con archivos faltantes')
                
                if not dry_run:
                    GlosaDocument.objects.filter(id__in=orphaned_files).delete()
                    self.stdout.write(
                        self.style.SUCCESS(f'Eliminados {len(orphaned_files)} documentos huérfanos')
                    )
            else:
                self.stdout.write('No se encontraron archivos huérfanos')

        self.stdout.write(self.style.SUCCESS('\n🧹 Limpieza completada'))