# apps/core/management/commands/debug_extraction.py

from django.core.management.base import BaseCommand
from django.conf import settings
from apps.extractor.medical_claim_extractor import MedicalClaimExtractor
import json

class Command(BaseCommand):
    help = 'Debug extracción de procedimientos'

    def add_arguments(self, parser):
        parser.add_argument('pdf_path', type=str, help='Ruta al PDF')

    def handle(self, *args, **options):
        pdf_path = options['pdf_path']
        
        # Inicializar extractor
        extractor = MedicalClaimExtractor(openai_api_key=getattr(settings, 'OPENAI_API_KEY', None))
        
        # Extraer texto
        text = extractor._extract_text_from_pdf(pdf_path)
        
        self.stdout.write("=== TEXTO EXTRAÍDO ===")
        self.stdout.write(text[:2000] + "...")
        
        # Limpiar texto
        cleaned_text = extractor._clean_text_for_table_parsing(text)
        
        self.stdout.write("\n=== TEXTO LIMPIO ===")
        self.stdout.write(cleaned_text[:2000] + "...")
        
        # Probar patrones
        self.stdout.write("\n=== PROBANDO PATRONES ===")
        
        import re
        
        # Patrón mejorado específico
        pattern = r'(\d{5}|00000)\s+([A-ZÁÉÍÓÚÑ\s\w\/\#\,\.\-\(\)]+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)(?:\s+(.+?))?(?=\n\d{5}|\n00000|\nTotal|\n[A-Z]{2,}|\Z)'
        
        matches = re.finditer(pattern, cleaned_text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        for i, match in enumerate(matches):
            self.stdout.write(f"\nCoincidencia {i+1}:")
            self.stdout.write(f"  Grupos: {match.groups()}")
            
        # Probar método línea por línea
        self.stdout.write("\n=== MÉTODO LÍNEA POR LÍNEA ===")
        
        lines = cleaned_text.split('\n')
        in_table = False
        
        for line_num, line in enumerate(lines):
            if 'Código' in line and 'Descripción' in line:
                self.stdout.write(f"Línea {line_num}: INICIO DE TABLA")
                in_table = True
                continue
                
            if in_table and line.strip():
                # Probar patrón simple
                simple_pattern = r'^(\d{5}|00000)\s+(.+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)'
                match = re.match(simple_pattern, line.strip())
                
                if match:
                    self.stdout.write(f"Línea {line_num}: PROCEDIMIENTO ENCONTRADO")
                    self.stdout.write(f"  Código: {match.group(1)}")
                    self.stdout.write(f"  Descripción: {match.group(2)[:50]}...")
                    self.stdout.write(f"  Cantidad: {match.group(3)}")
                    self.stdout.write(f"  Valores: {match.group(4)}, {match.group(5)}, {match.group(6)}")
                elif line.strip().startswith(('00010', '37202', '39221', '21105', '39202', '39305', '21101')):
                    self.stdout.write(f"Línea {line_num}: POSIBLE PROCEDIMIENTO NO CAPTURADO")
                    self.stdout.write(f"  Contenido: {line.strip()[:100]}...")
                
            if 'Total' in line and '$' in line and in_table:
                self.stdout.write(f"Línea {line_num}: FIN DE TABLA")
                break