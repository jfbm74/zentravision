# apps/extractor/utils.py
"""
Utilidades y funciones de apoyo para el extractor de glosas médicas
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class ColombianMedicalPatterns:
    """
    Patrones específicos para documentos médicos colombianos
    """
    
    # Códigos CUPS más comunes en glosas colombianas
    COMMON_CUPS_CODES = {
        # Procedimientos quirúrgicos
        '474101': 'COLECISTECTOMÍA LAPAROSCÓPICA',
        '474201': 'APENDICECTOMÍA LAPAROSCÓPICA',
        '474301': 'HERNIOPLASTIA LAPAROSCÓPICA',
        
        # Hospitalización
        '203001': 'HOSPITALIZACIÓN EN HABITACIÓN GENERAL',
        '203002': 'HOSPITALIZACIÓN EN UNIDAD DE CUIDADOS INTERMEDIOS',
        '203003': 'HOSPITALIZACIÓN EN UNIDAD DE CUIDADOS INTENSIVOS',
        
        # Honorarios médicos
        '301001': 'HONORARIOS MÉDICOS CIRUJANO',
        '301002': 'HONORARIOS MÉDICOS ESPECIALISTA',
        '301003': 'HONORARIOS MÉDICOS ANESTESIÓLOGO',
        
        # Ayudas diagnósticas
        '901001': 'TOMOGRAFÍA AXIAL COMPUTARIZADA',
        '901002': 'RESONANCIA MAGNÉTICA NUCLEAR',
        '901003': 'ECOGRAFÍA ABDOMINAL',
        
        # Medicamentos
        '401001': 'MEDICAMENTOS HOSPITALARIOS',
        '401002': 'MEDICAMENTOS AMBULATORIOS',
        
        # Materiales quirúrgicos
        '501001': 'MATERIALES QUIRÚRGICOS',
        '501002': 'IMPLANTES MÉDICOS',
    }
    
    # Aseguradoras colombianas más comunes
    COLOMBIAN_INSURERS = [
        'SURAMERICANA',
        'BOLIVAR',
        'MAPFRE',
        'AXA COLPATRIA',
        'LIBERTY SEGUROS',
        'MUNDIAL',
        'PREVISORA SEGUROS',
        'COLMENA SEGUROS',
        'EQUIDAD SEGUROS',
        'ALLIANZ',
        'ZURICH'
    ]
    
    # IPS más reconocidas en Colombia
    MAJOR_IPS = [
        'CLÍNICA VALLE DEL LILI',
        'FUNDACIÓN CARDIOINFANTIL',
        'HOSPITAL SAN IGNACIO',
        'CLÍNICA SHAIO',
        'HOSPITAL MILITAR CENTRAL',
        'CLÍNICA COUNTRY',
        'CLÍNICA REINA SOFÍA',
        'HOSPITAL PABLO TOBÓN URIBE',
        'CLÍNICA LAS AMÉRICAS',
        'HOSPITAL GENERAL DE MEDELLÍN'
    ]

class TextCleaner:
    """
    Utilidades para limpiar y normalizar texto de glosas médicas
    """
    
    @staticmethod
    def clean_medical_text(text: str) -> str:
        """Limpia texto específicamente para documentos médicos"""
        if not text:
            return ""
        
        # Remover caracteres especiales problemáticos
        text = re.sub(r'[^\w\s\.\,\:\;\-\$\(\)\/\%]', ' ', text)
        
        # Normalizar espacios múltiples
        text = re.sub(r'\s+', ' ', text)
        
        # Normalizar separadores de miles y decimales
        text = re.sub(r'(\d+)\.(\d{3})', r'\1\2', text)  # Remover puntos como separadores de miles
        
        # Convertir a mayúsculas para mejor matching
        text = text.upper().strip()
        
        return text
    
    @staticmethod
    def normalize_money_value(value_str: str) -> float:
        """Normaliza valores monetarios colombianos"""
        if not value_str:
            return 0.0
        
        try:
            # Remover símbolos de moneda y espacios
            clean_value = re.sub(r'[\$\s]', '', str(value_str))
            
            # Manejar separadores de miles (puntos) y decimales (comas)
            if ',' in clean_value:
                # Si hay coma, asumir que es separador decimal
                clean_value = clean_value.replace('.', '').replace(',', '.')
            else:
                # Si no hay coma, asumir que los puntos son separadores de miles
                clean_value = clean_value.replace('.', '')
            
            return float(clean_value)
        except (ValueError, TypeError):
            return 0.0
    
    @staticmethod
    def normalize_date(date_str: str) -> Optional[str]:
        """Normaliza fechas en formato colombiano"""
        if not date_str:
            return None
        
        # Patrones de fecha comunes en Colombia
        date_patterns = [
            r'(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})',  # DD/MM/YYYY o DD-MM-YYYY
            r'(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})',  # YYYY/MM/DD o YYYY-MM-DD
            r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})',   # DD de MMMM de YYYY
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, date_str, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    # Intentar formatear como YYYY-MM-DD
                    try:
                        if len(groups[2]) == 4:  # Formato DD/MM/YYYY
                            return f"{groups[2]}-{groups[1].zfill(2)}-{groups[0].zfill(2)}"
                        elif len(groups[0]) == 4:  # Formato YYYY/MM/DD
                            return f"{groups[0]}-{groups[1].zfill(2)}-{groups[2].zfill(2)}"
                    except:
                        pass
        
        return date_str  # Retornar original si no se puede normalizar

class MedicalValidator:
    """
    Validadores para datos médicos extraídos
    """
    
    @staticmethod
    def validate_cups_code(code: str) -> bool:
        """Valida código CUPS colombiano"""
        if not code:
            return False
        
        # CUPS debe tener 6 dígitos
        return re.match(r'^\d{6}$', str(code)) is not None
    
    @staticmethod
    def validate_cie10_code(code: str) -> bool:
        """Valida código CIE-10"""
        if not code:
            return False
        
        # CIE-10: Letra + 2 dígitos + opcionalmente punto y dígito
        return re.match(r'^[A-Z]\d{2}\.?\d?$', str(code).upper()) is not None
    
    @staticmethod
    def validate_colombian_id(document: str, doc_type: str = 'CC') -> bool:
        """Valida documento de identidad colombiano"""
        if not document:
            return False
        
        document = str(document).strip()
        
        if doc_type.upper() == 'CC':
            # Cédula de ciudadanía: 6-10 dígitos
            return re.match(r'^\d{6,10}$', document) is not None
        elif doc_type.upper() == 'NIT':
            # NIT: 9-12 dígitos
            return re.match(r'^\d{9,12}$', document) is not None
        elif doc_type.upper() == 'TI':
            # Tarjeta de identidad: 8-11 dígitos
            return re.match(r'^\d{8,11}$', document) is not None
        
        return len(document) >= 6  # Validación genérica
    
    @staticmethod
    def validate_money_amount(amount) -> bool:
        """Valida que un monto sea razonable para glosas médicas"""
        try:
            value = float(amount)
            # Montos entre $1,000 y $500,000,000 COP son razonables para glosas
            return 1000 <= value <= 500000000
        except (ValueError, TypeError):
            return False

class ExtractionEnhancer:
    """
    Mejora los resultados de extracción usando conocimiento específico
    """
    
    @staticmethod
    def enhance_procedure_descriptions(procedures: List[Dict]) -> List[Dict]:
        """Mejora descripciones de procedimientos usando códigos CUPS conocidos"""
        enhanced = []
        
        for proc in procedures:
            enhanced_proc = proc.copy()
            code = proc.get('codigo', '').strip()
            
            # Si el código está en nuestra base de datos, mejorar descripción
            if code in ColombianMedicalPatterns.COMMON_CUPS_CODES:
                known_desc = ColombianMedicalPatterns.COMMON_CUPS_CODES[code]
                current_desc = proc.get('descripcion', '').strip()
                
                # Si la descripción actual está vacía o es muy corta, usar la conocida
                if not current_desc or len(current_desc) < 10:
                    enhanced_proc['descripcion'] = known_desc
                    enhanced_proc['descripcion_mejorada'] = True
            
            # Validar y limpiar valores monetarios
            for money_field in ['valor_unitario', 'valor_total', 'valor_objetado']:
                if money_field in enhanced_proc:
                    cleaned_value = TextCleaner.normalize_money_value(enhanced_proc[money_field])
                    enhanced_proc[money_field] = cleaned_value
            
            # Validar código CUPS
            enhanced_proc['codigo_valido'] = MedicalValidator.validate_cups_code(code)
            
            enhanced.append(enhanced_proc)
        
        return enhanced
    
    @staticmethod
    def enhance_patient_info(patient_info: Dict) -> Dict:
        """Mejora información del paciente"""
        enhanced = patient_info.copy()
        
        # Normalizar nombre (título case)
        if 'nombre' in enhanced:
            nombre = enhanced['nombre'].strip()
            if nombre:
                enhanced['nombre'] = ' '.join(word.capitalize() for word in nombre.split())
        
        # Validar documento
        if 'documento' in enhanced and 'tipo_documento' in enhanced:
            doc_valid = MedicalValidator.validate_colombian_id(
                enhanced['documento'], 
                enhanced.get('tipo_documento', 'CC')
            )
            enhanced['documento_valido'] = doc_valid
        
        return enhanced
    
    @staticmethod
    def enhance_financial_summary(financial: Dict) -> Dict:
        """Mejora resumen financiero con cálculos adicionales"""
        enhanced = financial.copy()
        
        # Normalizar todos los valores monetarios
        money_fields = ['total_reclamado', 'total_objetado', 'total_aceptado', 'total_pagado']
        for field in money_fields:
            if field in enhanced:
                enhanced[field] = TextCleaner.normalize_money_value(enhanced[field])
        
        # Calcular valores derivados
        total_reclamado = enhanced.get('total_reclamado', 0)
        total_objetado = enhanced.get('total_objetado', 0)
        
        if total_reclamado > 0:
            # Calcular total aceptado si no existe
            if 'total_aceptado' not in enhanced:
                enhanced['total_aceptado'] = total_reclamado - total_objetado
            
            # Calcular porcentajes
            enhanced['porcentaje_objetado'] = round((total_objetado / total_reclamado) * 100, 2)
            enhanced['porcentaje_aceptado'] = round(((total_reclamado - total_objetado) / total_reclamado) * 100, 2)
        
        # Validar montos
        enhanced['montos_validos'] = all(
            MedicalValidator.validate_money_amount(enhanced.get(field, 0))
            for field in money_fields
            if field in enhanced
        )
        
        return enhanced
    
    @staticmethod
    def enhance_diagnostics(diagnostics: List[Dict]) -> List[Dict]:
        """Mejora información de diagnósticos"""
        enhanced = []
        
        for diag in diagnostics:
            enhanced_diag = diag.copy()
            codigo = diag.get('codigo', '').strip().upper()
            
            # Validar código CIE-10
            enhanced_diag['codigo_valido'] = MedicalValidator.validate_cie10_code(codigo)
            enhanced_diag['codigo'] = codigo
            
            # Categorizar diagnóstico
            if codigo:
                enhanced_diag['categoria'] = ExtractionEnhancer._categorize_cie10(codigo)
            
            enhanced.append(enhanced_diag)
        
        return enhanced
    
    @staticmethod
    def _categorize_cie10(code: str) -> str:
        """Categoriza códigos CIE-10 por capítulos"""
        if not code or len(code) < 3:
            return 'Desconocido'
        
        letter = code[0].upper()
        
        categories = {
            'A': 'Enfermedades infecciosas y parasitarias',
            'B': 'Enfermedades infecciosas y parasitarias',
            'C': 'Neoplasias',
            'D': 'Enfermedades de la sangre y trastornos inmunitarios',
            'E': 'Enfermedades endocrinas, nutricionales y metabólicas',
            'F': 'Trastornos mentales y del comportamiento',
            'G': 'Enfermedades del sistema nervioso',
            'H': 'Enfermedades del ojo y anexos / oído',
            'I': 'Enfermedades del sistema circulatorio',
            'J': 'Enfermedades del sistema respiratorio',
            'K': 'Enfermedades del sistema digestivo',
            'L': 'Enfermedades de la piel y tejido subcutáneo',
            'M': 'Enfermedades del sistema musculoesquelético',
            'N': 'Enfermedades del sistema genitourinario',
            'O': 'Embarazo, parto y puerperio',
            'P': 'Afecciones originadas en el período perinatal',
            'Q': 'Malformaciones congénitas',
            'R': 'Síntomas y signos no clasificados',
            'S': 'Traumatismos y envenenamientos',
            'T': 'Traumatismos y envenenamientos',
            'V': 'Causas externas de morbilidad y mortalidad',
            'W': 'Causas externas de morbilidad y mortalidad',
            'X': 'Causas externas de morbilidad y mortalidad',
            'Y': 'Causas externas de morbilidad y mortalidad',
            'Z': 'Factores que influyen en el estado de salud'
        }
        
        return categories.get(letter, 'Desconocido')

class QualityAssessment:
    """
    Evalúa la calidad de la extracción de datos
    """
    
    @staticmethod
    def assess_extraction_quality(extraction_result: Dict) -> Dict:
        """Evalúa la calidad general de la extracción"""
        
        scores = {}
        
        # Evaluar información del paciente
        patient_score = QualityAssessment._assess_patient_quality(
            extraction_result.get('patient_info', {})
        )
        scores['patient_info'] = patient_score
        
        # Evaluar información de póliza
        policy_score = QualityAssessment._assess_policy_quality(
            extraction_result.get('policy_info', {})
        )
        scores['policy_info'] = policy_score
        
        # Evaluar procedimientos
        procedures_score = QualityAssessment._assess_procedures_quality(
            extraction_result.get('procedures', [])
        )
        scores['procedures'] = procedures_score
        
        # Evaluar información financiera
        financial_score = QualityAssessment._assess_financial_quality(
            extraction_result.get('financial_summary', {})
        )
        scores['financial_summary'] = financial_score
        
        # Calcular score general
        total_score = sum(scores.values()) / len(scores) if scores else 0
        
        return {
            'scores_por_seccion': scores,
            'score_general': round(total_score, 2),
            'calidad': QualityAssessment._classify_quality(total_score),
            'recomendaciones': QualityAssessment._generate_recommendations(scores)
        }
    
    @staticmethod
    def _assess_patient_quality(patient_info: Dict) -> float:
        """Evalúa calidad de información del paciente"""
        score = 0
        max_score = 4
        
        # Nombre presente y válido
        if patient_info.get('nombre') and len(patient_info['nombre'].strip()) > 3:
            score += 1
        
        # Documento presente y válido
        if patient_info.get('documento'):
            doc_type = patient_info.get('tipo_documento', 'CC')
            if MedicalValidator.validate_colombian_id(patient_info['documento'], doc_type):
                score += 1
        
        # Tipo de documento presente
        if patient_info.get('tipo_documento'):
            score += 1
        
        # Edad presente y razonable
        edad = patient_info.get('edad')
        if edad and isinstance(edad, (int, float)) and 0 <= edad <= 120:
            score += 1
        
        return (score / max_score) * 100
    
    @staticmethod
    def _assess_policy_quality(policy_info: Dict) -> float:
        """Evalúa calidad de información de póliza"""
        score = 0
        max_score = 5
        
        # Número de póliza
        if policy_info.get('poliza'):
            score += 1
        
        # Aseguradora
        if policy_info.get('aseguradora'):
            score += 1
        
        # Número de reclamación
        if policy_info.get('numero_reclamacion'):
            score += 1
        
        # Fechas importantes
        if policy_info.get('fecha_siniestro'):
            score += 1
        
        if policy_info.get('fecha_ingreso'):
            score += 1
        
        return (score / max_score) * 100
    
    @staticmethod
    def _assess_procedures_quality(procedures: List[Dict]) -> float:
        """Evalúa calidad de información de procedimientos"""
        if not procedures:
            return 0
        
        valid_procedures = 0
        
        for proc in procedures:
            proc_score = 0
            max_proc_score = 4
            
            # Código CUPS válido
            if MedicalValidator.validate_cups_code(proc.get('codigo')):
                proc_score += 1
            
            # Descripción presente
            if proc.get('descripcion') and len(proc['descripcion'].strip()) > 5:
                proc_score += 1
            
            # Cantidad válida
            cantidad = proc.get('cantidad', 0)
            if isinstance(cantidad, (int, float)) and cantidad > 0:
                proc_score += 1
            
            # Valor monetario válido
            if MedicalValidator.validate_money_amount(proc.get('valor_total', 0)):
                proc_score += 1
            
            # Considerar procedimiento válido si tiene al menos 50% de score
            if proc_score / max_proc_score >= 0.5:
                valid_procedures += 1
        
        return (valid_procedures / len(procedures)) * 100
    
    @staticmethod
    def _assess_financial_quality(financial: Dict) -> float:
        """Evalúa calidad de información financiera"""
        score = 0
        max_score = 4
        
        # Total reclamado presente y válido
        if MedicalValidator.validate_money_amount(financial.get('total_reclamado', 0)):
            score += 1
        
        # Total objetado presente
        if 'total_objetado' in financial:
            score += 1
        
        # Coherencia entre valores
        total_rec = financial.get('total_reclamado', 0)
        total_obj = financial.get('total_objetado', 0)
        if total_rec >= total_obj >= 0:
            score += 1
        
        # Al menos 3 campos financieros presentes
        financial_fields = ['total_reclamado', 'total_objetado', 'total_aceptado', 'total_pagado']
        present_fields = sum(1 for field in financial_fields if field in financial and financial[field])
        if present_fields >= 3:
            score += 1
        
        return (score / max_score) * 100
    
    @staticmethod
    def _classify_quality(score: float) -> str:
        """Clasifica la calidad basada en el score"""
        if score >= 85:
            return 'excelente'
        elif score >= 70:
            return 'buena'
        elif score >= 50:
            return 'regular'
        elif score >= 30:
            return 'baja'
        else:
            return 'muy_baja'
    
    @staticmethod
    def _generate_recommendations(scores: Dict) -> List[str]:
        """Genera recomendaciones para mejorar la extracción"""
        recommendations = []
        
        if scores.get('patient_info', 0) < 70:
            recommendations.append("Mejorar extracción de datos del paciente (nombre, documento)")
        
        if scores.get('policy_info', 0) < 70:
            recommendations.append("Verificar información de póliza y fechas importantes")
        
        if scores.get('procedures', 0) < 70:
            recommendations.append("Revisar códigos CUPS y valores de procedimientos")
        
        if scores.get('financial_summary', 0) < 70:
            recommendations.append("Validar coherencia de valores financieros")
        
        if not recommendations:
            recommendations.append("Extracción de buena calidad, sin mejoras críticas necesarias")
        
        return recommendations

# Función principal para mejorar resultados de extracción
def enhance_extraction_results(extraction_result: Dict) -> Dict:
    """
    Función principal que mejora todos los aspectos de los resultados extraídos
    """
    enhanced_result = extraction_result.copy()
    
    # Mejorar cada sección
    if 'patient_info' in enhanced_result:
        enhanced_result['patient_info'] = ExtractionEnhancer.enhance_patient_info(
            enhanced_result['patient_info']
        )
    
    if 'procedures' in enhanced_result:
        enhanced_result['procedures'] = ExtractionEnhancer.enhance_procedure_descriptions(
            enhanced_result['procedures']
        )
    
    if 'financial_summary' in enhanced_result:
        enhanced_result['financial_summary'] = ExtractionEnhancer.enhance_financial_summary(
            enhanced_result['financial_summary']
        )
    
    if 'diagnostics' in enhanced_result:
        enhanced_result['diagnostics'] = ExtractionEnhancer.enhance_diagnostics(
            enhanced_result['diagnostics']
        )
    
    # Evaluar calidad
    quality_assessment = QualityAssessment.assess_extraction_quality(enhanced_result)
    enhanced_result['quality_assessment'] = quality_assessment
    
    # Actualizar extraction_details con información mejorada
    if 'extraction_details' not in enhanced_result:
        enhanced_result['extraction_details'] = {}
    
    enhanced_result['extraction_details'].update({
        'calidad_extraccion': quality_assessment['calidad'],
        'score_calidad': quality_assessment['score_general'],
        'mejoras_aplicadas': True,
        'recomendaciones': quality_assessment['recomendaciones']
    })
    
    return enhanced_result