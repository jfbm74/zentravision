# ==========================================
# apps/extractor/tasks.py
# ==========================================

from celery import shared_task
from django.utils import timezone
from django.core.files.base import ContentFile
import json
import csv
import io
import traceback
from apps.core.models import GlosaDocument, ProcessingLog
from .medical_claim_extractor import MedicalClaimExtractor

@shared_task(bind=True)
def process_glosa_document(self, glosa_id):
    """Tarea asíncrona para procesar documento de glosa"""
    
    try:
        # Obtener documento
        glosa = GlosaDocument.objects.get(id=glosa_id)
        glosa.status = 'processing'
        glosa.save()
        
        # Log inicio
        ProcessingLog.objects.create(
            glosa=glosa,
            level='INFO',
            message='Iniciando procesamiento del documento'
        )
        
        # Inicializar extractor
        extractor = MedicalClaimExtractor(strategy=glosa.strategy)
        
        # Procesar documento
        start_time = timezone.now()
        extracted_glosa = extractor.extract_from_pdf(glosa.original_file.path)
        end_time = timezone.now()
        
        processing_time = (end_time - start_time).total_seconds()
        
        # Convertir a diccionario para JSON
        extracted_data = {
            'header': extracted_glosa.header.__dict__,
            'detalles': [detalle.__dict__ for detalle in extracted_glosa.detalles],
            'totales': {
                'valor_reclamacion': extracted_glosa.valor_reclamacion,
                'valor_nota_credito': extracted_glosa.valor_nota_credito,
                'valor_aceptado_ips_anterior': extracted_glosa.valor_aceptado_ips_anterior,
                'valor_aceptado_ips_actual': extracted_glosa.valor_aceptado_ips_actual,
                'valor_objetado_anterior': extracted_glosa.valor_objetado_anterior,
                'valor_objetado_actual': extracted_glosa.valor_objetado_actual,
                'valor_pagado_acumulado': extracted_glosa.valor_pagado_acumulado,
                'valor_impuestos': extracted_glosa.valor_impuestos,
                'valor_pagado_actual': extracted_glosa.valor_pagado_actual,
            },
            'metadata': {
                'fecha_procesamiento': timezone.now().isoformat(),
                'estrategia_usada': glosa.strategy,
                'tiempo_procesamiento': processing_time,
            }
        }
        
        # Guardar JSON
        json_content = json.dumps(extracted_data, indent=2, ensure_ascii=False)
        json_file = ContentFile(json_content.encode('utf-8'))
        glosa.json_output.save(
            f'glosa_{glosa_id}.json',
            json_file,
            save=False
        )
        
        # Guardar CSV (header)
        csv_buffer = io.StringIO()
        if extracted_glosa.detalles:
            fieldnames = extracted_glosa.detalles[0].__dict__.keys()
            writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
            writer.writeheader()
            for detalle in extracted_glosa.detalles:
                writer.writerow(detalle.__dict__)
        
        csv_content = csv_buffer.getvalue()
        csv_file = ContentFile(csv_content.encode('utf-8'))
        glosa.csv_output.save(
            f'glosa_{glosa_id}.csv',
            csv_file,
            save=False
        )
        
        # Actualizar modelo
        glosa.extracted_data = extracted_data
        glosa.status = 'completed'
        glosa.processed_at = timezone.now()
        glosa.processing_time = processing_time
        glosa.save()
        
        # Log éxito
        ProcessingLog.objects.create(
            glosa=glosa,
            level='INFO',
            message=f'Documento procesado exitosamente en {processing_time:.2f} segundos',
            extra_data={
                'detalles_count': len(extracted_glosa.detalles),
                'valor_reclamacion': extracted_glosa.valor_reclamacion,
            }
        )
        
        return f"Documento {glosa_id} procesado exitosamente"
        
    except Exception as exc:
        # Manejo de errores
        error_message = str(exc)
        error_traceback = traceback.format_exc()
        
        try:
            glosa = GlosaDocument.objects.get(id=glosa_id)
            glosa.status = 'error'
            glosa.error_message = error_message
            glosa.save()
            
            ProcessingLog.objects.create(
                glosa=glosa,
                level='ERROR',
                message=f'Error en procesamiento: {error_message}',
                extra_data={'traceback': error_traceback}
            )
        except:
            pass
        
        # Re-lanzar excepción para Celery
        raise self.retry(exc=exc, countdown=60, max_retries=3)
