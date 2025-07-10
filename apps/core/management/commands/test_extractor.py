# apps/core/management/commands/test_extractor.py
"""
Comando para probar el extractor de glosas médicas
Uso: python manage.py test_extractor [ruta_archivo.pdf]
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
import os
import json
from apps.extractor.medical_claim_extractor_fixed import MedicalClaimExtractor

class Command(BaseCommand):
    help = 'Prueba el extractor de glosas médicas con un archivo PDF'

    def add_arguments(self, parser):
        parser.add_argument(
            'pdf_path',
            type=str,
            help='Ruta al archivo PDF de la glosa médica'
        )
        parser.add_argument(
            '--strategy',
            type=str,
            choices=['hybrid', 'ai_only', 'ocr_only'],
            default='hybrid',
            help='Estrategia de extracción a usar'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Archivo donde guardar el resultado JSON'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Mostrar información detallada'
        )

    def handle(self, *args, **options):
        pdf_path = options['pdf_path']
        strategy = options['strategy']
        output_file = options.get('output')
        verbose = options.get('verbose', False)

        # Verificar que el archivo existe
        if not os.path.exists(pdf_path):
            raise CommandError(f'El archivo {pdf_path} no existe')

        if not pdf_path.lower().endswith('.pdf'):
            raise CommandError('El archivo debe ser un PDF')

        self.stdout.write(
            self.style.SUCCESS(f'Iniciando extracción de: {pdf_path}')
        )
        self.stdout.write(f'Estrategia: {strategy}')

        try:
            # Inicializar extractor
            openai_api_key = getattr(settings, 'OPENAI_API_KEY', None)
            if verbose:
                if openai_api_key:
                    self.stdout.write('✓ OpenAI API key configurada')
                else:
                    self.stdout.write('⚠ OpenAI API key no configurada (usando solo OCR)')

            extractor = MedicalClaimExtractor(openai_api_key=openai_api_key)

            # Extraer datos
            self.stdout.write('Procesando documento...')
            result = extractor.extract_from_pdf(pdf_path, strategy=strategy)

            # Verificar si hubo errores
            if result.get('error'):
                self.stdout.write(
                    self.style.ERROR(f'Error en extracción: {result["error"]}')
                )
                return

            # Mostrar resumen de resultados
            self.show_extraction_summary(result, verbose)

            # Guardar archivo de salida si se especificó
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                self.stdout.write(
                    self.style.SUCCESS(f'Resultado guardado en: {output_file}')
                )

        except Exception as e:
            raise CommandError(f'Error procesando archivo: {str(e)}')

    def show_extraction_summary(self, result, verbose=False):
        """Muestra un resumen de los resultados extraídos"""
        
        self.stdout.write(self.style.SUCCESS('\n=== RESUMEN DE EXTRACCIÓN ==='))

        # Información del paciente
        patient_info = result.get('patient_info', {})
        if patient_info:
            self.stdout.write('\n📋 INFORMACIÓN DEL PACIENTE:')
            if patient_info.get('nombre'):
                self.stdout.write(f'  • Nombre: {patient_info["nombre"]}')
            if patient_info.get('documento'):
                doc_type = patient_info.get('tipo_documento', 'N/A')
                self.stdout.write(f'  • Documento: {doc_type} {patient_info["documento"]}')
            if patient_info.get('edad'):
                self.stdout.write(f'  • Edad: {patient_info["edad"]} años')

        # Información de póliza
        policy_info = result.get('policy_info', {})
        if policy_info:
            self.stdout.write('\n🏥 INFORMACIÓN DE PÓLIZA:')
            if policy_info.get('poliza'):
                self.stdout