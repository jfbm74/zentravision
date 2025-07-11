# ==========================================
# apps/core/management/commands/test_pdf_splitter.py - NUEVO COMANDO
# ==========================================

from django.core.management.base import BaseCommand, CommandError
import os
from apps.extractor.pdf_splitter import GlosaPDFSplitter

class Command(BaseCommand):
    help = 'Prueba el divisor de PDFs con un archivo específico'

    def add_arguments(self, parser):
        parser.add_argument(
            'pdf_path',
            type=str,
            help='Ruta al archivo PDF para dividir'
        )
        parser.add_argument(
            '--output-dir',
            type=str,
            default='./test_output',
            help='Directorio donde guardar los PDFs divididos'
        )
        parser.add_argument(
            '--validate-only',
            action='store_true',
            help='Solo validar el formato del PDF sin dividir'
        )

    def handle(self, *args, **options):
        pdf_path = options['pdf_path']
        output_dir = options['output_dir']
        validate_only = options['validate_only']

        # Verificar que el archivo existe
        if not os.path.exists(pdf_path):
            raise CommandError(f'El archivo {pdf_path} no existe')

        if not pdf_path.lower().endswith('.pdf'):
            raise CommandError('El archivo debe ser un PDF')

        self.stdout.write(
            self.style.SUCCESS(f'Probando divisor con: {pdf_path}')
        )

        try:
            # Inicializar divisor
            splitter = GlosaPDFSplitter()

            # Validar formato
            is_valid, validation_message = splitter.validate_pdf_format(pdf_path)
            
            if is_valid:
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Formato válido: {validation_message}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'⚠ Formato: {validation_message}')
                )

            # Obtener información del PDF
            pdf_info = splitter.get_pdf_info(pdf_path)
            self.stdout.write(f'📄 Páginas totales: {pdf_info["total_pages"]}')
            self.stdout.write(f'📊 Secciones detectadas: {pdf_info["sections_detected"]}')
            self.stdout.write(f'👥 Es múltiple: {"Sí" if pdf_info["is_multi_patient"] else "No"}')

            if validate_only:
                return

            # Detectar si es múltiple
            is_multiple = splitter.detect_multiple_patients(pdf_path)
            
            if not is_multiple:
                self.stdout.write(
                    self.style.WARNING('El PDF contiene un solo paciente, no necesita división')
                )
                return

            # Dividir PDF
            self.stdout.write('Dividiendo PDF...')
            sections = splitter.split_pdf(pdf_path)

            if not sections:
                self.stdout.write(
                    self.style.WARNING('No se pudieron extraer secciones')
                )
                return

            # Crear directorio de salida
            os.makedirs(output_dir, exist_ok=True)

            # Guardar secciones
            for i, (pdf_content, filename, metadata) in enumerate(sections):
                output_path = os.path.join(output_dir, f'section_{i+1}.pdf')
                
                with open(output_path, 'wb') as f:
                    f.write(pdf_content)
                
                self.stdout.write(f'✅ Guardado: {output_path}')
                self.stdout.write(f'   Páginas: {metadata["start_page"]}-{metadata["end_page"]}')
                self.stdout.write(f'   Tamaño: {len(pdf_content)} bytes')
                
                if metadata.get('patient_hint'):
                    self.stdout.write(f'   Paciente: {metadata["patient_hint"]}')

            self.stdout.write(
                self.style.SUCCESS(f'\n🎯 ¡División completada! {len(sections)} secciones en {output_dir}')
            )

        except Exception as e:
            raise CommandError(f'Error: {str(e)}')

