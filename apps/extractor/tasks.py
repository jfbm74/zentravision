# apps/extractor/tasks.py - CORRECCIÓN DEL ERROR .get()

from celery import shared_task
from django.utils import timezone
from django.core.files.base import ContentFile
from django.conf import settings
import json
import csv
import io
import traceback
import logging
from apps.core.models import GlosaDocument, ProcessingLog, ProcessingBatch
from .medical_claim_extractor_fixed import MedicalClaimExtractor

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def process_batch_documents(self, batch_id):
    """
    Tarea principal para procesar todos los documentos de un batch
    CORREGIDO: Sin usar .get() dentro de tareas
    """
    try:
        logger.info(f"Iniciando procesamiento de batch {batch_id}")
        
        batch = ProcessingBatch.objects.get(id=batch_id)
        batch.batch_status = 'processing'
        batch.save()
        
        master_document = batch.master_document
        
        ProcessingLog.objects.create(
            glosa=master_document,
            level='INFO',
            message=f'Iniciando procesamiento de batch con {batch.total_documents} documentos'
        )
        
        # Obtener documentos hijos
        child_documents = master_document.child_documents.all().order_by('patient_section_number')
        
        if not child_documents.exists():
            raise Exception("No se encontraron documentos hijos para procesar")
        
        # CORREGIDO: Procesar cada documento de forma síncrona dentro de la tarea
        for child_glosa in child_documents:
            try:
                logger.info(f"Procesando documento hijo {child_glosa.id} (sección {child_glosa.patient_section_number})")
                
                # CAMBIO: Llamar directamente a la función sin .get()
                success = process_single_glosa_sync(child_glosa.id)
                
                # Actualizar contadores del batch
                if success:
                    batch.completed_documents += 1
                    ProcessingLog.objects.create(
                        glosa=master_document,
                        level='INFO',
                        message=f'Documento {child_glosa.patient_section_number} completado exitosamente'
                    )
                else:
                    batch.failed_documents += 1
                    ProcessingLog.objects.create(
                        glosa=master_document,
                        level='ERROR',
                        message=f'Error procesando documento {child_glosa.patient_section_number}'
                    )
                
                batch.save()
                
            except Exception as e:
                logger.error(f"Error procesando documento hijo {child_glosa.id}: {e}")
                
                # Marcar documento como error
                child_glosa.status = 'error'
                child_glosa.error_message = str(e)
                child_glosa.save()
                
                # Actualizar batch
                batch.failed_documents += 1
                batch.save()
                
                ProcessingLog.objects.create(
                    glosa=master_document,
                    level='ERROR',
                    message=f'Error procesando documento {child_glosa.patient_section_number}: {str(e)}'
                )
        
        # Finalizar batch
        batch.update_progress()  # Esto actualiza estados finales
        
        # Log final
        ProcessingLog.objects.create(
            glosa=master_document,
            level='INFO',
            message=f'Batch completado: {batch.completed_documents} exitosos, {batch.failed_documents} fallidos'
        )
        
        logger.info(f"Batch {batch_id} completado: {batch.completed_documents}/{batch.total_documents} exitosos")
        
        return {
            'batch_id': str(batch_id),
            'completed': batch.completed_documents,
            'failed': batch.failed_documents,
            'total': batch.total_documents,
            'status': batch.batch_status
        }
        
    except ProcessingBatch.DoesNotExist:
        logger.error(f"Batch {batch_id} no encontrado")
        return {'error': 'Batch no encontrado'}
        
    except Exception as e:
        logger.error(f"Error crítico en batch {batch_id}: {e}")
        
        try:
            batch = ProcessingBatch.objects.get(id=batch_id)
            batch.batch_status = 'error'
            batch.error_message = str(e)
            batch.save()
            
            ProcessingLog.objects.create(
                glosa=batch.master_document,
                level='ERROR',
                message=f'Error crítico en batch: {str(e)}'
            )
        except:
            pass
        
        # Re-lanzar excepción para Celery
        raise self.retry(exc=e, countdown=60, max_retries=2)

def process_single_glosa_sync(glosa_id):
    """
    NUEVA FUNCIÓN: Procesa un documento de forma síncrona sin ser una tarea Celery
    """
    try:
        logger.info(f"Procesando documento individual {glosa_id}")
        
        # Obtener documento
        glosa = GlosaDocument.objects.get(id=glosa_id)
        glosa.status = 'processing'
        glosa.save()
        
        # Log inicio
        ProcessingLog.objects.create(
            glosa=glosa,
            level='INFO',
            message='Iniciando extracción de datos'
        )
        
        # Verificar que el archivo existe
        if not glosa.original_file or not glosa.original_file.path:
            raise Exception("Archivo no encontrado")
        
        # Inicializar extractor
        openai_api_key = getattr(settings, 'OPENAI_API_KEY', None)
        extractor = MedicalClaimExtractor(openai_api_key=openai_api_key)
        
        # Determinar estrategia
        strategy = glosa.strategy if hasattr(glosa, 'strategy') else 'hybrid'
        
        ProcessingLog.objects.create(
            glosa=glosa,
            level='INFO',
            message=f'Extrayendo datos con estrategia: {strategy}'
        )
        
        # Procesar documento
        start_time = timezone.now()
        result = extractor.extract_from_pdf(glosa.original_file.path, strategy=strategy)
        end_time = timezone.now()
        
        processing_time = (end_time - start_time).total_seconds()
        
        # Verificar resultados
        if result.get('error'):
            raise Exception(f"Error en extracción: {result['error']}")
        
        # Guardar datos extraídos
        glosa.extracted_data = result
        glosa.status = 'completed'
        glosa.updated_at = timezone.now()
        glosa.save()
        
        # Log de éxito
        extraction_stats = result.get('extraction_details', {})
        ProcessingLog.objects.create(
            glosa=glosa,
            level='INFO',
            message=f'Procesamiento completado en {processing_time:.2f}s. '
                   f'Campos extraídos: {extraction_stats.get("campos_extraidos", 0)}, '
                   f'Calidad: {extraction_stats.get("calidad_extraccion", "desconocida")}'
        )
        
        logger.info(f"Documento {glosa_id} procesado exitosamente en {processing_time:.2f}s")
        return True
        
    except GlosaDocument.DoesNotExist:
        logger.error(f"Documento {glosa_id} no encontrado")
        return False
        
    except Exception as e:
        logger.error(f"Error procesando documento {glosa_id}: {str(e)}")
        
        try:
            glosa = GlosaDocument.objects.get(id=glosa_id)
            glosa.status = 'error'
            glosa.error_message = str(e)
            glosa.save()
            
            ProcessingLog.objects.create(
                glosa=glosa,
                level='ERROR',
                message=f'Error en procesamiento: {str(e)}'
            )
        except:
            pass
        
        return False

@shared_task(bind=True)
def process_single_glosa_document(self, glosa_id):
    """
    Tarea para procesar un documento individual de glosa
    CORREGIDO: Sin usar .get()
    """
    return process_single_glosa_sync(glosa_id)

@shared_task(bind=True)
def process_glosa_document(self, glosa_id):
    """
    Tarea asíncrona heredada del sistema anterior
    Mantiene compatibilidad con documentos ya existentes
    """
    try:
        return process_single_glosa_sync(glosa_id)
        
    except Exception as exc:
        logger.error(f"Error en tarea legacy {glosa_id}: {str(exc)}")
        raise self.retry(exc=exc, countdown=60, max_retries=3)

# Resto de funciones sin cambios...
@shared_task
def cleanup_orphaned_files():
    """Tarea de mantenimiento para limpiar archivos huérfanos"""
    try:
        from django.core.files.storage import default_storage
        import os
        
        logger.info("Iniciando limpieza de archivos huérfanos")
        
        # Buscar documentos con archivos faltantes
        glosas_with_missing_files = []
        
        for glosa in GlosaDocument.objects.all():
            if glosa.original_file:
                if not default_storage.exists(glosa.original_file.name):
                    glosas_with_missing_files.append(glosa.id)
        
        if glosas_with_missing_files:
            logger.warning(f"Encontrados {len(glosas_with_missing_files)} documentos con archivos faltantes")
        
        logger.info("Limpieza de archivos completada")
        
        return {
            'missing_files': len(glosas_with_missing_files),
            'cleaned_files': 0
        }
        
    except Exception as e:
        logger.error(f"Error en limpieza de archivos: {e}")
        return {'error': str(e)}

@shared_task
def generate_batch_report(batch_id):
    """Genera un reporte completo de un batch procesado"""
    try:
        batch = ProcessingBatch.objects.get(id=batch_id)
        
        if not batch.is_complete:
            return {'error': 'Batch no completado aún'}
        
        # Recopilar estadísticas
        child_documents = batch.master_document.child_documents.all()
        
        report = {
            'batch_id': str(batch_id),
            'master_document': batch.master_document.original_filename,
            'total_documents': batch.total_documents,
            'completed_documents': batch.completed_documents,
            'failed_documents': batch.failed_documents,
            'success_rate': (batch.completed_documents / batch.total_documents * 100) if batch.total_documents > 0 else 0,
            'processing_time': None,
            'total_procedures': 0,
            'total_amount': 0,
            'total_objected': 0,
            'patients': []
        }
        
        if batch.completed_at and batch.created_at:
            processing_time = (batch.completed_at - batch.created_at).total_seconds()
            report['processing_time'] = processing_time
        
        # Procesar cada documento hijo
        for child_doc in child_documents.filter(status='completed'):
            patient_data = {
                'section_number': child_doc.patient_section_number,
                'filename': child_doc.original_filename,
                'status': child_doc.status,
                'procedures_count': 0,
                'total_amount': 0,
                'objected_amount': 0,
                'patient_name': 'N/A'
            }
            
            if child_doc.extracted_data:
                # Información del paciente
                patient_info = child_doc.extracted_data.get('patient_info', {})
                patient_data['patient_name'] = patient_info.get('nombre', 'N/A')
                
                # Información financiera
                financial = child_doc.extracted_data.get('financial_summary', {})
                patient_data['total_amount'] = financial.get('total_reclamado', 0)
                patient_data['objected_amount'] = financial.get('total_objetado', 0)
                
                # Procedimientos
                procedures = child_doc.extracted_data.get('procedures', [])
                patient_data['procedures_count'] = len(procedures)
                
                # Sumar a totales
                report['total_procedures'] += len(procedures)
                report['total_amount'] += patient_data['total_amount']
                report['total_objected'] += patient_data['objected_amount']
            
            report['patients'].append(patient_data)
        
        logger.info(f"Reporte generado para batch {batch_id}")
        return report
        
    except ProcessingBatch.DoesNotExist:
        return {'error': 'Batch no encontrado'}
    except Exception as e:
        logger.error(f"Error generando reporte de batch {batch_id}: {e}")
        return {'error': str(e)}

@shared_task
def update_batch_progress():
    """Tarea periódica para actualizar el progreso de batches activos"""
    try:
        active_batches = ProcessingBatch.objects.filter(
            batch_status__in=['splitting', 'processing']
        )
        
        updated_count = 0
        
        for batch in active_batches:
            try:
                batch.update_progress()
                updated_count += 1
            except Exception as e:
                logger.error(f"Error actualizando batch {batch.id}: {e}")
                continue
        
        logger.info(f"Actualizados {updated_count} batches activos")
        return {'updated_batches': updated_count}
        
    except Exception as e:
        logger.error(f"Error en actualización de batches: {e}")
        return {'error': str(e)}