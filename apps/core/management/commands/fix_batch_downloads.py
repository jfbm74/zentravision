# ============================================================================
# COMANDO DE MANAGEMENT PARA REPARAR BATCHES PROBLEMÁTICOS
# ============================================================================


from django.core.management.base import BaseCommand
from apps.core.models import ProcessingBatch
from apps.core.views import debug_csv_generation

class Command(BaseCommand):
    help = 'Diagnostica y repara problemas con descargas de batches'

    def add_arguments(self, parser):
        parser.add_argument('--batch-id', type=str, help='ID específico de batch para revisar')
        parser.add_argument('--fix-all', action='store_true', help='Intentar reparar todos los batches problemáticos')

    def handle(self, *args, **options):
        if options.get('batch_id'):
            self.stdout.write(f"Diagnosticando batch {options['batch_id']}...")
            debug_csv_generation(options['batch_id'])
        
        elif options.get('fix_all'):
            self.stdout.write("Buscando batches problemáticos...")
            problematic_batches = ProcessingBatch.objects.filter(
                batch_status__in=['completed', 'partial_error'],
                completed_documents__gt=0
            )
            
            for batch in problematic_batches:
                self.stdout.write(f"Revisando batch {batch.id}...")
                debug_csv_generation(str(batch.id))
        
        else:
            self.stdout.write("Especifica --batch-id o --fix-all")
