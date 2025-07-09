import logging
import json
import fitz  # PyMuPDF
from typing import Dict, Any, Optional, List
from datetime import datetime
import re
import os

logger = logging.getLogger(__name__)

class MedicalClaimExtractor:
    """
    Extractor mejorado específicamente para glosas SOAT colombianas
    """
    
    def __init__(self, openai_api_key=None):
        self.openai_api_key = openai_api_key
        self._setup_improved_soat_patterns()
        
        # Configurar patrones específicos para SOAT
        self._setup_soat_patterns()
    

    def _setup_improved_soat_patterns(self):
        """Patrones mejorados para extracción de tabla SOAT"""
        
        # PATRONES ESPECÍFICOS PARA EL FORMATO DE TU PDF
        self.improved_procedure_patterns = [
            # Patrón 1: Línea completa con observación
            r'(\d{5}|00000)\s+([A-ZÁÉÍÓÚÑ\s\w\/\#\,\.\-\(\)]+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+(\d{4})\s+>>(.+?)(?=\n\d{5}|\n00000|\nTotal|\n[A-Z]{2,}|\Z)',
            
            # Patrón 2: Línea básica sin observación detallada
            r'(\d{5}|00000)\s+([A-ZÁÉÍÓÚÑ\s\w\/\#\,\.\-\(\)]+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)(?:\s+(.+?))?(?=\n\d{5}|\n00000|\nTotal|\n[A-Z]{2,}|\Z)',
            
            # Patrón 3: Captura procedimientos que continúan en múltiples líneas
            r'^(\d{5}|00000)\s+(.+?)$\n^(.+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)',
            
            # Patrón 4: Específico para tu formato (más restrictivo)
            r'(\d{5}|00000)\s+([A-ZÁÉÍÓÚÑ\s\w\/\#\,\.\-\(\)\%\s]+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)'
        ]
        
        # Patrón para observaciones que continúan en múltiples líneas
        self.observation_continuation_pattern = r'(\d{4})\s+>>\s+(.+?)(?=\n\d{4}\s+>>|\n\d{5}|\n00000|\nTotal|\Z)'

    

    def _extract_soat_procedures_table_improved(self, text: str) -> List[Dict[str, Any]]:
        """Extracción mejorada de la tabla de procedimientos SOAT"""
        procedures = []
        
        logger.info("Iniciando extracción mejorada de tabla SOAT")
        
        # USAR DIRECTAMENTE EL MÉTODO QUE FUNCIONA
        procedures = self._extract_procedures_from_full_text_v2(text)
        
        logger.info(f"Total procedimientos extraídos: {len(procedures)}")
        return procedures


  


    def _extract_procedures_from_full_text(self, text: str) -> List[Dict[str, Any]]:
        """Extrae procedimientos buscando directamente en todo el texto"""
        procedures = []
        
        # Buscar todos los procedimientos que empiecen con códigos válidos
        # Patrón más específico para capturar líneas completas de procedimientos
        procedure_pattern = r'(\d{5}|00000)\s+([A-ZÁÉÍÓÚÑ\s\w\/\#\,\.\-\(\)\%]+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)(?:\s+(.+?))?(?=\n\d{5}|\n00000|\nTotal|\nValor de|\Z)'
        
        matches = re.finditer(procedure_pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        for match in matches:
            try:
                codigo = match.group(1).strip()
                descripcion_raw = match.group(2).strip()
                cantidad = float(match.group(3).strip())
                valor_total = self._parse_money_value(match.group(4))
                valor_pagado = self._parse_money_value(match.group(5))
                valor_objetado = self._parse_money_value(match.group(6))
                observacion_raw = match.group(7).strip() if match.group(7) else ""
                
                # Limpiar descripción
                descripcion = self._clean_procedure_description_v2(descripcion_raw)
                
                # Limpiar observación
                observacion = self._clean_observation_v2(observacion_raw)
                
                # Validar que sea un procedimiento válido
                if self._is_valid_procedure(codigo, descripcion, valor_total):
                    procedure = {
                        'codigo': codigo,
                        'descripcion': descripcion,
                        'cantidad': int(cantidad),
                        'valor_unitario': valor_total / cantidad if cantidad > 0 else 0,
                        'valor_total': valor_total,
                        'valor_pagado': valor_pagado,
                        'valor_objetado': valor_objetado,
                        'observacion': observacion,
                        'estado': 'objetado' if valor_objetado > 0 else 'aceptado'
                    }
                    
                    procedures.append(procedure)
                    logger.info(f"Procedimiento extraído: {codigo} - {descripcion[:50]}...")
                else:
                    logger.warning(f"Procedimiento inválido descartado: {codigo} - {descripcion_raw[:30]}...")
                    
            except Exception as e:
                logger.error(f"Error procesando procedimiento: {e}")
                continue
        
        logger.info(f"Total procedimientos válidos extraídos: {len(procedures)}")
        return procedures



    def _clean_procedure_description_v2(self, description: str) -> str:
        """Limpia descripción de procedimiento - versión mejorada"""
        if not description:
            return ""
        
        # Remover patrones problemáticos
        description = re.sub(r'^\d+\s*', '', description)  # Números al inicio
        description = re.sub(r'\s+\d+\s*$', '', description)  # Números al final
        description = re.sub(r'\$[\d,\.]+', '', description)  # Valores monetarios
        description = re.sub(r'\d{4}\s+>>', '', description)  # Códigos de observación
        
        # Remover texto que claramente no es descripción
        stop_words = ['LIQ-', 'Pagina', 'Liquidación', 'Fecha de', 'Víctima', 'Número de']
        for stop_word in stop_words:
            if stop_word in description:
                pos = description.find(stop_word)
                description = description[:pos].strip()
                break
        
        # Normalizar espacios
        description = re.sub(r'\s+', ' ', description.strip())
        
        # Capitalizar solo la primera letra de cada palabra principal
        if description:
            # Convertir a title case pero mantener acrónimos
            words = description.split()
            cleaned_words = []
            for word in words:
                if len(word) <= 3 and word.isupper():  # Mantener acrónimos
                    cleaned_words.append(word)
                else:
                    cleaned_words.append(word.title())
            description = ' '.join(cleaned_words)
        
        return description



    def _clean_observation_v2(self, observation: str) -> str:
        """Limpia observación - versión mejorada"""
        if not observation:
            return ""
        
        # Extraer solo la parte relevante de la observación
        obs_pattern = r'(\d{4})\s+>>\s+(.+?)(?=\n\d{4}\s+>>|\n\d{5}|\n00000|\nTotal|\Z)'
        match = re.search(obs_pattern, observation, re.DOTALL)
        
        if match:
            observation = match.group(2).strip()
        
        # Normalizar espacios
        observation = re.sub(r'\s+', ' ', observation.strip())
        
        # Truncar si es muy larga (mantener primera parte más importante)
        if len(observation) > 300:
            observation = observation[:300] + "..."
        
        return observation



    def _is_valid_procedure(self, codigo: str, descripcion: str, valor_total: float) -> bool:
        """Valida si es un procedimiento válido"""
        
        # Debe tener código válido
        if not re.match(r'^(\d{5}|00000)$', codigo):
            return False
        
        # Debe tener descripción no vacía y razonable
        if not descripcion or len(descripcion.strip()) < 3:
            return False
        
        # No debe contener patrones de header o metadata
        invalid_patterns = [
            'LIQ-', 'Pagina', 'Liquidación de siniestro', 'Fecha de Pago',
            'Víctima :', 'Número de reclamación', 'Póliza :', 'DX :'
        ]
        
        for pattern in invalid_patterns:
            if pattern in descripcion:
                return False
        
        # Valor total debe ser razonable
        if valor_total <= 0 or valor_total > 10000000:  # Entre 0 y 10 millones
            return False
        
        return True



    def debug_table_extraction_v2(self, text: str):
        """Debug mejorado para extracción de tabla"""
        lines = text.split('\n')
        
        print("=== DEBUG EXTRACCIÓN DE TABLA V2 ===")
        print(f"Total líneas: {len(lines)}")
        
        # Buscar línea de encabezado exacta
        header_found = False
        for i, line in enumerate(lines):
            line_clean = line.strip()
            if ('Código' in line_clean and 'Descripción' in line_clean and 
                'Cant' in line_clean and 'Valor total' in line_clean):
                print(f"✅ Encabezado encontrado en línea {i}: {line_clean}")
                header_found = True
                
                # Mostrar siguientes 20 líneas
                print("\n--- Líneas después del encabezado ---")
                for j in range(i+1, min(i+21, len(lines))):
                    line_data = lines[j].strip()
                    if line_data:
                        is_procedure = re.match(r'^(\d{5}|00000)', line_data)
                        marker = "📋" if is_procedure else "  "
                        print(f"{marker} Línea {j}: {line_data[:100]}...")
                break
        
        if not header_found:
            print("❌ No se encontró encabezado de tabla")
            print("\n--- Buscando líneas con 'Código' ---")
            for i, line in enumerate(lines):
                if 'Código' in line:
                    print(f"Línea {i}: {line.strip()}")
        
        # Buscar procedimientos en todo el texto
        print(f"\n=== BÚSQUEDA DE PROCEDIMIENTOS ===")
        procedure_pattern = r'(\d{5}|00000)\s+([A-ZÁÉÍÓÚÑ\s\w\/\#\,\.\-\(\)\%]+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)'
        
        matches = list(re.finditer(procedure_pattern, text, re.IGNORECASE | re.MULTILINE))
        print(f"Procedimientos encontrados con regex: {len(matches)}")
        
        for i, match in enumerate(matches[:10]):  # Mostrar primeros 10
            codigo = match.group(1)
            descripcion = match.group(2)[:50]
            cantidad = match.group(3)
            print(f"{i+1}. {codigo} - {descripcion}... (Cant: {cantidad})")
        
        return matches



    def _parse_procedure_from_lines(self, lines: List[str]) -> Dict[str, Any]:
        """Parsea un procedimiento a partir de múltiples líneas"""
        if not lines:
            return None
        
        try:
            # Unir todas las líneas
            full_text = ' '.join(lines)
            
            # Extraer código (primeros 5 dígitos o "00000")
            code_match = re.match(r'^(\d{5}|00000)', full_text)
            if not code_match:
                return None
            
            codigo = code_match.group(1)
            remaining_text = full_text[len(codigo):].strip()
            
            # Buscar valores monetarios en el texto
            # Patrón: cantidad + 3 valores monetarios
            money_pattern = r'(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)'
            money_match = re.search(money_pattern, remaining_text)
            
            if not money_match:
                logger.warning(f"No se encontraron valores monetarios en: {full_text[:100]}...")
                return None
            
            # Extraer valores
            cantidad = float(money_match.group(1))
            valor_total = self._parse_money_value(money_match.group(2))
            valor_pagado = self._parse_money_value(money_match.group(3))
            valor_objetado = self._parse_money_value(money_match.group(4))
            
            # Extraer descripción (entre código y cantidad)
            desc_start = len(codigo)
            desc_end = money_match.start()
            descripcion = remaining_text[desc_start:desc_end].strip()
            
            # Limpiar descripción
            descripcion = self._clean_procedure_description(descripcion)
            
            # Extraer observación (después de los valores monetarios)
            observacion_start = money_match.end()
            observacion = remaining_text[observacion_start:].strip()
            
            # Limpiar observación
            observacion = self._clean_observation(observacion)
            
            procedure = {
                'codigo': codigo,
                'descripcion': descripcion,
                'cantidad': int(cantidad),
                'valor_unitario': valor_total / cantidad if cantidad > 0 else 0,
                'valor_total': valor_total,
                'valor_pagado': valor_pagado,
                'valor_objetado': valor_objetado,
                'observacion': observacion,
                'estado': 'objetado' if valor_objetado > 0 else 'aceptado'
            }
            
            return procedure
            
        except Exception as e:
            logger.error(f"Error parseando procedimiento: {e}")
            logger.error(f"Líneas: {lines}")
            return None






    def _clean_text_for_table_parsing(self, text: str) -> str:
        """Limpia texto específicamente para parsing de tabla"""
        if not text:
            return ""
        
        # Normalizar saltos de línea
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'\r', '\n', text)
        
        # Eliminar caracteres problemáticos pero preservar estructura
        text = re.sub(r'[^\w\s\.\,\:\;\-\$\(\)\/\%\n]', ' ', text)
        
        # Normalizar espacios pero preservar saltos de línea
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Normalizar espacios múltiples en cada línea
            line = re.sub(r'\s+', ' ', line.strip())
            if line:  # Solo agregar líneas no vacías
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)


    def _parse_procedure_match(self, match) -> Dict[str, Any]:
        """Parsea una coincidencia de procedimiento"""
        try:
            groups = match.groups()
            
            # Extraer campos básicos
            codigo = groups[0].strip()
            descripcion = groups[1].strip()
            cantidad = float(groups[2].strip())
            valor_total = self._parse_money_value(groups[3])
            valor_pagado = self._parse_money_value(groups[4])
            valor_objetado = self._parse_money_value(groups[5])
            
            # Observación puede estar en grupo 6 o ser None
            observacion = groups[6].strip() if len(groups) > 6 and groups[6] else ""
            
            # Calcular valor unitario
            valor_unitario = valor_total / cantidad if cantidad > 0 else 0
            
            procedure = {
                'codigo': codigo,
                'descripcion': self._clean_description(descripcion),
                'cantidad': int(cantidad),
                'valor_unitario': valor_unitario,
                'valor_total': valor_total,
                'valor_pagado': valor_pagado,
                'valor_objetado': valor_objetado,
                'observacion': self._clean_observation(observacion),
                'estado': 'objetado' if valor_objetado > 0 else 'aceptado'
            }
            
            return procedure
            
        except Exception as e:
            logger.error(f"Error parseando procedimiento: {e}")
            return None
    

    def _extract_procedures_line_by_line(self, text: str) -> List[Dict[str, Any]]:
        """Método alternativo mejorado: extracción línea por línea"""
        procedures = []
        lines = text.split('\n')
        
        in_table = False
        current_procedure = None
        procedure_buffer = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Detectar inicio de tabla
            if 'Código' in line and 'Descripción' in line and 'Valor total' in line:
                in_table = True
                logger.info(f"Detectado inicio de tabla en línea {i}")
                continue
            
            # Detectar fin de tabla
            if (('Total' in line and '$' in line) or 
                'Valor de Reclamación' in line or 
                'Valor objetado' in line or 
                'Valor Pagado' in line) and in_table:
                
                # Procesar último procedimiento en buffer
                if procedure_buffer:
                    proc = self._process_procedure_buffer(procedure_buffer)
                    if proc:
                        procedures.append(proc)
                    procedure_buffer = []
                
                logger.info(f"Detectado fin de tabla en línea {i}")
                break
            
            if in_table and line:
                # Verificar si es inicio de nuevo procedimiento
                if re.match(r'^(\d{5}|00000)\s+', line):
                    # Procesar procedimiento anterior si existe
                    if procedure_buffer:
                        proc = self._process_procedure_buffer(procedure_buffer)
                        if proc:
                            procedures.append(proc)
                        procedure_buffer = []
                    
                    # Iniciar nuevo procedimiento
                    procedure_buffer = [line]
                    logger.debug(f"Nuevo procedimiento detectado: {line[:50]}...")
                else:
                    # Continuar con el procedimiento actual
                    if procedure_buffer:
                        procedure_buffer.append(line)
        
        # Procesar último procedimiento si existe
        if procedure_buffer:
            proc = self._process_procedure_buffer(procedure_buffer)
            if proc:
                procedures.append(proc)
        
        return procedures


    def _process_procedure_buffer(self, buffer: List[str]) -> Dict[str, Any]:
        """Procesa un buffer de líneas para extraer un procedimiento"""
        if not buffer:
            return None
        
        try:
            # Unir todas las líneas del buffer
            full_text = ' '.join(buffer)
            
            # Patrón para extraer componentes básicos
            basic_pattern = r'^(\d{5}|00000)\s+(.+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)'
            
            match = re.search(basic_pattern, full_text)
            if not match:
                logger.warning(f"No se pudo parsear procedimiento: {full_text[:100]}...")
                return None
            
            codigo = match.group(1)
            descripcion_raw = match.group(2)
            cantidad = float(match.group(3))
            valor_total = self._parse_money_value(match.group(4))
            valor_pagado = self._parse_money_value(match.group(5))
            valor_objetado = self._parse_money_value(match.group(6))
            
            # Limpiar descripción (remover valores monetarios que puedan haberse incluido)
            descripcion = self._clean_procedure_description(descripcion_raw)
            
            # Extraer observación del resto del texto
            observacion_text = full_text[match.end():].strip()
            observacion = self._extract_observation_from_text(observacion_text)
            
            procedure = {
                'codigo': codigo,
                'descripcion': descripcion,
                'cantidad': int(cantidad),
                'valor_unitario': valor_total / cantidad if cantidad > 0 else 0,
                'valor_total': valor_total,
                'valor_pagado': valor_pagado,
                'valor_objetado': valor_objetado,
                'observacion': observacion,
                'estado': 'objetado' if valor_objetado > 0 else 'aceptado'
            }
            
            logger.debug(f"Procedimiento procesado: {codigo} - {descripcion[:30]}...")
            return procedure
            
        except Exception as e:
            logger.error(f"Error procesando buffer: {e}")
            logger.error(f"Buffer content: {buffer}")
            return None


    def _parse_procedure_line(self, line: str) -> Dict[str, Any]:
        """Parsea una línea individual de procedimiento"""
        try:
            # Detectar si la línea tiene estructura de procedimiento
            # Buscar patrón: código + descripción + números
            
            # Patrón para línea completa
            pattern = r'^(\d{4,6}|00000)\s+(.+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)'
            match = re.match(pattern, line)
            
            if match:
                codigo = match.group(1)
                descripcion = match.group(2)
                cantidad = float(match.group(3))
                valor_total = self._parse_money_value(match.group(4))
                valor_pagado = self._parse_money_value(match.group(5))
                valor_objetado = self._parse_money_value(match.group(6))
                
                # Extraer observación del resto de la línea
                observacion_start = match.end()
                observacion = line[observacion_start:].strip()
                
                return {
                    'codigo': codigo,
                    'descripcion': self._clean_description(descripcion),
                    'cantidad': int(cantidad),
                    'valor_unitario': valor_total / cantidad if cantidad > 0 else 0,
                    'valor_total': valor_total,
                    'valor_pagado': valor_pagado,
                    'valor_objetado': valor_objetado,
                    'observacion': self._clean_observation(observacion),
                    'estado': 'objetado' if valor_objetado > 0 else 'aceptado'
                }
            
            return None
            
        except Exception as e:
            logger.debug(f"Error parseando línea: {e}")
            return None


    def _clean_procedure_description(self, description: str) -> str:
        """Limpia descripción de procedimiento"""
        if not description:
            return ""
        
        # Remover números sueltos y patrones problemáticos
        description = re.sub(r'^\d+\s*', '', description)  # Números al inicio
        description = re.sub(r'\s+\d+\s*$', '', description)  # Números al final
        description = re.sub(r'\$[\d,\.]+', '', description)  # Valores monetarios
        
        # Normalizar espacios
        description = re.sub(r'\s+', ' ', description.strip())
        
        # Capitalizar correctamente
        if description:
            description = description.title()
        
        return description


    def debug_table_extraction_detailed(self, pdf_path: str):
        """Debug detallado para extracción de tabla"""
        text = self._extract_text_from_pdf(pdf_path)
        lines = text.split('\n')
        
        print("=== ANÁLISIS DETALLADO DE TABLA ===")
        print(f"Total líneas: {len(lines)}")
        
        # Buscar línea de encabezado
        header_line = -1
        for i, line in enumerate(lines):
            if 'Código' in line and 'Descripción' in line and 'Valor total' in line:
                header_line = i
                print(f"Encabezado encontrado en línea {i}: {line.strip()}")
                break
        
        if header_line == -1:
            print("❌ No se encontró encabezado de tabla")
            return
        
        # Buscar líneas de procedimientos
        procedure_lines = []
        for i in range(header_line + 1, len(lines)):
            line = lines[i].strip()
            
            if not line:
                continue
                
            # Buscar líneas que empiecen con código de procedimiento
            if re.match(r'^(\d{5}|00000)', line):
                procedure_lines.append((i, line))
                print(f"Procedimiento en línea {i}: {line[:80]}...")
            
            # Detectar fin de tabla
            if line.startswith('Total') and '$' in line:
                print(f"Fin de tabla en línea {i}: {line}")
                break
        
        print(f"\n✅ Procedimientos encontrados: {len(procedure_lines)}")
        
        # Intentar parsear cada procedimiento
        for line_num, line in procedure_lines:
            print(f"\n--- Procesando línea {line_num} ---")
            
            # Simular parsing
            try:
                # Buscar código
                code_match = re.match(r'^(\d{5}|00000)', line)
                if code_match:
                    codigo = code_match.group(1)
                    print(f"Código: {codigo}")
                    
                    # Buscar valores monetarios
                    money_pattern = r'(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)'
                    money_match = re.search(money_pattern, line)
                    
                    if money_match:
                        cantidad = money_match.group(1)
                        valor_total = money_match.group(2)
                        valor_pagado = money_match.group(3)
                        valor_objetado = money_match.group(4)
                        
                        print(f"Cantidad: {cantidad}")
                        print(f"Valor total: {valor_total}")
                        print(f"Valor pagado: {valor_pagado}")
                        print(f"Valor objetado: {valor_objetado}")
                        
                        # Extraer descripción
                        desc_start = len(codigo)
                        desc_end = money_match.start()
                        descripcion = line[desc_start:desc_end].strip()
                        print(f"Descripción: {descripcion[:50]}...")
                        
                        print("✅ Parsing exitoso")
                    else:
                        print("❌ No se encontraron valores monetarios")
                else:
                    print("❌ No se encontró código válido")
                    
            except Exception as e:
                print(f"❌ Error: {e}")
        
        return procedure_lines


    def _extract_observation_from_text(self, text: str) -> str:
        """Extrae observación del texto"""
        if not text:
            return ""
        
        # Buscar patrón de observación con código
        obs_pattern = r'(\d{4})\s+>>\s+(.+)'
        match = re.search(obs_pattern, text)
        
        if match:
            return match.group(2).strip()
        
        # Si no hay patrón específico, usar todo el texto
        return text.strip()


    def debug_specific_pdf_extraction(self, pdf_path: str):
        """Debug específico para tu PDF"""
        text = self._extract_text_from_pdf(pdf_path)
        
        print("=== ANÁLISIS ESPECÍFICO DEL PDF ===")
        
        # Buscar líneas que empiecen con códigos conocidos
        lines = text.split('\n')
        procedure_lines = []
        
        for i, line in enumerate(lines):
            if re.match(r'^(00010|37202|00000|39221|39305|21105|39202|21101)\s+', line.strip()):
                procedure_lines.append((i, line.strip()))
        
        print(f"Líneas de procedimientos encontradas: {len(procedure_lines)}")
        
        for line_num, line in procedure_lines:
            print(f"Línea {line_num}: {line[:100]}...")
            
            # Probar parsing
            try:
                buffer = [line]
                proc = self._process_procedure_buffer(buffer)
                if proc:
                    print(f"  ✓ Parseado: {proc['codigo']} - {proc['descripcion'][:30]}...")
                else:
                    print(f"  ✗ No se pudo parsear")
            except Exception as e:
                print(f"  ✗ Error: {e}")
        
        return procedure_lines


    def _enhance_observations(self, procedures: List[Dict], text: str) -> List[Dict]:
        """Mejora las observaciones usando patrones adicionales"""
        try:
            # Buscar observaciones detalladas en el texto
            observation_matches = re.finditer(
                self.observation_continuation_pattern, 
                text, 
                re.IGNORECASE | re.MULTILINE | re.DOTALL
            )
            
            observation_map = {}
            for match in observation_matches:
                code = match.group(1)
                observation = match.group(2).strip()
                observation_map[code] = observation
            
            # Mejorar observaciones de procedimientos
            for procedure in procedures:
                codigo = procedure.get('codigo', '')
                
                # Buscar observación específica para este código
                if codigo in observation_map:
                    procedure['observacion'] = observation_map[codigo]
                
                # Limpiar observación final
                procedure['observacion'] = self._clean_observation(procedure.get('observacion', ''))
            
            return procedures
            
        except Exception as e:
            logger.warning(f"Error mejorando observaciones: {e}")
            return procedures  


    def _clean_description(self, description: str) -> str:
        """Limpia descripción de procedimiento"""
        if not description:
            return ""
        
        # Eliminar espacios extra
        description = re.sub(r'\s+', ' ', description.strip())
        
        # Capitalizar correctamente
        description = description.title()
        
        return description
    


    def _clean_observation(self, observation: str) -> str:
        """Limpia observación de procedimiento"""
        if not observation:
            return ""
        
        # Eliminar códigos de referencia iniciales
        observation = re.sub(r'^\d{4}\s+>>\s+', '', observation)
        
        # Normalizar espacios
        observation = re.sub(r'\s+', ' ', observation.strip())
        
        # Truncar si es muy larga
        if len(observation) > 500:
            observation = observation[:500] + "..."
        
        return observation



    def _setup_soat_patterns(self):
        """Configura patrones específicos para documentos SOAT - VERSIÓN MEJORADA"""
        
        # Patrones para información del paciente en SOAT
        self.patient_patterns = {
            'nombre': [
                r'Víctima\s*:\s*[A-Z]{1,3}\s*-\s*\d+\s*-\s*([A-ZÁÉÍÓÚÑ\s]+?)(?:\n|\r|Número)',
                r'VICTIMA\s*:\s*[A-Z]{1,3}\s*-\s*\d+\s*-\s*([A-ZÁÉÍÓÚÑ\s]+)',
                r'CC\s*-\s*\d+\s*-\s*([A-ZÁÉÍÓÚÑ\s]+?)(?:\n|\r|Número)',
            ],
            'documento': [
                r'Víctima\s*:\s*([A-Z]{1,3})\s*-\s*(\d+)\s*-',
                r'VICTIMA\s*:\s*([A-Z]{1,3})\s*-\s*(\d+)\s*-',
                r'CC\s*-\s*(\d+)\s*-',
                r'TI\s*-\s*(\d+)\s*-',
                r'NIT\s*-\s*(\d+)',
            ],
            'tipo_documento': [
                r'Víctima\s*:\s*([A-Z]{1,3})\s*-',
                r'VICTIMA\s*:\s*([A-Z]{1,3})\s*-',
            ]
        }
        
        # Patrones para información de póliza SOAT
        self.policy_patterns = {
            'numero_liquidacion': [
                r'Liquidación\s+de\s+siniestro\s+No\.\s*([A-Z0-9\-]+)',
                r'LIQ-(\d+)',
                r'GNS-LIQ-(\d+)',
            ],
            'poliza': [
                r'Póliza\s*:\s*(\d+)',
                r'POLIZA\s*:\s*(\d+)',
            ],
            'numero_reclamacion': [
                r'Número\s+de\s+reclamación\s*:\s*([A-Z0-9]+)',
                r'reclamación\s*:\s*([A-Z0-9]+)',
            ],
            'fecha_siniestro': [
                r'Fecha\s+de\s+siniestro\s*:\s*(\d{1,2}/\d{1,2}/\d{4})',
                r'siniestro\s*:\s*(\d{1,2}/\d{1,2}/\d{4})',
            ],
            'fecha_ingreso': [
                r'Fecha\s+de\s+ingreso\s*:\s*(\d{1,2}/\d{1,2}/\d{4})',
                r'ingreso\s*:\s*(\d{1,2}/\d{1,2}/\d{4})',
            ],
            'orden_pago': [
                r'Orden\s+de\s+pago\s*:\s*(\d+)',
                r'pago\s*:\s*(\d+)',
            ]
        }
        
        # Patrones para diagnósticos SOAT
        self.diagnostic_patterns = [
            r'DX\s*:\s*([A-Z]\d{2,3})',
            r'DIAGNOSTICO\s*:\s*([A-Z]\d{2,3})',
            r'CIE\s*:\s*([A-Z]\d{2,3})',
        ]
        
        # PATRONES MEJORADOS PARA PROCEDIMIENTOS
        self.improved_procedure_patterns = [
            # Patrón principal para tabla estructurada
            r'(\d{5}|00000)\s+(.+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+(.+?)(?=\n\d{5}|\n00000|\nTotal|\n[A-Z]{2,}|\Z)',
            
            # Patrón alternativo para procedimientos con descripción larga
            r'(\d{5}|00000)\s+(.+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)(?:\s+(.+?))?(?=\n\d{5}|\n00000|\nTotal|\n[A-Z]{2,}|\Z)',
            
            # Patrón para capturar líneas de tabla completas
            r'^(\d{5}|00000)\s+([A-ZÁÉÍÓÚÑ\s\w\/\#\,\.\-\(\)]+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)(?:\s+(.+?))?$'
        ]
        
        # Patrón para observaciones que continúan en múltiples líneas
        self.observation_continuation_pattern = r'(\d{4})\s+>>\s+(.+?)(?=\n\d{4}\s+>>|\n\d{5}|\nTotal|\Z)'
        
        # Patrones para valores monetarios finales
        self.financial_totals_patterns = {
            'valor_reclamacion': [
                r'Valor\s+de\s+Reclamación\s*:\s*\$?([\d,\.]+)',
                r'Total\s+\$?([\d,\.]+)',
                r'TOTAL\s+RECLAMADO\s*:\s*\$?([\d,\.]+)',
            ],
            'valor_objetado': [
                r'Valor\s+objetado\s*:\s*\$?([\d,\.]+)',
                r'VALOR\s+OBJETADO\s*:\s*\$?([\d,\.]+)',
                r'Total\s+objetado\s*:\s*\$?([\d,\.]+)',
            ],
            'valor_pagado': [
                r'Valor\s+pagado\s*:\s*\$?([\d,\.]+)',
                r'VALOR\s+PAGADO\s*:\s*\$?([\d,\.]+)',
                r'Total\s+pagado\s*:\s*\$?([\d,\.]+)',
                r'Valor\s+Pagado\s*:\s*\$?([\d,\.]+)',
            ],
            'valor_nota_credito': [
                r'Valor\s+Nota\s+Crédito\s*:\s*\$?([\d,\.]+)',
                r'NOTA\s+CREDITO\s*:\s*\$?([\d,\.]+)',
            ],
            'valor_impuestos': [
                r'Valor\s+impuestos\s*:\s*\$?([\d,\.]+)',
                r'IMPUESTOS\s*:\s*\$?([\d,\.]+)',
            ]
        }
        
        # Patrones para IPS
        self.ips_patterns = [
            r'Señores\s*:\s*([A-ZÁÉÍÓÚÑ\s\.]+?)(?:\n|\r)',
            r'([A-ZÁÉÍÓÚÑ\s\.]+?)\s+IPS\s+SAS',
            r'([A-ZÁÉÍÓÚÑ\s\.]+?)\s+Departamento\s+de\s+cartera',
        ]


    
    def extract_from_pdf(self, pdf_path: str, strategy: str = 'hybrid') -> Dict[str, Any]:
        """Método principal actualizado"""
        try:
            logger.info(f"Iniciando extracción SOAT mejorada con estrategia: {strategy}")
            
            # Extraer texto del PDF
            text_content = self._extract_text_from_pdf(pdf_path)
            
            if not text_content.strip():
                logger.warning("No se pudo extraer texto del PDF")
                return self._get_empty_result()
            
            # Usar el extractor mejorado
            result = self._extract_soat_data_improved(text_content)
            
            # Mejorar con IA si está disponible
            if self.openai_api_key and strategy in ['hybrid', 'ai_only']:
                try:
                    ai_result = self._extract_with_openai_enabled(text_content)
                    result = self._merge_results(result, ai_result)
                except Exception as e:
                    logger.warning(f"Error con OpenAI, usando solo OCR: {e}")
            
            # Agregar metadata
            result['metadata'] = {
                'extraction_strategy': strategy,
                'extraction_date': datetime.now().isoformat(),
                'file_path': pdf_path,
                'text_length': len(text_content),
                'success': True,
                'document_type': 'SOAT'
            }
            
            logger.info(f"Extracción completada: {len(result.get('procedures', []))} procedimientos")
            return result
            
        except Exception as e:
            logger.error(f"Error en extracción: {str(e)}")
            return self._get_error_result(str(e))

    

    def _extract_soat_data_improved(self, text: str) -> Dict[str, Any]:
        """Extracción SOAT con tabla mejorada"""
        try:
            result = self._get_empty_result()
            
            # Limpiar texto
            cleaned_text = self._clean_text(text)
            
            # Extraer información del paciente
            result['patient_info'] = self._extract_soat_patient_info(cleaned_text)
            
            # Extraer información de la póliza
            result['policy_info'] = self._extract_soat_policy_info(cleaned_text)
            
            # USAR EXTRACTOR MEJORADO PARA PROCEDIMIENTOS
            result['procedures'] = self._extract_soat_procedures_table_improved(cleaned_text)
            
            # Extraer resumen financiero
            result['financial_summary'] = self._extract_soat_financial_summary(cleaned_text)
            
            # Extraer diagnósticos
            result['diagnostics'] = self._extract_soat_diagnostics(cleaned_text)
            
            # Extraer información de la IPS
            result['ips_info'] = self._extract_soat_ips_info(cleaned_text)
            
            # Calcular estadísticas adicionales
            result['extraction_details'] = self._calculate_extraction_stats(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error en extracción SOAT mejorada: {str(e)}")
            return self._get_empty_result()
    


    def _extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extrae texto de un PDF usando PyMuPDF"""
        try:
            doc = fitz.open(pdf_path)
            text = ""
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                page_text = page.get_text()
                text += page_text + "\n"
            
            doc.close()
            return text
            
        except Exception as e:
            logger.error(f"Error extrayendo texto del PDF: {str(e)}")
            return ""
    
    
    def _extract_soat_data(self, text: str) -> Dict[str, Any]:
        """Extracción específica para documentos SOAT - VERSIÓN MEJORADA"""
        try:
            result = self._get_empty_result()
            
            # Limpiar texto
            cleaned_text = self._clean_text(text)
            
            # Extraer información del paciente
            result['patient_info'] = self._extract_soat_patient_info(cleaned_text)
            
            # Extraer información de la póliza
            result['policy_info'] = self._extract_soat_policy_info(cleaned_text)
            
            # USAR EXTRACTOR MEJORADO PARA PROCEDIMIENTOS
            result['procedures'] = self._extract_soat_procedures_table(cleaned_text)
            
            # Extraer resumen financiero
            result['financial_summary'] = self._extract_soat_financial_summary(cleaned_text)
            
            # Extraer diagnósticos
            result['diagnostics'] = self._extract_soat_diagnostics(cleaned_text)
            
            # Extraer información de la IPS
            result['ips_info'] = self._extract_soat_ips_info(cleaned_text)
            
            # Calcular estadísticas adicionales
            result['extraction_details'] = self._calculate_extraction_stats(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error en extracción SOAT: {str(e)}")
            return self._get_empty_result()



    def _extract_soat_patient_info(self, text: str) -> Dict[str, Any]:
        """Extrae información del paciente específica para SOAT"""
        patient_info = {}
        
        # Extraer nombre del paciente
        for pattern in self.patient_patterns['nombre']:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                nombre = match.group(1).strip()
                # Limpiar el nombre
                nombre = re.sub(r'\s+', ' ', nombre)
                patient_info['nombre'] = nombre.title()
                break
        
        # Extraer documento
        for pattern in self.patient_patterns['documento']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if len(match.groups()) == 2:  # Tipo y número
                    patient_info['tipo_documento'] = match.group(1).strip()
                    patient_info['documento'] = match.group(2).strip()
                else:  # Solo número
                    patient_info['documento'] = match.group(1).strip()
                break
        
        # Extraer tipo de documento si no se extrajo antes
        if 'tipo_documento' not in patient_info:
            for pattern in self.patient_patterns['tipo_documento']:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    patient_info['tipo_documento'] = match.group(1).strip()
                    break
        
        return patient_info
    
    def _extract_soat_policy_info(self, text: str) -> Dict[str, Any]:
        """Extrae información de la póliza específica para SOAT"""
        policy_info = {}
        
        for key, patterns in self.policy_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    policy_info[key] = match.group(1).strip()
                    break
        
        return policy_info
    
    
    def _extract_soat_procedures_table(self, text: str) -> List[Dict[str, Any]]:
        """Extrae procedimientos de la tabla estructurada SOAT - VERSIÓN MEJORADA"""
        procedures = []
        
        logger.info("Iniciando extracción mejorada de tabla SOAT")
        
        # Limpiar texto para mejor parsing
        cleaned_text = self._clean_text_for_table_parsing(text)
        
        # Buscar tabla usando múltiples patrones
        for pattern_idx, pattern in enumerate(self.improved_procedure_patterns):
            logger.info(f"Probando patrón {pattern_idx + 1}")
            matches = list(re.finditer(pattern, cleaned_text, re.IGNORECASE | re.MULTILINE | re.DOTALL))
            
            if matches:
                logger.info(f"Encontradas {len(matches)} coincidencias con patrón {pattern_idx + 1}")
                
                for match in matches:
                    try:
                        procedure = self._parse_procedure_match(match)
                        if procedure:
                            procedures.append(procedure)
                            logger.debug(f"Procedimiento extraído: {procedure['codigo']} - {procedure['descripcion'][:50]}...")
                    except Exception as e:
                        logger.warning(f"Error procesando coincidencia: {e}")
                        continue
                
                # Si encontramos procedimientos, no probar más patrones
                if procedures:
                    break
        
        # Si no encontramos procedimientos, intentar método línea por línea
        if not procedures:
            logger.info("Intentando extracción línea por línea")
            procedures = self._extract_procedures_line_by_line(cleaned_text)
        
        # Mejorar observaciones con patrones adicionales
        procedures = self._enhance_observations(procedures, cleaned_text)
        
        logger.info(f"Extracción completada: {len(procedures)} procedimientos")
        return procedures


    def _extract_procedures_alternative_pattern(self, text: str) -> List[Dict[str, Any]]:
        """Patrón alternativo para extraer procedimientos"""
        procedures = []
        
        # Patrón más simple línea por línea
        lines = text.split('\n')
        in_table = False
        
        for line in lines:
            line = line.strip()
            
            # Detectar inicio de tabla
            if 'Código' in line and 'Descripción' in line and 'Valor total' in line:
                in_table = True
                continue
            
            # Detectar fin de tabla
            if 'Total' in line and '$' in line and in_table:
                break
            
            if in_table and line:
                # Intentar extraer datos de la línea
                parts = re.split(r'\s+', line)
                if len(parts) >= 6:
                    try:
                        codigo = parts[0]
                        # Buscar valores monetarios en la línea
                        money_values = re.findall(r'\$?([\d,\.]+)', line)
                        
                        if len(money_values) >= 3:
                            valor_total = self._parse_money_value(money_values[-3])
                            valor_pagado = self._parse_money_value(money_values[-2])
                            valor_objetado = self._parse_money_value(money_values[-1])
                            
                            # Extraer descripción (entre código y primer valor)
                            desc_start = line.find(codigo) + len(codigo)
                            desc_end = line.find(money_values[0])
                            descripcion = line[desc_start:desc_end].strip()
                            
                            procedure = {
                                'codigo': codigo,
                                'descripcion': descripcion,
                                'cantidad': 1,
                                'valor_unitario': valor_total,
                                'valor_total': valor_total,
                                'valor_pagado': valor_pagado,
                                'valor_objetado': valor_objetado,
                                'observacion': "",
                                'estado': 'objetado' if valor_objetado > 0 else 'aceptado'
                            }
                            
                            procedures.append(procedure)
                    
                    except (ValueError, IndexError):
                        continue
        
        return procedures
    
    def _extract_soat_financial_summary(self, text: str) -> Dict[str, Any]:
        """Extrae resumen financiero específico para SOAT"""
        financial = {}
        
        for key, patterns in self.financial_totals_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    financial[key] = self._parse_money_value(match.group(1))
                    break
        
        # Calcular valores derivados
        if 'valor_reclamacion' in financial and 'valor_objetado' in financial:
            financial['total_aceptado'] = financial['valor_reclamacion'] - financial['valor_objetado']
            
            if financial['valor_reclamacion'] > 0:
                financial['porcentaje_objetado'] = (financial['valor_objetado'] / financial['valor_reclamacion']) * 100
            else:
                financial['porcentaje_objetado'] = 0.0
        
        # Mapear a nombres estándar
        if 'valor_reclamacion' in financial:
            financial['total_reclamado'] = financial['valor_reclamacion']
        if 'valor_objetado' in financial:
            financial['total_objetado'] = financial['valor_objetado']
        if 'valor_pagado' in financial:
            financial['total_pagado'] = financial['valor_pagado']
        
        return financial
    
    def _extract_soat_diagnostics(self, text: str) -> List[Dict[str, Any]]:
        """Extrae diagnósticos específicos para SOAT"""
        diagnostics = []
        
        for pattern in self.diagnostic_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            
            for match in matches:
                codigo = match.strip().upper()
                
                diagnostic = {
                    'codigo': codigo,
                    'descripcion': self._get_cie10_description(codigo),
                    'tipo': 'principal' if len(diagnostics) == 0 else 'secundario'
                }
                
                diagnostics.append(diagnostic)
        
        return diagnostics
    
    def _extract_soat_ips_info(self, text: str) -> Dict[str, Any]:
        """Extrae información de la IPS específica para SOAT"""
        ips_info = {}
        
        for pattern in self.ips_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                nombre = match.group(1).strip()
                # Limpiar nombre de la IPS
                nombre = re.sub(r'\s+', ' ', nombre)
                ips_info['nombre'] = nombre.title()
                break
        
        # Buscar NIT
        nit_pattern = r'NIT\s*-?\s*(\d{9,12})'
        match = re.search(nit_pattern, text, re.IGNORECASE)
        if match:
            ips_info['nit'] = match.group(1).strip()
        
        return ips_info
    
    def _get_cie10_description(self, codigo: str) -> str:
        """Obtiene descripción básica de códigos CIE-10 comunes"""
        cie10_descriptions = {
            'S836': 'Esguince y distensión de otras partes y las no especificadas de la rodilla',
            'S83': 'Luxación, esguince y distensión de articulaciones y ligamentos de la rodilla',
            'M25': 'Otros trastornos articulares no clasificados en otra parte',
            'S72': 'Fractura del fémur',
            'S82': 'Fractura de la pierna, incluyendo el tobillo',
        }
        
        # Buscar coincidencia exacta o parcial
        for key, desc in cie10_descriptions.items():
            if codigo.startswith(key):
                return desc
        
        return ""
    
    def _parse_money_value(self, value_str: str) -> float:
        """Convierte string de valor monetario a float"""
        if not value_str:
            return 0.0
        
        try:
            # Remover símbolos y espacios
            clean_value = re.sub(r'[\$\s]', '', str(value_str))
            
            # Reemplazar comas por puntos para decimales
            if ',' in clean_value and clean_value.count(',') == 1:
                # Si hay solo una coma, probablemente es decimal
                parts = clean_value.split(',')
                if len(parts[1]) <= 2:  # Máximo 2 decimales
                    clean_value = clean_value.replace(',', '.')
                else:
                    # Es separador de miles
                    clean_value = clean_value.replace(',', '')
            else:
                # Múltiples comas o ninguna, eliminar todas
                clean_value = clean_value.replace(',', '')
            
            return float(clean_value)
        except (ValueError, TypeError):
            return 0.0
    
    def _clean_text(self, text: str) -> str:
        """Limpia y normaliza el texto"""
        if not text:
            return ""
        
        # Normalizar espacios y saltos de línea
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'\r', '\n', text)
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def _calculate_extraction_stats(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Calcula estadísticas de la extracción"""
        procedures = result.get('procedures', [])
        financial = result.get('financial_summary', {})
        
        stats = {
            'total_procedimientos': len(procedures),
            'procedimientos_objetados': len([p for p in procedures if p.get('valor_objetado', 0) > 0]),
            'campos_extraidos': self._count_extracted_fields(result),
            'calidad_extraccion': self._calculate_extraction_quality(result)
        }
        
        if financial:
            stats.update({
                'total_reclamado': financial.get('total_reclamado', 0),
                'total_objetado': financial.get('total_objetado', 0),
                'total_aceptado': financial.get('total_aceptado', 0)
            })
        
        return stats
    
    def _count_extracted_fields(self, result: Dict[str, Any]) -> int:
        """Cuenta campos exitosamente extraídos"""
        count = 0
        
        # Contar campos de paciente
        patient_info = result.get('patient_info', {})
        count += len([v for v in patient_info.values() if v])
        
        # Contar campos de póliza
        policy_info = result.get('policy_info', {})
        count += len([v for v in policy_info.values() if v])
        
        # Contar campos financieros
        financial = result.get('financial_summary', {})
        count += len([v for v in financial.values() if v])
        
        # Contar procedimientos y diagnósticos
        count += len(result.get('procedures', []))
        count += len(result.get('diagnostics', []))
        
        return count
    
    def _calculate_extraction_quality(self, result: Dict[str, Any]) -> str:
        """Calcula la calidad de la extracción"""
        total_fields = self._count_extracted_fields(result)
        
        # Para SOAT, esperamos al menos: paciente (3), póliza (5), procedimientos (5+), diagnósticos (1), IPS (1)
        if total_fields >= 20:
            return 'excelente'
        elif total_fields >= 15:
            return 'buena'
        elif total_fields >= 10:
            return 'regular'
        else:
            return 'baja'
    
    def _extract_with_openai_enabled(self, text: str) -> Dict[str, Any]:
        """Extrae información usando OpenAI GPT - Versión simplificada sin proxies"""
        try:
            import openai
            
            # Configurar cliente OpenAI de forma simple
            client = openai.OpenAI(
                api_key=self.openai_api_key
                # Removemos cualquier argumento problemático como proxies
            )
            
            # Crear prompt específico para SOAT
            prompt = self._build_soat_openai_prompt(text)
            
            # Llamar a OpenAI
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Eres un experto en análisis de documentos médicos colombianos, especialmente glosas SOAT. Extrae información de manera precisa y estructurada."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            ai_response = response.choices[0].message.content.strip()
            
            # Procesar respuesta JSON
            try:
                import json
                
                # Limpiar respuesta si tiene texto adicional
                if ai_response.startswith('```json'):
                    ai_response = ai_response.replace('```json', '').replace('```', '')
                elif ai_response.startswith('```'):
                    ai_response = ai_response.replace('```', '')
                
                ai_data = json.loads(ai_response)
                logger.info("OpenAI: Datos extraídos exitosamente")
                return ai_data
                
            except json.JSONDecodeError as e:
                logger.warning(f"OpenAI: Error parseando JSON: {e}")
                logger.warning(f"OpenAI response: {ai_response[:500]}...")
                return self._get_empty_result()
                
        except ImportError:
            logger.warning("OpenAI no está instalado")
            return self._get_empty_result()
        except Exception as e:
            logger.error(f"Error con OpenAI: {str(e)}")
            # Por ahora, retornar resultado vacío para que no afecte la extracción OCR
            return self._get_empty_result()


    def _build_soat_openai_prompt(self, text: str) -> str:
        """Construye prompt específico para documentos SOAT"""
        
        # Limitar texto para no exceder límites de tokens
        text_sample = text[:4000] if len(text) > 4000 else text
        
        prompt = f"""
    Analiza este documento de liquidación SOAT colombiano y extrae la información en formato JSON exacto.

    TEXTO DEL DOCUMENTO:
    {text_sample}

    Extrae ÚNICAMENTE la siguiente información en formato JSON válido:

    {{
    "patient_info": {{
        "nombre": "nombre completo del paciente/víctima",
        "documento": "número de documento",
        "tipo_documento": "tipo (CC, TI, etc.)"
    }},
    "policy_info": {{
        "numero_liquidacion": "número de liquidación completo",
        "poliza": "número de póliza",
        "numero_reclamacion": "número de reclamación",
        "fecha_siniestro": "fecha del siniestro",
        "fecha_ingreso": "fecha de ingreso",
        "orden_pago": "orden de pago"
    }},
    "procedures": [
        {{
        "codigo": "código del procedimiento",
        "descripcion": "descripción del procedimiento", 
        "cantidad": 1,
        "valor_total": 0,
        "valor_pagado": 0,
        "valor_objetado": 0,
        "observacion": "observación si existe"
        }}
    ],
    "financial_summary": {{
        "total_reclamado": 0,
        "total_objetado": 0,
        "total_pagado": 0,
        "valor_nota_credito": 0,
        "valor_impuestos": 0
    }},
    "diagnostics": [
        {{
        "codigo": "código CIE-10",
        "descripcion": "descripción del diagnóstico"
        }}
    ],
    "ips_info": {{
        "nombre": "nombre de la IPS",
        "nit": "NIT de la IPS"
    }}
    }}

    INSTRUCCIONES IMPORTANTES:
    1. Responde SOLO con el JSON, sin texto adicional
    2. Usa valores numéricos sin símbolos $ ni comas para los montos
    3. Si no encuentras un dato, usa "" para strings y 0 para números
    4. Extrae TODOS los procedimientos de la tabla
    5. Mantén las observaciones completas para cada procedimiento
    6. Identifica correctamente códigos CUPS y CIE-10

    JSON:"""
        
        return prompt


    def _merge_results(self, ocr_result: Dict[str, Any], ai_result: Dict[str, Any]) -> Dict[str, Any]:
        """Combina resultados de OCR y IA"""
        # Por ahora solo retorna OCR
        return ocr_result
    
    def _extract_hybrid(self, text: str) -> Dict[str, Any]:
        """Estrategia híbrida"""
        return self._extract_soat_data(text)
    
    def _extract_ai_only(self, text: str) -> Dict[str, Any]:
        """Estrategia solo IA"""
        if self.openai_api_key:
            return self._extract_with_openai_enabled(text)
        return self._extract_soat_data(text)
    
    def _extract_ocr_only(self, text: str) -> Dict[str, Any]:
        """Estrategia solo OCR"""
        return self._extract_soat_data(text)
    
    def _get_empty_result(self) -> Dict[str, Any]:
        """Retorna estructura vacía del resultado"""
        return {
            'patient_info': {},
            'policy_info': {},
            'procedures': [],
            'financial_summary': {},
            'diagnostics': [],
            'ips_info': {},
            'extraction_details': {}
        }
    
    def _get_error_result(self, error_message: str) -> Dict[str, Any]:
        """Retorna resultado de error"""
        result = self._get_empty_result()
        result['error'] = error_message
        result['success'] = False
        result['metadata'] = {
            'extraction_date': datetime.now().isoformat(),
            'success': False
        }
        return result
    

    def debug_table_extraction(self, text: str) -> Dict[str, Any]:
        """Método de debugging para analizar la extracción de tabla"""
        debug_info = {
            'original_text_length': len(text),
            'cleaned_text_length': 0,
            'patterns_tried': [],
            'matches_found': [],
            'procedures_extracted': [],
            'errors': []
        }
        
        try:
            # Limpiar texto
            cleaned_text = self._clean_text_for_table_parsing(text)
            debug_info['cleaned_text_length'] = len(cleaned_text)
            
            # Probar cada patrón
            for pattern_idx, pattern in enumerate(self.improved_procedure_patterns):
                pattern_info = {
                    'pattern_index': pattern_idx,
                    'pattern': pattern,
                    'matches': 0,
                    'successful_extractions': 0
                }
                
                try:
                    matches = list(re.finditer(pattern, cleaned_text, re.IGNORECASE | re.MULTILINE | re.DOTALL))
                    pattern_info['matches'] = len(matches)
                    
                    for match in matches:
                        try:
                            procedure = self._parse_procedure_match(match)
                            if procedure:
                                pattern_info['successful_extractions'] += 1
                                debug_info['procedures_extracted'].append(procedure)
                        except Exception as e:
                            debug_info['errors'].append(f"Error parsing match: {str(e)}")
                    
                except Exception as e:
                    debug_info['errors'].append(f"Error with pattern {pattern_idx}: {str(e)}")
                
                debug_info['patterns_tried'].append(pattern_info)
            
            return debug_info
            
        except Exception as e:
            debug_info['errors'].append(f"General error: {str(e)}")
            return debug_info

    def debug_procedure_validation(self, text: str):
        """Debug específico para validación de procedimientos"""
        print("=== DEBUG VALIDACIÓN DE PROCEDIMIENTOS ===")
        
        # Usar el mismo patrón que el método principal
        procedure_pattern = r'(\d{5}|00000)\s+([A-ZÁÉÍÓÚÑ\s\w\/\#\,\.\-\(\)\%]+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)(?:\s+(.+?))?(?=\n\d{5}|\n00000|\nTotal|\nValor de|\Z)'
        
        matches = re.finditer(procedure_pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        valid_procedures = []
        invalid_procedures = []
        
        for i, match in enumerate(matches, 1):
            try:
                codigo = match.group(1).strip()
                descripcion_raw = match.group(2).strip()
                cantidad = float(match.group(3).strip())
                valor_total = self._parse_money_value(match.group(4))
                valor_pagado = self._parse_money_value(match.group(5))
                valor_objetado = self._parse_money_value(match.group(6))
                observacion_raw = match.group(7).strip() if match.group(7) else ""
                
                # Limpiar descripción
                descripcion = self._clean_procedure_description_v2(descripcion_raw)
                
                print(f"\n--- PROCEDIMIENTO {i} ---")
                print(f"Código: {codigo}")
                print(f"Descripción raw: {descripcion_raw[:80]}...")
                print(f"Descripción limpia: {descripcion}")
                print(f"Cantidad: {cantidad}")
                print(f"Valor total: {valor_total}")
                print(f"Valor pagado: {valor_pagado}")
                print(f"Valor objetado: {valor_objetado}")
                
                # Probar validación paso a paso
                print("--- VALIDACIÓN ---")
                
                # Validar código
                code_valid = re.match(r'^(\d{5}|00000)$', codigo)
                print(f"✓ Código válido: {bool(code_valid)} ({codigo})")
                
                # Validar descripción
                desc_valid = descripcion and len(descripcion.strip()) >= 3
                print(f"✓ Descripción válida: {desc_valid} (len: {len(descripcion)})")
                
                # Validar patrones inválidos
                invalid_patterns = [
                    'LIQ-', 'Pagina', 'Liquidación de siniestro', 'Fecha de Pago',
                    'Víctima :', 'Número de reclamación', 'Póliza :', 'DX :'
                ]
                
                has_invalid_pattern = any(pattern in descripcion for pattern in invalid_patterns)
                print(f"✓ Sin patrones inválidos: {not has_invalid_pattern}")
                if has_invalid_pattern:
                    for pattern in invalid_patterns:
                        if pattern in descripcion:
                            print(f"  ❌ Patrón encontrado: '{pattern}'")
                
                # Validar valor
                value_valid = valor_total > 0 and valor_total <= 10000000
                print(f"✓ Valor válido: {value_valid} (${valor_total:,.0f})")
                
                # Resultado final de validación
                is_valid = self._is_valid_procedure(codigo, descripcion, valor_total)
                print(f"🔍 RESULTADO: {'✅ VÁLIDO' if is_valid else '❌ INVÁLIDO'}")
                
                if is_valid:
                    valid_procedures.append({
                        'codigo': codigo,
                        'descripcion': descripcion,
                        'valor_total': valor_total
                    })
                else:
                    invalid_procedures.append({
                        'codigo': codigo,
                        'descripcion': descripcion,
                        'valor_total': valor_total,
                        'razon': 'Falló validación _is_valid_procedure'
                    })
                    
            except Exception as e:
                print(f"❌ ERROR procesando procedimiento {i}: {e}")
                invalid_procedures.append({
                    'codigo': codigo if 'codigo' in locals() else 'N/A',
                    'razon': f'Error: {e}'
                })
        
        print(f"\n=== RESUMEN ===")
        print(f"✅ Procedimientos válidos: {len(valid_procedures)}")
        for proc in valid_procedures:
            print(f"  - {proc['codigo']}: {proc['descripcion'][:50]}...")
        
        print(f"\n❌ Procedimientos inválidos: {len(invalid_procedures)}")
        for proc in invalid_procedures:
            print(f"  - {proc['codigo']}: {proc.get('descripcion', 'N/A')[:50]}... ({proc['razon']})")
        
        return valid_procedures, invalid_procedures


    def _is_valid_procedure_v2(self, codigo: str, descripcion: str, valor_total: float) -> bool:
        """Validación mejorada de procedimientos"""
        
        # 1. Validar código
        if not re.match(r'^(\d{5}|00000)$', codigo):
            return False
        
        # 2. Validar descripción básica
        if not descripcion or len(descripcion.strip()) < 3:
            return False
        
        # 3. Validar patrones específicos que NO deben estar en descripción
        invalid_patterns = [
            'Pagina', 'LIQ-', 'Liquidación de siniestro', 
            'Fecha de Pago', 'Víctima :', 'Número de reclamación', 
            'Póliza :', 'DX :', 'CORRESPONDE ESTA ESPECIALIDAD'
        ]
        
        for pattern in invalid_patterns:
            if pattern in descripcion:
                return False
        
        # 4. Validar valor monetario
        if valor_total <= 0 or valor_total > 10000000:
            return False
        
        # 5. Validaciones adicionales específicas
        # No debe ser solo números
        if descripcion.strip().isdigit():
            return False
        
        # No debe ser muy corta después de limpiar
        desc_clean = re.sub(r'[^\w\s]', '', descripcion).strip()
        if len(desc_clean) < 5:
            return False
        
        return True
    
    def _extract_procedures_from_full_text_v2(self, text: str) -> List[Dict[str, Any]]:
        """Extrae procedimientos buscando directamente en todo el texto - VERSIÓN CORREGIDA"""
        procedures = []
        
        # Buscar todos los procedimientos que empiecen con códigos válidos
        procedure_pattern = r'(\d{5}|00000)\s+([A-ZÁÉÍÓÚÑ\s\w\/\#\,\.\-\(\)\%]+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)(?:\s+(.+?))?(?=\n\d{5}|\n00000|\nTotal|\nValor de|\Z)'
        
        matches = re.finditer(procedure_pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        for match in matches:
            try:
                codigo = match.group(1).strip()
                descripcion_raw = match.group(2).strip()
                cantidad = float(match.group(3).strip())
                valor_total = self._parse_money_value(match.group(4))
                valor_pagado = self._parse_money_value(match.group(5))
                valor_objetado = self._parse_money_value(match.group(6))
                observacion_raw = match.group(7).strip() if match.group(7) else ""
                
                # Limpiar descripción
                descripcion = self._clean_procedure_description_v2(descripcion_raw)
                
                # Limpiar observación
                observacion = self._clean_observation_v2(observacion_raw)
                
                # USAR VALIDACIÓN MEJORADA
                if self._is_valid_procedure_v2(codigo, descripcion, valor_total):
                    procedure = {
                        'codigo': codigo,
                        'descripcion': descripcion,
                        'cantidad': int(cantidad),
                        'valor_unitario': valor_total / cantidad if cantidad > 0 else 0,
                        'valor_total': valor_total,
                        'valor_pagado': valor_pagado,
                        'valor_objetado': valor_objetado,
                        'observacion': observacion,
                        'estado': 'objetado' if valor_objetado > 0 else 'aceptado'
                    }
                    
                    procedures.append(procedure)
                    logger.info(f"Procedimiento válido extraído: {codigo} - {descripcion[:50]}...")
                else:
                    logger.warning(f"Procedimiento inválido descartado: {codigo} - {descripcion[:30]}...")
                    
            except Exception as e:
                logger.error(f"Error procesando procedimiento: {e}")
                continue
        
        logger.info(f"Total procedimientos válidos extraídos: {len(procedures)}")
        return procedures