# apps/extractor/pdf_splitter.py

import fitz  # PyMuPDF
import os
import tempfile
import logging
from typing import List, Tuple, Optional
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

class GlosaPDFSplitter:
    """
    Divisor de PDFs de glosas médicas integrado con Django
    Basado en el código original pero optimizado para la aplicación
    """
    
    def __init__(self):
        # Palabras clave para definir las secciones
        self.start_keyword = "Víctima"
        self.end_keyword = "Valor de Reclamación:"
        
    def detect_multiple_patients(self, pdf_file_path: str) -> bool:
        """
        Detecta si un PDF contiene múltiples pacientes
        Retorna True si encuentra más de una sección
        """
        try:
            doc = fitz.open(pdf_file_path)
            start_pages, end_pages = self._detect_sections(doc)
            doc.close()
            
            # Si hay más de una página de inicio, es un documento múltiple
            return len(start_pages) > 1
            
        except Exception as e:
            logger.error(f"Error detectando múltiples pacientes: {str(e)}")
            return False
    
    def split_pdf(self, pdf_file_path: str) -> List[Tuple[bytes, str, dict]]:
        """
        Divide un PDF en secciones por paciente
        Retorna lista de tuplas (contenido_pdf, nombre_archivo, metadata)
        """
        try:
            logger.info(f"Iniciando división de PDF: {pdf_file_path}")
            
            doc = fitz.open(pdf_file_path)
            start_pages, end_pages = self._detect_sections(doc)
            sections = self._pair_sections(start_pages, end_pages)
            
            if len(sections) <= 1:
                logger.info("PDF contiene un solo paciente")
                doc.close()
                return []  # No necesita división
            
            logger.info(f"Detectadas {len(sections)} secciones de pacientes")
            
            split_pdfs = []
            
            for i, (start, end) in enumerate(sections):
                try:
                    pdf_content = self._extract_section(doc, start, end)
                    section_metadata = self._extract_section_metadata(doc, start, end)
                    
                    filename = f"section_{i+1}.pdf"
                    split_pdfs.append((pdf_content, filename, section_metadata))
                    
                    logger.debug(f"Sección {i+1} extraída: páginas {start}-{end}")
                    
                except Exception as e:
                    logger.error(f"Error extrayendo sección {i+1}: {e}")
                    continue
            
            doc.close()
            logger.info(f"División completada: {len(split_pdfs)} secciones extraídas")
            return split_pdfs
            
        except Exception as e:
            logger.error(f"Error dividiendo PDF: {str(e)}")
            raise Exception(f"Error dividiendo PDF: {str(e)}")
    
    def _detect_sections(self, doc) -> Tuple[List[int], List[int]]:
        """Detecta páginas de inicio y fin de secciones"""
        start_pages = []
        end_pages = []
        
        logger.debug(f"Analizando {len(doc)} páginas para detectar secciones")
        
        for page_num in range(len(doc)):
            try:
                text = doc[page_num].get_text("text").lower()
                
                # Buscar inicio de sección
                if self.start_keyword.lower() in text:
                    start_pages.append(page_num)
                    logger.debug(f"Inicio de sección encontrado en página {page_num}")
                
                # Buscar fin de sección
                if self.end_keyword.lower() in text:
                    end_pages.append(page_num)
                    logger.debug(f"Fin de sección encontrado en página {page_num}")
                    
            except Exception as e:
                logger.warning(f"Error analizando página {page_num}: {e}")
                continue
        
        logger.info(f"Detección completada: {len(start_pages)} inicios, {len(end_pages)} finales")
        return start_pages, end_pages
    
    def _pair_sections(self, start_pages: List[int], end_pages: List[int]) -> List[Tuple[int, int]]:
        """Empareja páginas de inicio con páginas de fin"""
        sections = []
        used_end_pages = set()
        
        logger.debug("Emparejando páginas de inicio y fin")
        
        for start_page in start_pages:
            # Buscar la siguiente página de finalización disponible
            end_page = next(
                (ep for ep in end_pages if ep >= start_page and ep not in used_end_pages), 
                None
            )
            
            if end_page is not None:
                sections.append((start_page, end_page))
                used_end_pages.add(end_page)
                logger.debug(f"Sección emparejada: páginas {start_page}-{end_page}")
            else:
                logger.warning(f"No se encontró página de fin para la sección que empieza en {start_page}")
        
        return sections
    
    def _extract_section(self, doc, start: int, end: int) -> bytes:
        """Extrae una sección específica como PDF"""
        try:
            new_pdf = fitz.open()
            
            # Insertar las páginas de la sección
            for page_num in range(start, end + 1):
                if page_num < len(doc):
                    new_pdf.insert_pdf(doc, from_page=page_num, to_page=page_num)
            
            # Convertir a bytes
            pdf_bytes = new_pdf.tobytes()
            new_pdf.close()
            
            logger.debug(f"Sección extraída: {len(pdf_bytes)} bytes")
            return pdf_bytes
            
        except Exception as e:
            logger.error(f"Error extrayendo sección páginas {start}-{end}: {e}")
            raise
    
    def _extract_section_metadata(self, doc, start: int, end: int) -> dict:
        """Extrae metadata básica de una sección"""
        metadata = {
            'start_page': start,
            'end_page': end,
            'total_pages': end - start + 1,
            'patient_hint': None
        }
        
        try:
            # Intentar extraer nombre del paciente de la primera página
            if start < len(doc):
                first_page_text = doc[start].get_text("text")
                
                # Buscar patrón de víctima
                import re
                victim_pattern = r'Víctima\s*:\s*[A-Z]{1,3}\s*-\s*\d+\s*-\s*([A-ZÁÉÍÓÚÑ\s]+?)(?:\n|\r|Número)'
                match = re.search(victim_pattern, first_page_text, re.IGNORECASE)
                
                if match:
                    patient_name = match.group(1).strip()
                    metadata['patient_hint'] = patient_name
                    logger.debug(f"Paciente detectado: {patient_name}")
        
        except Exception as e:
            logger.warning(f"Error extrayendo metadata de sección: {e}")
        
        return metadata
    
    def validate_pdf_format(self, pdf_file_path: str) -> Tuple[bool, str]:
        """
        Valida que el PDF tenga el formato esperado de glosa SOAT
        Retorna (es_válido, mensaje)
        """
        try:
            doc = fitz.open(pdf_file_path)
            
            # Buscar indicadores de glosa SOAT en las primeras páginas
            soat_indicators = [
                "liquidación de siniestros soat",
                "seguros mundial",
                "víctima",
                "reclamación",
                "póliza"
            ]
            
            text_found = ""
            for page_num in range(min(3, len(doc))):  # Revisar primeras 3 páginas
                page_text = doc[page_num].get_text("text").lower()
                text_found += page_text + " "
            
            doc.close()
            
            # Verificar que contenga al menos 3 indicadores
            indicators_found = sum(1 for indicator in soat_indicators if indicator in text_found)
            
            if indicators_found >= 3:
                return True, "Formato de glosa SOAT válido"
            else:
                return False, f"Formato no reconocido como glosa SOAT (indicadores: {indicators_found}/5)"
                
        except Exception as e:
            return False, f"Error validando PDF: {str(e)}"
    
    def get_pdf_info(self, pdf_file_path: str) -> dict:
        """Obtiene información general del PDF"""
        try:
            doc = fitz.open(pdf_file_path)
            
            info = {
                'total_pages': len(doc),
                'file_size': os.path.getsize(pdf_file_path),
                'is_valid': True,
                'error': None
            }
            
            # Detectar secciones
            start_pages, end_pages = self._detect_sections(doc)
            info['sections_detected'] = len(start_pages)
            info['is_multi_patient'] = len(start_pages) > 1
            
            doc.close()
            return info
            
        except Exception as e:
            return {
                'total_pages': 0,
                'file_size': 0,
                'is_valid': False,
                'error': str(e),
                'sections_detected': 0,
                'is_multi_patient': False
            }