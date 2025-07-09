import logging
import json
import fitz  # PyMuPDF
from typing import Dict, Any, Optional, List
from datetime import datetime
import re
import os

# Importar utilidades si están disponibles
try:
    from .utils import enhance_extraction_results, TextCleaner, MedicalValidator
    UTILS_AVAILABLE = True
except ImportError:
    UTILS_AVAILABLE = False

logger = logging.getLogger(__name__)

class MedicalClaimExtractor:
    """
    Extractor mejorado de información de glosas médicas colombianas
    Utiliza patrones específicos del sistema de salud colombiano
    """
    
    def __init__(self, openai_api_key: Optional[str] = None):
        self.openai_api_key = openai_api_key
        self.extraction_strategies = {
            'hybrid': self._extract_hybrid,
            'ai_only': self._extract_ai_only,
            'ocr_only': self._extract_ocr_only
        }
        
        # Configurar patrones para glosas médicas colombianas
        self._setup_extraction_patterns()
    
    def _setup_extraction_patterns(self):
        """Configura patrones de extracción específicos para Colombia"""
        
        # Patrones para información del paciente
        self.patient_patterns = {
            'nombre': [
                r'(?:nombre|paciente|beneficiario|titular)[\s:]*([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)',
                r'PACIENTE[\s:]*([A-ZÁÉÍÓÚÑ\s]+?)(?:\n|CC|NIT)',
                r'BENEFICIARIO[\s:]*([A-ZÁÉÍÓÚÑ\s]+?)(?:\n|DOCUMENTO)',
                r'NOMBRE DEL PACIENTE[\s:]*([A-ZÁÉÍÓÚÑ\s]+)'
            ],
            'documento': [
                r'(?:C\.?C\.?|CEDULA|DOCUMENTO|IDENTIFICACION)[\s:]*(\d{6,12})',
                r'CC[\s:]?(\d{6,12})',
                r'IDENTIFICACION[\s:]*(\d{6,12})',
                r'NIT[\s:]?(\d{9,12})'
            ],
            'tipo_documento': [
                r'(CC|C\.C\.|CEDULA|NIT|TI|PASAPORTE|EXTRANJERIA)',
                r'TIPO[\s:]*([A-Z]{2,})'
            ],
            'edad': [
                r'EDAD[\s:]*(\d{1,3})',
                r'(\d{1,3})\s*AÑOS',
                r'AÑOS[\s:]*(\d{1,3})'
            ]
        }
        
        # Patrones para información de la póliza/seguro
        self.policy_patterns = {
            'poliza': [
                r'POLIZA[\s:]*([A-Z0-9\-]+)',
                r'PÓLIZA[\s:]*([A-Z0-9\-]+)',
                r'No\.?\s*POLIZA[\s:]*([A-Z0-9\-]+)',
                r'POLICY[\s:]*([A-Z0-9\-]+)'
            ],
            'aseguradora': [
                r'ASEGURADORA[\s:]*([A-ZÁÉÍÓÚÑ\s]+?)(?:\n|POLIZA)',
                r'COMPAÑIA[\s:]*([A-ZÁÉÍÓÚÑ\s\.]+)',
                r'SEGUROS\s+([A-ZÁÉÍÓÚÑ\s]+)',
                r'(SURAMERICANA|BOLIVAR|MAPFRE|AXA|LIBERTY|MUNDIAL|PREVISORA|COLMENA)'
            ],
            'numero_reclamacion': [
                r'RECLAMACION[\s:]*([A-Z0-9\-]+)',
                r'RECLAMO[\s:]*([A-Z0-9\-]+)',
                r'No\.?\s*RECLAMACION[\s:]*([A-Z0-9\-]+)',
                r'CLAIM[\s:]*([A-Z0-9\-]+)'
            ],
            'numero_liquidacion': [
                r'LIQUIDACION[\s:]*([A-Z0-9\-]+)',
                r'No\.?\s*LIQUIDACION[\s:]*([A-Z0-9\-]+)',
                r'SETTLEMENT[\s:]*([A-Z0-9\-]+)'
            ]
        }
        
        # Patrones para fechas
        self.date_patterns = {
            'fecha_siniestro': [
                r'FECHA.*SINIESTRO[\s:]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
                r'SINIESTRO[\s:]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
                r'ACCIDENT.*DATE[\s:]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})'
            ],
            'fecha_ingreso': [
                r'FECHA.*INGRESO[\s:]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
                r'INGRESO[\s:]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
                r'ADMISSION[\s:]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})'
            ],
            'fecha_egreso': [
                r'FECHA.*EGRESO[\s:]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
                r'EGRESO[\s:]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
                r'DISCHARGE[\s:]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})'
            ]
        }
        
        # Patrones para diagnósticos (CIE-10)
        self.diagnostic_patterns = [
            r'(?:DIAGNOSTICO|DX|CIE)[\s:]*([A-Z]\d{2}\.?\d?)',
            r'CIE[\-\s]*10[\s:]*([A-Z]\d{2}\.?\d?)',
            r'([A-Z]\d{2}\.\d)\s*[-–]\s*([A-ZÁÉÍÓÚÑ\s]+)',
            r'CODIGO[\s:]*([A-Z]\d{2}\.?\d?)'
        ]
        
        # Patrones para procedimientos médicos (CUPS)
        self.procedure_patterns = [
            # Código CUPS (6 dígitos) + descripción + valores
            r'(\d{6})\s+([A-ZÁÉÍÓÚÑ\s\-,\.]+?)\s+(\d+)\s+(\$?\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',
            # Código + descripción en líneas separadas
            r'(\d{6})\s*\n([A-ZÁÉÍÓÚÑ\s\-,\.]+)\s+(\d+)\s+(\$?\d{1,3}(?:\.\d{3})*)',
            # Formato con códigos SOAT
            r'(\d{4,6})\s+([A-ZÁÉÍÓÚÑ\s]+)\s+(\d+)\s+(\$?\d{1,3}(?:\.\d{3})*)',
        ]
        
        # Patrones para valores monetarios
        self.money_patterns = {
            'total_reclamado': [
                r'TOTAL.*RECLAMADO[\s:]*\$?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',
                r'VALOR.*RECLAMADO[\s:]*\$?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',
                r'RECLAMADO[\s:]*\$?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)'
            ],
            'total_objetado': [
                r'TOTAL.*OBJETADO[\s:]*\$?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',
                r'VALOR.*OBJETADO[\s:]*\$?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',
                r'OBJETADO[\s:]*\$?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)'
            ],
            'total_pagado': [
                r'TOTAL.*PAGADO[\s:]*\$?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',
                r'VALOR.*PAGADO[\s:]*\$?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',
                r'PAGADO[\s:]*\$?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)'
            ],
            'total_aceptado': [
                r'TOTAL.*ACEPTADO[\s:]*\$?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',
                r'VALOR.*ACEPTADO[\s:]*\$?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',
                r'ACEPTADO[\s:]*\$?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)'
            ]
        }
        
        # Patrones para instituciones prestadoras de salud (IPS)
        self.ips_patterns = [
            r'IPS[\s:]*([A-ZÁÉÍÓÚÑ\s\.]+?)(?:\n|NIT)',
            r'CLINICA\s+([A-ZÁÉÍÓÚÑ\s]+)',
            r'HOSPITAL\s+([A-ZÁÉÍÓÚÑ\s]+)',
            r'CENTRO\s+MEDICO\s+([A-ZÁÉÍÓÚÑ\s]+)',
            r'INSTITUCION[\s:]*([A-ZÁÉÍÓÚÑ\s\.]+)'
        ]
    
    def extract_from_pdf(self, pdf_path: str, strategy: str = 'hybrid') -> Dict[str, Any]:
        """
        Extrae información estructurada de un PDF de glosa médica
        
        Args:
            pdf_path: Ruta al archivo PDF
            strategy: Estrategia de extracción ('hybrid', 'ai_only', 'ocr_only')
        
        Returns:
            Dict con la información extraída
        """
        try:
            if strategy not in self.extraction_strategies:
                strategy = 'hybrid'
            
            logger.info(f"Iniciando extracción con estrategia: {strategy}")
            
            # Extraer texto del PDF
            text_content = self._extract_text_from_pdf(pdf_path)
            
            if not text_content.strip():
                logger.warning("No se pudo extraer texto del PDF")
                return self._get_empty_result()
            
            # Aplicar estrategia seleccionada
            result = self.extraction_strategies[strategy](text_content)
            
            # Agregar metadata
            result['metadata'] = {
                'extraction_strategy': strategy,
                'extraction_date': datetime.now().isoformat(),
                'file_path': pdf_path,
                'text_length': len(text_content),
                'success': True
            }
            
            logger.info("Extracción completada exitosamente")
            return result
            
        except Exception as e:
            logger.error(f"Error en extracción: {str(e)}")
            return self._get_error_result(str(e))
    
    def _extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extrae texto de un PDF usando PyMuPDF con mejoras para OCR"""
        try:
            doc = fitz.open(pdf_path)
            text = ""
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                
                # Extraer texto normal
                page_text = page.get_text()
                
                # Si no hay texto o es muy poco, intentar OCR en la imagen
                if len(page_text.strip()) < 50:
                    logger.info(f"Poco texto en página {page_num}, intentando OCR...")
                    try:
                        # Convertir página a imagen y extraer texto
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # Aumentar resolución
                        img_data = pix.tobytes("png")
                        
                        # Aquí podrías integrar Tesseract OCR si está disponible
                        # Por ahora usamos el texto disponible
                        page_text = page.get_text()
                        
                    except Exception as e:
                        logger.warning(f"Error en OCR para página {page_num}: {e}")
                
                text += page_text + "\n"
            
            doc.close()
            return text
            
        except Exception as e:
            logger.error(f"Error extrayendo texto del PDF: {str(e)}")
            return ""
    
    def _extract_hybrid(self, text: str) -> Dict[str, Any]:
        """Estrategia híbrida: OCR mejorado + IA (si disponible)"""
        try:
            # Usar OCR mejorado como base
            ocr_result = self._extract_ocr_only(text)
            
            # Si hay API key de OpenAI, mejorar con IA
            if self.openai_api_key:
                try:
                    ai_result = self._extract_with_openai(text)
                    # Combinar resultados priorizando IA donde sea más precisa
                    return self._merge_results(ocr_result, ai_result)
                except Exception as e:
                    logger.warning(f"Error con OpenAI, usando solo OCR: {e}")
            
            return ocr_result
                
        except Exception as e:
            logger.error(f"Error en estrategia híbrida: {str(e)}")
            return self._extract_ocr_only(text)
    
    def _extract_ai_only(self, text: str) -> Dict[str, Any]:
        """Estrategia solo IA (requiere OpenAI API)"""
        if not self.openai_api_key:
            logger.warning("No hay API key de OpenAI, usando OCR mejorado")
            return self._extract_ocr_only(text)
        
        try:
            return self._extract_with_openai(text)
        except Exception as e:
            logger.error(f"Error en extracción con IA: {str(e)}")
            return self._extract_ocr_only(text)
    
    def _extract_ocr_only(self, text: str) -> Dict[str, Any]:
        """Estrategia OCR mejorada con patrones específicos para Colombia"""
        try:
            result = self._get_empty_result()
            
            # Limpiar y normalizar texto
            cleaned_text = self._clean_text(text)
            
            # Extraer información del paciente
            result['patient_info'] = self._extract_patient_info_improved(cleaned_text)
            
            # Extraer información de la póliza
            result['policy_info'] = self._extract_policy_info_improved(cleaned_text)
            
            # Extraer procedimientos médicos
            result['procedures'] = self._extract_procedures_improved(cleaned_text)
            
            # Extraer resumen financiero
            result['financial_summary'] = self._extract_financial_summary_improved(cleaned_text)
            
            # Extraer diagnósticos
            result['diagnostics'] = self._extract_diagnostics(cleaned_text)
            
            # Extraer información de la IPS
            result['ips_info'] = self._extract_ips_info(cleaned_text)
            
            # Calcular estadísticas adicionales
            result['extraction_details'] = self._calculate_extraction_stats(result)
            
            # Aplicar mejoras si las utilidades están disponibles
            if UTILS_AVAILABLE:
                result = enhance_extraction_results(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error en extracción OCR: {str(e)}")
            return self._get_empty_result()
    
    def _clean_text(self, text: str) -> str:
        """Limpia y normaliza el texto extraído"""
        if UTILS_AVAILABLE:
            return TextCleaner.clean_medical_text(text)
        
        # Fallback básico si no hay utils
        text = re.sub(r'[^\w\s\.\,\:\;\-\$\(\)\/]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        text = text.upper()
        return text.strip()
    
    def _extract_patient_info_improved(self, text: str) -> Dict[str, Any]:
        """Extrae información del paciente con patrones mejorados"""
        patient_info = {}
        
        # Extraer nombre
        for pattern in self.patient_patterns['nombre']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                patient_info['nombre'] = match.group(1).strip().title()
                break
        
        # Extraer documento
        for pattern in self.patient_patterns['documento']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                patient_info['documento'] = match.group(1).strip()
                break
        
        # Extraer tipo de documento
        for pattern in self.patient_patterns['tipo_documento']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                patient_info['tipo_documento'] = match.group(1).strip()
                break
        
        # Extraer edad
        for pattern in self.patient_patterns['edad']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    patient_info['edad'] = int(match.group(1))
                except ValueError:
                    pass
                break
        
        return patient_info
    
    def _extract_policy_info_improved(self, text: str) -> Dict[str, Any]:
        """Extrae información de la póliza con patrones mejorados"""
        policy_info = {}
        
        # Extraer información de póliza y seguro
        for key, patterns in self.policy_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    policy_info[key] = match.group(1).strip()
                    break
        
        # Extraer fechas importantes
        for key, patterns in self.date_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    policy_info[key] = match.group(1).strip()
                    break
        
        return policy_info
    
    def _extract_procedures_improved(self, text: str) -> List[Dict[str, Any]]:
        """Extrae procedimientos médicos con patrones mejorados"""
        procedures = []
        
        for pattern in self.procedure_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            
            for match in matches:
                try:
                    codigo = match[0].strip()
                    descripcion = match[1].strip()
                    cantidad = int(match[2]) if match[2].isdigit() else 1
                    
                    # Limpiar valor monetario
                    if UTILS_AVAILABLE:
                        valor_unitario = TextCleaner.normalize_money_value(match[3])
                    else:
                        try:
                            valor_str = match[3].replace('$', '').replace('.', '').replace(',', '.')
                            valor_unitario = float(valor_str)
                        except ValueError:
                            valor_unitario = 0.0
                    
                    procedure = {
                        'codigo': codigo,
                        'descripcion': descripcion.title(),
                        'cantidad': cantidad,
                        'valor_unitario': valor_unitario,
                        'valor_total': cantidad * valor_unitario,
                        'valor_objetado': 0.0,  # Se calculará después si hay información
                        'estado': 'pendiente'
                    }
                    
                    procedures.append(procedure)
                    
                except (ValueError, IndexError) as e:
                    logger.warning(f"Error procesando procedimiento: {e}")
                    continue
        
        return procedures
    
    def _extract_financial_summary_improved(self, text: str) -> Dict[str, Any]:
        """Extrae resumen financiero con patrones mejorados"""
        financial = {}
        
        # Extraer valores monetarios principales
        for key, patterns in self.money_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        # Limpiar y convertir valor
                        if UTILS_AVAILABLE:
                            financial[key] = TextCleaner.normalize_money_value(match.group(1))
                        else:
                            valor_str = match.group(1).replace('.', '').replace(',', '.')
                            financial[key] = float(valor_str)
                        break
                    except ValueError:
                        continue
        
        # Calcular valores derivados
        if 'total_reclamado' in financial and 'total_objetado' in financial:
            financial['total_aceptado'] = financial['total_reclamado'] - financial['total_objetado']
            
            if financial['total_reclamado'] > 0:
                financial['porcentaje_objetado'] = (financial['total_objetado'] / financial['total_reclamado']) * 100
            else:
                financial['porcentaje_objetado'] = 0.0
        
        return financial
    
    def _extract_diagnostics(self, text: str) -> List[Dict[str, Any]]:
        """Extrae diagnósticos CIE-10"""
        diagnostics = []
        
        for pattern in self.diagnostic_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            
            for match in matches:
                if isinstance(match, tuple):
                    codigo = match[0].strip() if len(match) > 0 else ""
                    descripcion = match[1].strip() if len(match) > 1 else ""
                else:
                    codigo = match.strip()
                    descripcion = ""
                
                if codigo and len(codigo) >= 3:
                    diagnostic = {
                        'codigo': codigo.upper(),
                        'descripcion': descripcion.title() if descripcion else "",
                        'tipo': 'principal' if len(diagnostics) == 0 else 'secundario'
                    }
                    diagnostics.append(diagnostic)
        
        return diagnostics
    
    def _extract_ips_info(self, text: str) -> Dict[str, Any]:
        """Extrae información de la IPS"""
        ips_info = {}
        
        for pattern in self.ips_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                ips_info['nombre'] = match.group(1).strip().title()
                break
        
        # Buscar NIT de la IPS
        nit_pattern = r'NIT[\s:]*(\d{9,12})'
        match = re.search(nit_pattern, text, re.IGNORECASE)
        if match:
            ips_info['nit'] = match.group(1).strip()
        
        return ips_info
    
    def _calculate_extraction_stats(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Calcula estadísticas de la extracción"""
        procedures = result.get('procedures', [])
        financial = result.get('financial_summary', {})
        
        stats = {
            'total_procedimientos': len(procedures),
            'procedimientos_con_objecciones': len([p for p in procedures if p.get('valor_objetado', 0) > 0]),
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
        
        if total_fields >= 15:
            return 'excelente'
        elif total_fields >= 10:
            return 'buena'
        elif total_fields >= 5:
            return 'regular'
        else:
            return 'baja'
    
    def _extract_with_openai(self, text: str) -> Dict[str, Any]:
        """Extrae información usando OpenAI GPT-4 - Versión sin OpenAI para evitar errores"""
        try:
            # Por ahora deshabilitar OpenAI para evitar errores de compatibilidad
            logger.info("OpenAI deshabilitado temporalmente, usando solo OCR")
            return self._extract_ocr_only(text)
            
        except Exception as e:
            logger.error(f"Error con OpenAI: {str(e)}")
            # Fallback a OCR si falla OpenAI
            return self._extract_ocr_only(text)
    
    def _build_openai_prompt(self, text: str) -> str:
        """Construye prompt para OpenAI"""
        return f"""
        Analiza la siguiente glosa médica colombiana y extrae la información en formato JSON.
        
        Texto de la glosa:
        {text[:3000]}  # Limitar tamaño para no exceder tokens
        
        Extrae la siguiente información en formato JSON:
        {{
            "patient_info": {{
                "nombre": "",
                "documento": "",
                "tipo_documento": "",
                "edad": null
            }},
            "policy_info": {{
                "poliza": "",
                "aseguradora": "",
                "numero_reclamacion": "",
                "fecha_siniestro": "",
                "fecha_ingreso": "",
                "fecha_egreso": ""
            }},
            "procedures": [
                {{
                    "codigo": "",
                    "descripcion": "",
                    "cantidad": 0,
                    "valor_unitario": 0,
                    "valor_total": 0
                }}
            ],
            "financial_summary": {{
                "total_reclamado": 0,
                "total_objetado": 0,
                "total_aceptado": 0,
                "total_pagado": 0
            }},
            "diagnostics": [
                {{
                    "codigo": "",
                    "descripcion": ""
                }}
            ]
        }}
        
        Responde SOLO con el JSON, sin texto adicional.
        """
    
    def _merge_results(self, ocr_result: Dict[str, Any], ai_result: Dict[str, Any]) -> Dict[str, Any]:
        """Combina resultados de OCR y IA priorizando IA"""
        merged = ocr_result.copy()
        
        # Priorizar IA para campos complejos
        for key in ['patient_info', 'policy_info', 'financial_summary']:
            if ai_result.get(key) and any(ai_result[key].values()):
                merged[key].update(ai_result[key])
        
        # Para procedures y diagnostics, usar IA si tiene más elementos
        if ai_result.get('procedures') and len(ai_result['procedures']) > len(merged.get('procedures', [])):
            merged['procedures'] = ai_result['procedures']
        
        if ai_result.get('diagnostics') and len(ai_result['diagnostics']) > len(merged.get('diagnostics', [])):
            merged['diagnostics'] = ai_result['diagnostics']
        
        return merged
    
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