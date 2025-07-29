# apps/extractor/openai_paginated_processor.py
"""
Versión mejorada del procesador paginado para OpenAI
Soluciona problemas de extracción en documentos grandes
"""

import logging
import json
import time
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class OpenAIPaginatedProcessorV2:
    """
    Versión mejorada del procesador paginado que maneja mejor la extracción
    """
    
    def __init__(self, openai_api_key: str, chunk_size: int = 10, delay_between_calls: float = 2.0):
        self.openai_api_key = openai_api_key
        self.chunk_size = chunk_size
        self.delay = delay_between_calls
        self.total_api_calls = 0
        self.total_tokens_used = 0
        
    def should_use_pagination(self, text: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Determina si un documento requiere procesamiento paginado
        """
        analysis = {
            'text_length': len(text),
            'estimated_procedures': 0,
            'has_procedure_table': False,
            'complexity_score': 0
        }
        
        # Contar procedimientos de forma más precisa
        # Buscar líneas que contengan patrones de código + valores monetarios
        procedure_pattern = r'^\s*\d{4,}[\s\-\w]*.*\$[\d,]+.*\$[\d,]+.*\$[\d,]+'
        matches = re.findall(procedure_pattern, text, re.MULTILINE)
        analysis['estimated_procedures'] = len(matches)
        
        # Verificar longitud
        if len(text) > 8000:
            analysis['complexity_score'] += 2
            
        # Verificar número de procedimientos
        if analysis['estimated_procedures'] > 25:
            analysis['complexity_score'] += 3
        elif analysis['estimated_procedures'] > 15:
            analysis['complexity_score'] += 1
            
        # Buscar indicadores de tabla de procedimientos
        if re.search(r'Código\s+Descripción\s+Cant\s+Valor', text, re.IGNORECASE):
            analysis['has_procedure_table'] = True
            analysis['complexity_score'] += 1
            
        should_paginate = (
            analysis['complexity_score'] >= 3 or 
            analysis['estimated_procedures'] > 20 or
            len(text) > 10000
        )
        
        logger.info(f"📊 Análisis de documento V2:")
        logger.info(f"   - Longitud: {analysis['text_length']:,} caracteres")
        logger.info(f"   - Procedimientos detectados: {analysis['estimated_procedures']}")
        logger.info(f"   - Score: {analysis['complexity_score']}")
        logger.info(f"   - ¿Paginar?: {'SÍ' if should_paginate else 'NO'}")
        
        return should_paginate, analysis
    
    def extract_with_pagination(self, text: str, fallback_method=None) -> Dict[str, Any]:
        """
        Extrae datos usando procesamiento paginado mejorado
        """
        logger.info("🔄 INICIANDO PROCESAMIENTO PAGINADO V2")
        start_time = time.time()
        
        try:
            # Paso 1: Extraer tabla completa de procedimientos
            logger.info("📋 PASO 1: Extrayendo tabla de procedimientos...")
            procedures_table = self._extract_full_procedures_table(text)
            
            if not procedures_table:
                logger.warning("⚠️ No se encontró tabla de procedimientos")
                if fallback_method:
                    return fallback_method(text)
                return self._get_empty_result()
            
            # Paso 2: Extraer información general del encabezado
            logger.info("👤 PASO 2: Extrayendo información del paciente y póliza...")
            general_info = self._extract_header_info(text)
            
            # Paso 3: Procesar la tabla de procedimientos completa
            logger.info("⚙️ PASO 3: Procesando tabla de procedimientos...")
            all_procedures = self._process_procedures_table(procedures_table)
            
            # Paso 4: Extraer totales del final del documento
            logger.info("💰 PASO 4: Extrayendo totales financieros...")
            financial_summary = self._extract_financial_totals(text)
            
            # Paso 5: Combinar todo
            final_result = {
                **general_info,
                "procedures": all_procedures,
                "financial_summary": financial_summary,
                "processing_metadata": {
                    "method": "paginated_v2",
                    "total_procedures": len(all_procedures),
                    "processing_time": time.time() - start_time,
                    "api_calls": self.total_api_calls
                }
            }
            
            logger.info(f"✅ PROCESAMIENTO COMPLETADO: {len(all_procedures)} procedimientos")
            return final_result
            
        except Exception as e:
            logger.error(f"❌ Error en procesamiento paginado V2: {str(e)}")
            if fallback_method:
                return fallback_method(text)
            return self._get_empty_result()
    
    def _extract_full_procedures_table(self, text: str) -> str:
        """
        Extrae la tabla completa de procedimientos del documento
        """
        # Buscar inicio de tabla
        start_patterns = [
            r'Código\s+Descripción\s+Cant\s+Valor\s+total\s+Valor\s+pagado\s+Valor\s*objetado',
            r'Código.*Descripción.*Cant.*Valor',
            r'CÓDIGO.*DESCRIPCIÓN.*CANTIDAD',
            r'^\d{4,}\s+[A-ZÁÉÍÓÚÑ\s]+\s+\d+\.\d+\s+\$'
        ]
        
        start_pos = -1
        for pattern in start_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                start_pos = match.start()
                logger.info(f"📍 Tabla encontrada con patrón: {pattern[:30]}...")
                break
        
        if start_pos == -1:
            # Buscar por el primer procedimiento
            proc_match = re.search(r'^\s*\d{4,}[\s\-]*[A-ZÁÉÍÓÚÑ\s]+.*\$', text, re.MULTILINE)
            if proc_match:
                start_pos = proc_match.start()
                logger.info("📍 Tabla encontrada por primer procedimiento")
        
        if start_pos == -1:
            return ""
        
        # Buscar fin de tabla
        end_patterns = [
            r'Valor\s+de\s+Reclamación\s*:\s*\$',
            r'TOTAL\s+RECLAMADO',
            r'Total\s+general',
            r'RESUMEN\s+FINANCIERO',
            r'^\s*\$[\d,]+\s*\$[\d,]+\s*\$[\d,]+\s*$'  # Línea de totales
        ]
        
        end_pos = len(text)
        for pattern in end_patterns:
            match = re.search(pattern, text[start_pos:], re.IGNORECASE | re.MULTILINE)
            if match:
                end_pos = start_pos + match.start()
                break
        
        table_text = text[start_pos:end_pos]
        logger.info(f"📊 Tabla extraída: {len(table_text)} caracteres")
        
        return table_text
    
    def _extract_header_info(self, text: str) -> Dict[str, Any]:
        """
        Extrae información del encabezado del documento
        """
        header_text = text[:2000]  # Primeros 2000 caracteres
        
        result = {
            "patient_info": {},
            "policy_info": {}
        }
        
        # Extraer información del paciente
        patient_patterns = {
            'nombre': [
                r'Víctima\s*:\s*[A-Z]{1,3}\s*-\s*\d+\s*-\s*([A-ZÁÉÍÓÚÑ\s]+?)(?:\s*Número|\s*$)',
                r'VICTIMA\s*:\s*[A-Z]{1,3}\s*-\s*\d+\s*-\s*([A-ZÁÉÍÓÚÑ\s]+)',
                r'Paciente\s*:\s*([A-ZÁÉÍÓÚÑ\s]+?)(?:\s*\n|\s*$)'
            ],
            'documento': [
                r'Víctima\s*:\s*[A-Z]{1,3}\s*-\s*(\d+)\s*-',
                r'CC\s*-\s*(\d+)',
                r'TI\s*-\s*(\d+)'
            ],
            'tipo_documento': [
                r'Víctima\s*:\s*([A-Z]{1,3})\s*-',
                r'(CC|TI|CE)\s*-\s*\d+'
            ]
        }
        
        for field, patterns in patient_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, header_text, re.IGNORECASE)
                if match:
                    result["patient_info"][field] = match.group(1).strip()
                    break
        
        # Extraer información de póliza
        policy_patterns = {
            'numero_liquidacion': [
                r'Liquidación\s+de\s+siniestro\s+No\.\s*([A-Z0-9\-]+)',
                r'LIQ-(\d+)',
                r'No\.\s*(\d{2}-\d{4}-\d+)'
            ],
            'poliza': [
                r'Póliza\s*:\s*(\d+)',
                r'POLIZA\s*:\s*(\d+)'
            ],
            'numero_reclamacion': [
                r'Número\s+de\s+reclamación\s*:\s*([A-Z0-9]+)',
                r'reclamación\s*:\s*([A-Z0-9]+)'
            ],
            'fecha_siniestro': [
                r'Fecha\s+de\s+siniestro\s*:\s*(\d{1,2}/\d{1,2}/\d{4})',
                r'siniestro\s*:\s*(\d{1,2}/\d{1,2}/\d{4})'
            ]
        }
        
        for field, patterns in policy_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, header_text, re.IGNORECASE)
                if match:
                    result["policy_info"][field] = match.group(1).strip()
                    break
        
        logger.info(f"✅ Información extraída: Paciente={result['patient_info']}, Póliza={result['policy_info']}")
        return result
    
    def _process_procedures_table(self, table_text: str) -> List[Dict[str, Any]]:
        """
        Procesa la tabla de procedimientos usando OpenAI
        """
        try:
            import openai
            client = openai.OpenAI(api_key=self.openai_api_key)
            
            # Si la tabla es pequeña, procesarla completa
            if len(table_text) < 3000:
                return self._extract_procedures_from_text(table_text, client)
            
            # Para tablas grandes, dividir en chunks inteligentes
            chunks = self._split_table_intelligently(table_text)
            all_procedures = []
            
            for i, chunk in enumerate(chunks, 1):
                logger.info(f"   Procesando chunk {i}/{len(chunks)}...")
                procedures = self._extract_procedures_from_text(chunk, client)
                all_procedures.extend(procedures)
                
                if i < len(chunks):
                    time.sleep(self.delay)
            
            return all_procedures
            
        except Exception as e:
            logger.error(f"❌ Error procesando tabla: {str(e)}")
            return []
    
    def _extract_procedures_from_text(self, text: str, client) -> List[Dict[str, Any]]:
        """
        Extrae procedimientos de un texto usando OpenAI
        """
        prompt = f"""
Extrae TODOS los procedimientos médicos de esta tabla SOAT colombiana.

TABLA DE PROCEDIMIENTOS:
{text}

INSTRUCCIONES:
1. Identifica CADA línea que contenga un procedimiento médico
2. Los procedimientos tienen: código, descripción, cantidad, valor total, valor pagado, valor objetado
3. Si no hay código visible, usa "00000"
4. Las observaciones pueden estar después del procedimiento (empiezan con números como "2033 >>")
5. NO incluyas totales o subtotales

Responde SOLO con JSON válido:
{{
    "procedures": [
        {{
            "codigo": "13582",
            "descripcion": "OSTEOSINTESIS HUESO DE PIE",
            "cantidad": 1,
            "valor_total": 432000,
            "valor_pagado": 431900,
            "valor_objetado": 100,
            "observacion": "2033 >> Los cargos por honorarios...",
            "estado": "objetado"
        }}
    ]
}}"""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un experto en procesamiento de documentos médicos SOAT. Extrae información con precisión."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=3000,
                temperature=0.1
            )
            
            self.total_api_calls += 1
            content = response.choices[0].message.content.strip()
            
            # Limpiar respuesta
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            
            result = json.loads(content)
            procedures = result.get('procedures', [])
            
            logger.info(f"   ✅ Extraídos {len(procedures)} procedimientos")
            return procedures
            
        except Exception as e:
            logger.error(f"   ❌ Error: {str(e)}")
            return []
    
    def _split_table_intelligently(self, table_text: str) -> List[str]:
        """
        Divide la tabla en chunks inteligentes preservando procedimientos completos
        """
        lines = table_text.split('\n')
        chunks = []
        current_chunk = []
        current_size = 0
        max_chunk_size = 2000  # Caracteres por chunk
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Si agregar esta línea excede el tamaño, guardar chunk actual
            if current_size + len(line) > max_chunk_size and current_chunk:
                # Asegurar que incluimos observaciones si las hay
                while i + 1 < len(lines) and lines[i + 1].strip().startswith(('2', '3', '4', '5', '6')):
                    i += 1
                    current_chunk.append(lines[i])
                
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
            
            current_chunk.append(line)
            current_size += len(line)
            i += 1
        
        # Agregar último chunk
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        logger.info(f"📦 Tabla dividida en {len(chunks)} chunks")
        return chunks
    
    def _extract_financial_totals(self, text: str) -> Dict[str, Any]:
        """
        Extrae los totales financieros del final del documento
        """
        # Buscar en los últimos 1000 caracteres
        footer_text = text[-1000:]
        
        totals = {
            'total_reclamado': 0,
            'total_objetado': 0,
            'total_pagado': 0
        }
        
        # Patrones para totales
        patterns = {
            'total_reclamado': [
                r'Valor\s+de\s+Reclamación\s*:\s*\$?([\d,]+)',
                r'Total\s+Reclamado\s*:\s*\$?([\d,]+)',
                r'TOTAL\s*:\s*\$?([\d,]+)'
            ],
            'total_objetado': [
                r'Valor\s+objetado\s*:\s*\$?([\d,]+)',
                r'Total\s+Objetado\s*:\s*\$?([\d,]+)'
            ],
            'total_pagado': [
                r'Valor\s+a\s+Pagar\s*:\s*\$?([\d,]+)',
                r'Total\s+Pagado\s*:\s*\$?([\d,]+)',
                r'Valor\s+Aceptado\s*:\s*\$?([\d,]+)'
            ]
        }
        
        for field, field_patterns in patterns.items():
            for pattern in field_patterns:
                match = re.search(pattern, footer_text, re.IGNORECASE)
                if match:
                    value_str = match.group(1).replace(',', '')
                    totals[field] = int(value_str)
                    break
        
        # Si no encontramos totales en el footer, buscar en toda la tabla
        if totals['total_reclamado'] == 0:
            # Buscar línea de totales en formato de tabla
            total_line_pattern = r'^\s*.*?\s+\$?([\d,]+)\s+\$?([\d,]+)\s+\$?([\d,]+)\s*$'
            matches = re.findall(total_line_pattern, text, re.MULTILINE)
            if matches:
                # Tomar la última coincidencia (probablemente los totales)
                last_match = matches[-1]
                totals['total_reclamado'] = int(last_match[0].replace(',', ''))
                totals['total_pagado'] = int(last_match[1].replace(',', ''))
                totals['total_objetado'] = int(last_match[2].replace(',', ''))
        
        logger.info(f"💰 Totales extraídos: {totals}")
        return totals
    
    def _get_empty_result(self) -> Dict[str, Any]:
        """
        Retorna estructura vacía
        """
        return {
            "patient_info": {},
            "policy_info": {},
            "procedures": [],
            "financial_summary": {
                "total_reclamado": 0,
                "total_objetado": 0,
                "total_pagado": 0
            },
            "processing_metadata": {
                "method": "paginated_v2_failed",
                "status": "error"
            }
        }