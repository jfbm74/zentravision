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
    
    def __init__(self, openai_api_key: Optional[str] = None):
        self.openai_api_key = openai_api_key
        self.extraction_strategies = {
            'hybrid': self._extract_hybrid,
            'ai_only': self._extract_ai_only,
            'ocr_only': self._extract_ocr_only
        }
        
        # Configurar patrones específicos para SOAT
        self._setup_soat_patterns()
    
    def _setup_soat_patterns(self):
        """Configura patrones específicos para documentos SOAT"""
        
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
                r'GNS-LIQ-(\d+)',
                r'LIQ-(\d+)',
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
        
        # Patrones específicos para procedimientos SOAT (tabla estructurada)
        self.procedure_table_pattern = r'(\d{1,8}(?:-\d{1,2})?)\s+([A-ZÁÉÍÓÚÑ\s\w\/\#]+?)\s+(\d+(?:\.\d+)?)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)\s+\$?([\d,\.]+)(?:\s+(.+?))?(?=\n\d|\nTotal|\n[A-Z]{2,}|\Z)'
        
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
        """Extrae información estructurada de un PDF de glosa SOAT"""
        try:
            logger.info(f"Iniciando extracción SOAT con estrategia: {strategy}")
            
            # Extraer texto del PDF
            text_content = self._extract_text_from_pdf(pdf_path)
            
            if not text_content.strip():
                logger.warning("No se pudo extraer texto del PDF")
                return self._get_empty_result()
            
            # Para SOAT siempre usar OCR mejorado
            result = self._extract_soat_data(text_content)
            
            # Si hay API key de OpenAI y la estrategia lo permite, mejorar con IA
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
            
            logger.info("Extracción SOAT completada exitosamente")
            return result
            
        except Exception as e:
            logger.error(f"Error en extracción: {str(e)}")
            return self._get_error_result(str(e))
    
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
        """Extracción específica para documentos SOAT"""
        try:
            result = self._get_empty_result()
            
            # Limpiar texto
            cleaned_text = self._clean_text(text)
            
            # Extraer información del paciente
            result['patient_info'] = self._extract_soat_patient_info(cleaned_text)
            
            # Extraer información de la póliza
            result['policy_info'] = self._extract_soat_policy_info(cleaned_text)
            
            # Extraer procedimientos de la tabla
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
        """Extrae procedimientos de la tabla estructurada SOAT"""
        procedures = []
        
        # Buscar la tabla de procedimientos
        matches = re.finditer(self.procedure_table_pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        for match in matches:
            try:
                codigo = match.group(1).strip()
                descripcion = match.group(2).strip()
                cantidad = float(match.group(3).strip())
                valor_total = self._parse_money_value(match.group(4))
                valor_pagado = self._parse_money_value(match.group(5))
                valor_objetado = self._parse_money_value(match.group(6))
                observacion = match.group(7).strip() if match.group(7) else ""
                
                # Calcular valor unitario
                valor_unitario = valor_total / cantidad if cantidad > 0 else 0
                
                procedure = {
                    'codigo': codigo,
                    'descripcion': descripcion,
                    'cantidad': int(cantidad),
                    'valor_unitario': valor_unitario,
                    'valor_total': valor_total,
                    'valor_pagado': valor_pagado,
                    'valor_objetado': valor_objetado,
                    'observacion': observacion,
                    'estado': 'objetado' if valor_objetado > 0 else 'aceptado'
                }
                
                procedures.append(procedure)
                
            except (ValueError, IndexError) as e:
                logger.warning(f"Error procesando procedimiento: {e}")
                continue
        
        # Si no encontró procedimientos con el patrón principal, intentar patrón alternativo
        if not procedures:
            procedures = self._extract_procedures_alternative_pattern(text)
        
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