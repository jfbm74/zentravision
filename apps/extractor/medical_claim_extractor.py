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
    Extractor optimizado específicamente para glosas SOAT colombianas
    Versión consolidada que elimina código redundante y usa solo métodos que funcionan
    """
    
    def __init__(self, openai_api_key=None):
        self.openai_api_key = openai_api_key
        self._setup_soat_patterns()

    def _setup_soat_patterns(self):
        """Configura patrones específicos para documentos SOAT"""
        
        # Patrones para información del paciente
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
        
        # Patrones para información de póliza
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
        
        # Patrones para diagnósticos
        self.diagnostic_patterns = [
            r'DX\s*:\s*([A-Z]\d{2,3})',
            r'DIAGNOSTICO\s*:\s*([A-Z]\d{2,3})',
            r'CIE\s*:\s*([A-Z]\d{2,3})',
        ]
        
        # Patrones financieros
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

        # Patrón principal optimizado para procedimientos
        self.main_procedure_pattern = r'(\d{5}|00000)\s+([A-ZÁÉÍÓÚÑ\s\w\/\#\,\.\-\(\)\%]+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)(?:\s+(.+?))?(?=\n\d{5}|\n00000|\nTotal|\nValor de|\Z)'

    # ============================================================================
    # MÉTODO PRINCIPAL DE EXTRACCIÓN
    # ============================================================================

    def extract_from_pdf(self, pdf_path: str, strategy: str = 'hybrid') -> Dict[str, Any]:
        """Método principal de extracción"""
        try:
            logger.info(f"Iniciando extracción SOAT con estrategia: {strategy}")
            
            # Extraer texto del PDF
            text_content = self._extract_text_from_pdf(pdf_path)
            
            if not text_content.strip():
                logger.warning("No se pudo extraer texto del PDF")
                return self._get_empty_result()
            
            # Usar extracción optimizada
            result = self._extract_soat_data(text_content)
            
            # Mejorar con IA si está disponible
            if self.openai_api_key and strategy in ['hybrid', 'ai_only']:
                try:
                    ai_result = self._extract_with_openai(text_content)
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

    # ============================================================================
    # EXTRACCIÓN DE DATOS PRINCIPALES
    # ============================================================================

    def _extract_soat_data(self, text: str) -> Dict[str, Any]:
        """Extracción principal de datos SOAT"""
        try:
            result = self._get_empty_result()
            
            # ✅ FIX: NO limpiar texto para procedimientos, usar texto original
            # cleaned_text = self._clean_text(text)  # ❌ ESTO CAUSABA EL PROBLEMA
            
            # Extraer cada sección con el texto apropiado
            result['patient_info'] = self._extract_patient_info(text)
            result['policy_info'] = self._extract_policy_info(text)
            result['procedures'] = self._extract_procedures(text)      # ✅ FIX: Usar texto original
            result['financial_summary'] = self._extract_financial_summary(text)
            result['diagnostics'] = self._extract_diagnostics(text)
            result['ips_info'] = self._extract_ips_info(text)
            
            # Calcular estadísticas
            result['extraction_details'] = self._calculate_extraction_stats(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error en extracción SOAT: {str(e)}")
            return self._get_empty_result()


    # ============================================================================
    # EXTRACCIÓN DE PROCEDIMIENTOS (MÉTODO PRINCIPAL OPTIMIZADO)
    # ============================================================================

    def _extract_procedures(self, text: str) -> List[Dict[str, Any]]:
        """
        MÉTODO PRINCIPAL OPTIMIZADO para extracción de procedimientos
        Consolida todos los métodos que funcionan en uno solo
        """
        procedures = []
        
        logger.info("Iniciando extracción optimizada de procedimientos")
        
        # Usar patrón principal optimizado
        matches = re.finditer(self.main_procedure_pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        for match in matches:
            try:
                # Extraer datos básicos
                codigo = match.group(1).strip()
                descripcion_raw = match.group(2).strip()
                cantidad = float(match.group(3).strip())
                valor_total = self._parse_money_value(match.group(4))
                valor_pagado = self._parse_money_value(match.group(5))
                valor_objetado = self._parse_money_value(match.group(6))
                observacion_raw = match.group(7).strip() if match.group(7) else ""
                
                # Limpiar y validar
                descripcion = self._clean_description(descripcion_raw)
                observacion = self._clean_observation(observacion_raw)
                
                # Validar procedimiento
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
                    logger.debug(f"Procedimiento extraído: {codigo} - {descripcion[:50]}...")
                else:
                    logger.debug(f"Procedimiento descartado: {codigo} - {descripcion[:30]}...")
                    
            except Exception as e:
                logger.error(f"Error procesando procedimiento: {e}")
                continue
        
        logger.info(f"Total procedimientos extraídos: {len(procedures)}")
        return procedures

    def _is_valid_procedure(self, codigo: str, descripcion: str, valor_total: float) -> bool:
        """Validación optimizada de procedimientos"""
        
        # 1. Validar código
        if not re.match(r'^(\d{5}|00000)$', codigo):
            return False
        
        # 2. Validar descripción básica
        if not descripcion or len(descripcion.strip()) < 3:
            return False
        
        # 3. Patrones que NO deben estar en descripción (consolidado)
        invalid_patterns = [
            'Pagina', 'LIQ-', 'Liquidación de siniestro', 'Fecha de Pago',
            'Víctima :', 'Número de reclamación', 'Póliza :', 'DX :',
            'CORRESPONDE ESTA ESPECIALIDAD'
        ]
        
        for pattern in invalid_patterns:
            if pattern in descripcion:
                return False
        
        # 4. Validar valor monetario
        if valor_total <= 0 or valor_total > 10000000:
            return False
        
        # 5. Validaciones adicionales
        if descripcion.strip().isdigit():
            return False
        
        desc_clean = re.sub(r'[^\w\s]', '', descripcion).strip()
        if len(desc_clean) < 5:
            return False
        
        return True

    def _clean_description(self, description: str) -> str:
        """Limpieza optimizada de descripción"""
        if not description:
            return ""
        
        # Remover patrones problemáticos
        description = re.sub(r'^\d+\s*', '', description)  # Números al inicio
        description = re.sub(r'\s+\d+\s*$', '', description)  # Números al final
        description = re.sub(r'\$[\d,\.]+', '', description)  # Valores monetarios
        description = re.sub(r'\d{4}\s+>>', '', description)  # Códigos de observación
        
        # Remover texto problemático
        stop_words = ['LIQ-', 'Pagina', 'Liquidación', 'Fecha de', 'Víctima', 'Número de']
        for stop_word in stop_words:
            if stop_word in description:
                pos = description.find(stop_word)
                description = description[:pos].strip()
                break
        
        # Normalizar espacios
        description = re.sub(r'\s+', ' ', description.strip())
        
        # Capitalizar apropiadamente
        if description:
            words = description.split()
            cleaned_words = []
            for word in words:
                if len(word) <= 3 and word.isupper():  # Mantener acrónimos
                    cleaned_words.append(word)
                else:
                    cleaned_words.append(word.title())
            description = ' '.join(cleaned_words)
        
        return description

    def _clean_observation(self, observation: str) -> str:
        """Limpieza optimizada de observación"""
        if not observation:
            return ""
        
        # Extraer parte relevante
        obs_pattern = r'(\d{4})\s+>>\s+(.+?)(?=\n\d{4}\s+>>|\n\d{5}|\n00000|\nTotal|\Z)'
        match = re.search(obs_pattern, observation, re.DOTALL)
        
        if match:
            observation = match.group(2).strip()
        
        # Normalizar y truncar
        observation = re.sub(r'\s+', ' ', observation.strip())
        
        if len(observation) > 300:
            observation = observation[:300] + "..."
        
        return observation

    # ============================================================================
    # EXTRACCIÓN DE OTRAS SECCIONES
    # ============================================================================

    def _extract_patient_info(self, text: str) -> Dict[str, Any]:
        """Extrae información del paciente"""
        patient_info = {}
        
        # Extraer nombre
        for pattern in self.patient_patterns['nombre']:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                nombre = match.group(1).strip()
                nombre = re.sub(r'\s+', ' ', nombre)
                patient_info['nombre'] = nombre.title()
                break
        
        # Extraer documento
        for pattern in self.patient_patterns['documento']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if len(match.groups()) == 2:
                    patient_info['tipo_documento'] = match.group(1).strip()
                    patient_info['documento'] = match.group(2).strip()
                else:
                    patient_info['documento'] = match.group(1).strip()
                break
        
        # Extraer tipo de documento si falta
        if 'tipo_documento' not in patient_info:
            for pattern in self.patient_patterns['tipo_documento']:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    patient_info['tipo_documento'] = match.group(1).strip()
                    break
        
        return patient_info

    def _extract_policy_info(self, text: str) -> Dict[str, Any]:
        """Extrae información de póliza"""
        policy_info = {}
        
        for key, patterns in self.policy_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    policy_info[key] = match.group(1).strip()
                    break
        
        return policy_info

    def _extract_financial_summary(self, text: str) -> Dict[str, Any]:
        """Extrae resumen financiero"""
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
        
        # Mapear nombres estándar
        if 'valor_reclamacion' in financial:
            financial['total_reclamado'] = financial['valor_reclamacion']
        if 'valor_objetado' in financial:
            financial['total_objetado'] = financial['valor_objetado']
        if 'valor_pagado' in financial:
            financial['total_pagado'] = financial['valor_pagado']
        
        return financial

    def _extract_diagnostics(self, text: str) -> List[Dict[str, Any]]:
        """Extrae diagnósticos"""
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

    def _extract_ips_info(self, text: str) -> Dict[str, Any]:
        """Extrae información de IPS"""
        ips_info = {}
        
        for pattern in self.ips_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                nombre = match.group(1).strip()
                nombre = re.sub(r'\s+', ' ', nombre)
                ips_info['nombre'] = nombre.title()
                break
        
        # Buscar NIT
        nit_pattern = r'NIT\s*-?\s*(\d{9,12})'
        match = re.search(nit_pattern, text, re.IGNORECASE)
        if match:
            ips_info['nit'] = match.group(1).strip()
        
        return ips_info

    # ============================================================================
    # UTILIDADES Y HELPERS
    # ============================================================================

    def _extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extrae texto de PDF usando PyMuPDF"""
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

    def _parse_money_value(self, value_str: str) -> float:
        """Convierte string monetario a float"""
        if not value_str:
            return 0.0
        
        try:
            clean_value = re.sub(r'[\$\s]', '', str(value_str))
            
            if ',' in clean_value and clean_value.count(',') == 1:
                parts = clean_value.split(',')
                if len(parts[1]) <= 2:
                    clean_value = clean_value.replace(',', '.')
                else:
                    clean_value = clean_value.replace(',', '')
            else:
                clean_value = clean_value.replace(',', '')
            
            return float(clean_value)
        except (ValueError, TypeError):
            return 0.0

    def _clean_text(self, text: str) -> str:
        """Limpia y normaliza texto"""
        if not text:
            return ""
        
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'\r', '\n', text)
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()

    def _get_cie10_description(self, codigo: str) -> str:
        """Obtiene descripción de códigos CIE-10"""
        cie10_descriptions = {
            'S836': 'Esguince y distensión de otras partes y las no especificadas de la rodilla',
            'S83': 'Luxación, esguince y distensión de articulaciones y ligamentos de la rodilla',
            'M25': 'Otros trastornos articulares no clasificados en otra parte',
            'S72': 'Fractura del fémur',
            'S82': 'Fractura de la pierna, incluyendo el tobillo',
        }
        
        for key, desc in cie10_descriptions.items():
            if codigo.startswith(key):
                return desc
        
        return ""

    def _calculate_extraction_stats(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Calcula estadísticas de extracción"""
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
        """Cuenta campos extraídos exitosamente"""
        count = 0
        
        count += len([v for v in result.get('patient_info', {}).values() if v])
        count += len([v for v in result.get('policy_info', {}).values() if v])
        count += len([v for v in result.get('financial_summary', {}).values() if v])
        count += len(result.get('procedures', []))
        count += len(result.get('diagnostics', []))
        
        return count

    def _calculate_extraction_quality(self, result: Dict[str, Any]) -> str:
        """Calcula calidad de extracción"""
        total_fields = self._count_extracted_fields(result)
        
        if total_fields >= 20:
            return 'excelente'
        elif total_fields >= 15:
            return 'buena'
        elif total_fields >= 10:
            return 'regular'
        else:
            return 'baja'

    # ============================================================================
    # INTEGRACIÓN CON OPENAI (OPCIONAL)
    # ============================================================================

    def _extract_with_openai(self, text: str) -> Dict[str, Any]:
        """Extrae información usando OpenAI GPT"""
        try:
            import openai
            
            client = openai.OpenAI(api_key=self.openai_api_key)
            
            prompt = self._build_openai_prompt(text)
            
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
                if ai_response.startswith('```json'):
                    ai_response = ai_response.replace('```json', '').replace('```', '')
                elif ai_response.startswith('```'):
                    ai_response = ai_response.replace('```', '')
                
                ai_data = json.loads(ai_response)
                logger.info("OpenAI: Datos extraídos exitosamente")
                return ai_data
                
            except json.JSONDecodeError as e:
                logger.warning(f"OpenAI: Error parseando JSON: {e}")
                return self._get_empty_result()
                
        except ImportError:
            logger.warning("OpenAI no está instalado")
            return self._get_empty_result()
        except Exception as e:
            logger.error(f"Error con OpenAI: {str(e)}")
            return self._get_empty_result()

    def _build_openai_prompt(self, text: str) -> str:
        """Construye prompt para OpenAI"""
        text_sample = text[:4000] if len(text) > 4000 else text
        
        return f"""
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
            "numero_reclamacion": "número de reclamación"
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
            "total_pagado": 0
        }}
        }}

        Responde SOLO con el JSON, sin texto adicional.
        """

    def _merge_results(self, ocr_result: Dict[str, Any], ai_result: Dict[str, Any]) -> Dict[str, Any]:
        """Combina resultados de OCR y IA"""
        return ocr_result  # Por ahora usar solo OCR

    # ============================================================================
    # MÉTODOS DE RESULTADO Y ERROR
    # ============================================================================

    def _get_empty_result(self) -> Dict[str, Any]:
        """Retorna estructura vacía"""
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

    # ============================================================================
    # MÉTODOS DE DEBUG Y TESTING
    # ============================================================================

    def debug_table_extraction(self, text: str):
        """Debug para análisis de extracción"""
        lines = text.split('\n')
        
        print("=== DEBUG EXTRACCIÓN DE TABLA ===")
        print(f"Total líneas: {len(lines)}")
        
        # Buscar encabezado
        for i, line in enumerate(lines):
            line_clean = line.strip()
            if ('Código' in line_clean and 'Descripción' in line_clean and 
                'Cant' in line_clean and 'Valor total' in line_clean):
                print(f"✅ Encabezado encontrado en línea {i}: {line_clean}")
                
                # Mostrar líneas siguientes
                print("\n--- Líneas después del encabezado ---")
                for j in range(i+1, min(i+21, len(lines))):
                    line_data = lines[j].strip()
                    if line_data:
                        is_procedure = re.match(r'^(\d{5}|00000)', line_data)
                        marker = "📋" if is_procedure else "  "
                        print(f"{marker} Línea {j}: {line_data[:100]}...")
                break
        
        # Buscar procedimientos
        print(f"\n=== BÚSQUEDA DE PROCEDIMIENTOS ===")
        matches = list(re.finditer(self.main_procedure_pattern, text, re.IGNORECASE | re.MULTILINE))
        print(f"Procedimientos encontrados: {len(matches)}")
        
        for i, match in enumerate(matches[:10]):
            codigo = match.group(1)
            descripcion = match.group(2)[:50]
            cantidad = match.group(3)
            print(f"{i+1}. {codigo} - {descripcion}... (Cant: {cantidad})")
        
        return matches

    def debug_procedure_validation(self, text: str):
        """Debug específico para validación"""
        print("=== DEBUG VALIDACIÓN DE PROCEDIMIENTOS ===")
        
        matches = re.finditer(self.main_procedure_pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        valid_procedures = []
        invalid_procedures = []
        
        for i, match in enumerate(matches, 1):
            try:
                codigo = match.group(1).strip()
                descripcion_raw = match.group(2).strip()
                cantidad = float(match.group(3).strip())
                valor_total = self._parse_money_value(match.group(4))
                
                descripcion = self._clean_description(descripcion_raw)
                
                print(f"\n--- PROCEDIMIENTO {i} ---")
                print(f"Código: {codigo}")
                print(f"Descripción: {descripcion}")
                print(f"Valor total: {valor_total}")
                
                is_valid = self._is_valid_procedure(codigo, descripcion, valor_total)
                print(f"🔍 RESULTADO: {'✅ VÁLIDO' if is_valid else '❌ INVÁLIDO'}")
                
                if is_valid:
                    valid_procedures.append({'codigo': codigo, 'descripcion': descripcion})
                else:
                    invalid_procedures.append({'codigo': codigo, 'descripcion': descripcion})
                    
            except Exception as e:
                print(f"❌ ERROR procesando procedimiento {i}: {e}")
        
        print(f"\n=== RESUMEN ===")
        print(f"✅ Procedimientos válidos: {len(valid_procedures)}")
        print(f"❌ Procedimientos inválidos: {len(invalid_procedures)}")
        
        return valid_procedures, invalid_procedures

    # ============================================================================
    # MÉTODOS LEGACY DE COMPATIBILIDAD (PARA NO ROMPER CÓDIGO EXISTENTE)
    # ============================================================================

    def _extract_soat_data_improved(self, text: str) -> Dict[str, Any]:
        """Alias para compatibilidad"""
        return self._extract_soat_data(text)

    def _extract_soat_procedures_table_improved(self, text: str) -> List[Dict[str, Any]]:
        """Alias para compatibilidad"""
        return self._extract_procedures(text)

    def _extract_procedures_from_full_text_v2(self, text: str) -> List[Dict[str, Any]]:
        """Alias para compatibilidad"""
        return self._extract_procedures(text)

    def _is_valid_procedure_v2(self, codigo: str, descripcion: str, valor_total: float) -> bool:
        """Alias para compatibilidad"""
        return self._is_valid_procedure(codigo, descripcion, valor_total)

    def _clean_procedure_description_v2(self, description: str) -> str:
        """Alias para compatibilidad"""
        return self._clean_description(description)

    def _clean_observation_v2(self, observation: str) -> str:
        """Alias para compatibilidad"""
        return self._clean_observation(observation)

    def _extract_soat_patient_info(self, text: str) -> Dict[str, Any]:
        """Alias para compatibilidad"""
        return self._extract_patient_info(text)

    def _extract_soat_policy_info(self, text: str) -> Dict[str, Any]:
        """Alias para compatibilidad"""
        return self._extract_policy_info(text)

    def _extract_soat_financial_summary(self, text: str) -> Dict[str, Any]:
        """Alias para compatibilidad"""
        return self._extract_financial_summary(text)

    def _extract_soat_diagnostics(self, text: str) -> List[Dict[str, Any]]:
        """Alias para compatibilidad"""
        return self._extract_diagnostics(text)

    def _extract_soat_ips_info(self, text: str) -> Dict[str, Any]:
        """Alias para compatibilidad"""
        return self._extract_ips_info(text)