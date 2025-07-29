# apps/core/management/commands/test_paginated_extractor.py
"""
Comando para probar el extractor paginado con documentos grandes
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
import os
import json
import logging
from apps.extractor.medical_claim_extractor_fixed import MedicalClaimExtractor
from apps.extractor.openai_paginated_processor import OpenAIPaginatedProcessorV2

# Configurar logging para el comando
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Prueba el extractor paginado con documentos PDF grandes'

    def add_arguments(self, parser):
        parser.add_argument(
            'pdf_path',
            type=str,
            help='Ruta al archivo PDF a procesar'
        )
        parser.add_argument(
            '--strategy',
            type=str,
            choices=['hybrid', 'ai_only', 'ocr_only'],
            default='hybrid',
            help='Estrategia de extracción (default: hybrid)'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Archivo donde guardar el resultado JSON'
        )
        parser.add_argument(
            '--test-pagination',
            action='store_true',
            help='Forzar uso de procesamiento paginado independientemente del tamaño'
        )
        parser.add_argument(
            '--chunk-size',
            type=int,
            default=15,
            help='Número de procedimientos por chunk (default: 15)'
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=2.0,
            help='Segundos de espera entre llamadas a OpenAI (default: 2.0)'
        )

    def handle(self, *args, **options):
        pdf_path = options['pdf_path']
        strategy = options['strategy']
        output_file = options.get('output')
        test_pagination = options['test_pagination']
        chunk_size = options['chunk_size']
        delay = options['delay']

        # Verificar que el archivo existe
        if not os.path.exists(pdf_path):
            raise CommandError(f'El archivo {pdf_path} no existe')

        # Verificar que es un PDF
        if not pdf_path.lower().endswith('.pdf'):
            raise CommandError('El archivo debe ser un PDF')

        # Verificar que OpenAI API key está configurada
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise CommandError('OPENAI_API_KEY no está configurada en las variables de entorno')

        self.stdout.write(
            self.style.SUCCESS(f'🚀 INICIANDO PRUEBA DE EXTRACTOR PAGINADO')
        )
        self.stdout.write('=' * 80)
        self.stdout.write(f'📄 Archivo: {pdf_path}')
        self.stdout.write(f'⚙️ Estrategia: {strategy}')
        self.stdout.write(f'📦 Chunk size: {chunk_size}')
        self.stdout.write(f'⏱️ Delay: {delay}s')
        self.stdout.write(f'🔄 Forzar paginación: {"SÍ" if test_pagination else "NO"}')
        self.stdout.write('=' * 80)

        try:
            # Crear extractor
            extractor = MedicalClaimExtractor(openai_api_key=api_key)
            
            # Si se solicita probar paginación forzada
            if test_pagination:
                self.stdout.write(
                    self.style.WARNING('🔄 PRUEBA FORZADA DE PAGINACIÓN')
                )
                self._test_forced_pagination(pdf_path, api_key, chunk_size, delay, output_file)
            else:
                self.stdout.write(
                    self.style.SUCCESS('📋 PROCESAMIENTO NORMAL (con detección automática)')
                )
                self._test_normal_processing(extractor, pdf_path, strategy, output_file)

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ ERROR: {str(e)}')
            )
            raise CommandError(f'Error procesando archivo: {str(e)}')

    def _test_normal_processing(self, extractor, pdf_path, strategy, output_file):
        """Prueba el procesamiento normal con detección automática"""
        
        self.stdout.write('📖 Extrayendo datos del PDF...')
        
        # Extraer datos
        result = extractor.extract_from_pdf(pdf_path, strategy=strategy)
        
        # Mostrar resultados
        self._display_results(result, "PROCESAMIENTO NORMAL")
        
        # Guardar archivo si se especificó
        if output_file:
            self._save_results(result, output_file)

    def _test_forced_pagination(self, pdf_path, api_key, chunk_size, delay, output_file):
        """Prueba forzada del procesamiento paginado"""
        
        # Extraer texto del PDF primero
        self.stdout.write('📖 Extrayendo texto del PDF...')
        
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            text_content = ""
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text_content += page.get_text()
            
            doc.close()
            
            self.stdout.write(f'✅ Texto extraído: {len(text_content):,} caracteres')
            
        except Exception as e:
            raise CommandError(f'Error extrayendo texto: {str(e)}')
        
        # Crear procesador paginado
        processor = OpenAIPaginatedProcessorV2(
            openai_api_key=api_key,
            chunk_size=chunk_size,
            delay_between_calls=delay
        )
        
        # Analizar documento
        should_paginate, analysis = processor.should_use_pagination(text_content)
        
        self.stdout.write('📊 ANÁLISIS DEL DOCUMENTO:')
        self.stdout.write(f'   - Longitud: {analysis["text_length"]:,} caracteres')
        self.stdout.write(f'   - Procedimientos estimados: {analysis["estimated_procedures"]}')
        self.stdout.write(f'   - Score complejidad: {analysis["complexity_score"]}')
        self.stdout.write(f'   - ¿Usar paginación?: {"SÍ" if should_paginate else "NO"}')
        
        # Forzar procesamiento paginado
        self.stdout.write('🔄 FORZANDO PROCESAMIENTO PAGINADO...')
        
        result = processor.extract_with_pagination(text_content)
        
        # Mostrar resultados
        self._display_results(result, "PROCESAMIENTO PAGINADO FORZADO")
        
        # Guardar archivo si se especificó
        if output_file:
            self._save_results(result, output_file)

    def _display_results(self, result, title):
        """Muestra los resultados de la extracción"""
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'📊 RESULTADOS - {title}'))
        self.stdout.write('=' * 80)
        
        # Información del paciente
        patient_info = result.get('patient_info', {})
        if patient_info:
            self.stdout.write('👤 INFORMACIÓN DEL PACIENTE:')
            self.stdout.write(f'   - Nombre: {patient_info.get("nombre", "N/A")}')
            self.stdout.write(f'   - Documento: {patient_info.get("tipo_documento", "N/A")} {patient_info.get("documento", "N/A")}')
        
        # Información de póliza
        policy_info = result.get('policy_info', {})
        if policy_info:
            self.stdout.write('📋 INFORMACIÓN DE PÓLIZA:')
            self.stdout.write(f'   - Liquidación: {policy_info.get("numero_liquidacion", "N/A")}')
            self.stdout.write(f'   - Póliza: {policy_info.get("poliza", "N/A")}')
            self.stdout.write(f'   - Fecha siniestro: {policy_info.get("fecha_siniestro", "N/A")}')
        
        # Procedimientos
        procedures = result.get('procedures', [])
        self.stdout.write(f'⚕️ PROCEDIMIENTOS: {len(procedures)} encontrados')
        
        if procedures:
            self.stdout.write('   Primeros 5 procedimientos:')
            for i, proc in enumerate(procedures[:5], 1):
                codigo = proc.get('codigo', 'N/A')
                descripcion = proc.get('descripcion', 'N/A')[:50]
                valor = proc.get('valor_total', 0)
                estado = proc.get('estado', 'N/A')
                
                self.stdout.write(f'   {i}. {codigo} - {descripcion}... - ${valor:,.0f} ({estado})')
            
            if len(procedures) > 5:
                self.stdout.write(f'   ... y {len(procedures) - 5} procedimientos más')
        
        # Resumen financiero
        financial = result.get('financial_summary', {})
        if financial:
            total_reclamado = financial.get('total_reclamado', 0)
            total_objetado = financial.get('total_objetado', 0)
            total_pagado = financial.get('total_pagado', 0)
            
            self.stdout.write('💰 RESUMEN FINANCIERO:')
            self.stdout.write(f'   - Total reclamado: ${total_reclamado:,.0f}')
            self.stdout.write(f'   - Total objetado: ${total_objetado:,.0f}')
            self.stdout.write(f'   - Total pagado: ${total_pagado:,.0f}')
            
            if total_reclamado > 0:
                porcentaje_objetado = (total_objetado / total_reclamado) * 100
                self.stdout.write(f'   - % objetado: {porcentaje_objetado:.1f}%')
        
        # Metadata de procesamiento
        metadata = result.get('processing_metadata', {})
        if metadata:
            self.stdout.write('🔧 METADATA DE PROCESAMIENTO:')
            self.stdout.write(f'   - Método: {metadata.get("method", "N/A")}')
            if 'total_api_calls' in metadata:
                self.stdout.write(f'   - Llamadas API: {metadata.get("total_api_calls", 0)}')
            if 'processing_timestamp' in metadata:
                self.stdout.write(f'   - Timestamp: {metadata.get("processing_timestamp", "N/A")}')
        
        self.stdout.write('=' * 80)

    def _save_results(self, result, output_file):
        """Guarda los resultados en un archivo JSON"""
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            self.stdout.write(
                self.style.SUCCESS(f'💾 Resultados guardados en: {output_file}')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error guardando archivo: {str(e)}')
            )

    def _get_file_size_mb(self, file_path):
        """Obtiene el tamaño del archivo en MB"""
        size_bytes = os.path.getsize(file_path)
        size_mb = size_bytes / (1024 * 1024)
        return size_mb