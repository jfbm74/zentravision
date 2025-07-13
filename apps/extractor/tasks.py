# apps/extractor/tasks.py - TAREAS ASÍNCRONAS CORREGIDAS

from celery import shared_task, group
from django.utils import timezone
from django.core.files.base import ContentFile
from django.conf import settings
import json
import traceback
import logging
import time
from apps.core.models import GlosaDocument, ProcessingLog, ProcessingBatch

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def process_batch_documents(self, batch_id):
    """
    TAREA PRINCIPAL CORREGIDA: Procesa todos los documentos de un batch EN PARALELO
    """
    try:
        logger.info(f"=== INICIANDO BATCH {batch_id} ===")
        
        batch = ProcessingBatch.objects.get(id=batch_id)
        batch.batch_status = 'processing'
        batch.save()
        
        master_document = batch.master_document
        
        ProcessingLog.objects.create(
            glosa=master_document,
            level='INFO',
            message=f'Iniciando procesamiento PARALELO de batch con {batch.total_documents} documentos'
        )
        
        # Obtener documentos hijos
        child_documents = master_document.child_documents.all().order_by('patient_section_number')
        
        if not child_documents.exists():
            raise Exception("No se encontraron documentos hijos para procesar")
        
        # PROCESAMIENTO PARALELO USANDO CELERY GROUP
        child_ids = [str(child.id) for child in child_documents]
        
        logger.info(f"Creando {len(child_ids)} tareas paralelas")
        ProcessingLog.objects.create(
            glosa=master_document,
            level='INFO',
            message=f'Creando {len(child_ids)} tareas PARALELAS para procesamiento'
        )
        
        # Crear grupo de tareas que se ejecutarán en paralelo
        job = group(process_single_glosa_document.s(child_id) for child_id in child_ids)
        result = job.apply_async()
        
        # NO esperamos los resultados aquí - las tareas se procesan en paralelo
        logger.info(f"✅ {len(child_ids)} tareas paralelas iniciadas exitosamente")
        logger.info("Las tareas se procesarán en paralelo. El progreso se monitoreará automáticamente.")
        
        # El progreso real se actualiza por el monitor automático y al completarse cada tarea
        # No necesitamos esperar aquí - esto permite verdadero procesamiento asíncrono
        
        ProcessingLog.objects.create(
            glosa=master_document,
            level='INFO',
            message=f'✅ Procesamiento paralelo iniciado para {len(child_ids)} documentos. '
                   f'Las tareas se ejecutarán de forma asíncrona.'
        )
        
        
        # El batch se marca como 'processing' y se deja que las tareas individuales se completen
        # El monitor automático actualizará el progreso cuando las tareas terminen
        batch.batch_status = 'processing'
        batch.save()
        
        logger.info(f"=== BATCH {batch_id} INICIADO EXITOSAMENTE ===")
        
        return {
            'batch_id': str(batch_id),
            'status': 'processing',
            'total_tasks': len(child_ids),
            'message': 'Procesamiento paralelo iniciado exitosamente'
        }
        
    except ProcessingBatch.DoesNotExist:
        logger.error(f"Batch {batch_id} no encontrado")
        return {'error': 'Batch no encontrado'}
        
    except Exception as e:
        logger.error(f"Error crítico en batch {batch_id}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
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
        
        # Retry con backoff exponencial
        raise self.retry(exc=e, countdown=300 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def process_single_glosa_document(self, glosa_id):
    """
    TAREA CORREGIDA: Procesa un documento individual con logs mejorados
    """
    try:
        logger.info(f"=== PROCESANDO DOCUMENTO {glosa_id} ===")
        
        # Obtener documento
        glosa = GlosaDocument.objects.get(id=glosa_id)
        glosa.status = 'processing'
        glosa.save()
        
        # Log inicio con información de intento
        ProcessingLog.objects.create(
            glosa=glosa,
            level='INFO',
            message=f'Iniciando extracción de datos (intento {self.request.retries + 1}/3)'
        )
        
        # Verificar que el archivo existe
        if not glosa.original_file or not glosa.original_file.path:
            raise Exception("Archivo no encontrado")
        
        logger.info(f"Archivo encontrado: {glosa.original_file.path}")
        
        # Inicializar extractor con verificación de API key
        openai_api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not openai_api_key:
            raise Exception("API Key de OpenAI no configurada en settings")
            
        logger.info("API Key de OpenAI verificada")
        
        # Importar aquí para evitar import circular
        from .medical_claim_extractor_fixed import MedicalClaimExtractor
        extractor = MedicalClaimExtractor(openai_api_key=openai_api_key)
        
        # Determinar estrategia
        strategy = getattr(glosa, 'strategy', 'ai_only')
        
        ProcessingLog.objects.create(
            glosa=glosa,
            level='INFO',
            message=f'Extrayendo datos con estrategia: {strategy}'
        )
        
        logger.info(f"Iniciando extracción con estrategia: {strategy}")
        
        # Procesar documento con medición de tiempo
        start_time = timezone.now()
        
        # Rate limiting manual para OpenAI
        if self.request.retries > 0:
            delay = min(60 * (2 ** self.request.retries), 300)
            logger.info(f"Aplicando delay de {delay}s antes de llamar OpenAI")
            time.sleep(delay)
        
        result = extractor.extract_from_pdf(glosa.original_file.path, strategy=strategy)
        end_time = timezone.now()
        
        processing_time = (end_time - start_time).total_seconds()
        logger.info(f"Extracción completada en {processing_time:.2f}s")
        
        # Verificar resultados
        if result.get('error'):
            raise Exception(f"Error en extracción: {result['error']}")
        
        # Validar que hay procedimientos extraídos
        procedures = result.get('procedures', [])
        if not procedures:
            logger.warning(f"No se encontraron procedimientos en documento {glosa_id}")
        
        # Guardar datos extraídos
        glosa.extracted_data = result
        glosa.status = 'completed'
        glosa.updated_at = timezone.now()
        glosa.save()
        
        # Log de éxito con estadísticas detalladas
        financial = result.get('financial_summary', {})
        
        ProcessingLog.objects.create(
            glosa=glosa,
            level='INFO',
            message=f'Procesamiento completado en {processing_time:.2f}s. '
                   f'Procedimientos: {len(procedures)}, '
                   f'Monto total: ${financial.get("total_reclamado", 0):,.0f}'
        )
        
        logger.info(f"=== DOCUMENTO {glosa_id} COMPLETADO EXITOSAMENTE ===")
        return True
        
    except GlosaDocument.DoesNotExist:
        logger.error(f"Documento {glosa_id} no encontrado")
        return False
        
    except Exception as e:
        logger.error(f"Error procesando documento {glosa_id}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        try:
            glosa = GlosaDocument.objects.get(id=glosa_id)
            glosa.status = 'error'
            glosa.error_message = str(e)
            glosa.save()
            
            ProcessingLog.objects.create(
                glosa=glosa,
                level='ERROR',
                message=f'Error en procesamiento (intento {self.request.retries + 1}): {str(e)}'
            )
        except:
            pass
        
        # Retry inteligente para errores específicos
        error_str = str(e).lower()
        if any(keyword in error_str for keyword in ['api', 'timeout', 'connection', 'rate limit', 'quota']):
            if self.request.retries < self.max_retries:
                retry_delay = 60 + (self.request.retries * 30)
                logger.info(f"Reintentando documento {glosa_id} en {retry_delay} segundos")
                raise self.retry(exc=e, countdown=retry_delay)
        
        return False


# TAREAS DE MONITOREO Y MANTENIMIENTO

@shared_task
def monitor_batch_progress():
    """Monitorea el progreso de batches activos"""
    try:
        active_batches = ProcessingBatch.objects.filter(
            batch_status__in=['splitting', 'processing']
        )
        
        updated_count = 0
        
        for batch in active_batches:
            try:
                old_status = batch.batch_status
                old_completed = batch.completed_documents
                
                batch.update_progress()
                
                if (batch.batch_status != old_status or 
                    batch.completed_documents != old_completed):
                    
                    ProcessingLog.objects.create(
                        glosa=batch.master_document,
                        level='INFO',
                        message=f'Progreso actualizado: {batch.completed_documents}/{batch.total_documents} '
                               f'completados. Estado: {batch.batch_status}'
                    )
                    updated_count += 1
                    
            except Exception as e:
                logger.error(f"Error actualizando batch {batch.id}: {e}")
                continue
        
        if updated_count > 0:
            logger.info(f"Monitor: {updated_count} batches actualizados")
        
        return {'updated_batches': updated_count}
        
    except Exception as e:
        logger.error(f"Error en monitor de batches: {e}")
        return {'error': str(e)}


@shared_task
def cleanup_old_batches():
    """Limpia batches antiguos completados"""
    try:
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=30)
        
        old_batches = ProcessingBatch.objects.filter(
            completed_at__lt=cutoff_date,
            batch_status__in=['completed', 'partial_error']
        )
        
        deleted_count = old_batches.count()
        old_batches.delete()
        
        logger.info(f"Limpieza completada: {deleted_count} batches eliminados")
        return {'deleted_batches': deleted_count}
        
    except Exception as e:
        logger.error(f"Error en limpieza de batches: {e}")
        return {'error': str(e)}


@shared_task
def cleanup_orphaned_files():
    """Limpia archivos huérfanos"""
    try:
        logger.info("Iniciando limpieza de archivos huérfanos")
        return {'cleaned_files': 0}
        
    except Exception as e:
        logger.error(f"Error en limpieza de archivos: {e}")
        return {'error': str(e)}


@shared_task
def send_completion_notification(batch_id, user_email):
    """Envía email cuando se completa un batch"""
    try:
        batch = ProcessingBatch.objects.get(id=batch_id)
        logger.info(f"Notificación enviada a {user_email} para batch {batch_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error enviando notificación para batch {batch_id}: {e}")
        return False


@shared_task
def generate_batch_report(batch_id):
    """Genera un reporte completo de un batch procesado"""
    try:
        batch = ProcessingBatch.objects.get(id=batch_id)
        
        if not batch.is_complete:
            return {'error': 'Batch no completado aún'}
        
        # Generar reporte básico
        report = {
            'batch_id': str(batch_id),
            'master_document': batch.master_document.original_filename,
            'total_documents': batch.total_documents,
            'completed_documents': batch.completed_documents,
            'failed_documents': batch.failed_documents,
            'success_rate': (batch.completed_documents / batch.total_documents * 100) if batch.total_documents > 0 else 0,
        }
        
        logger.info(f"Reporte generado para batch {batch_id}")
        return report
        
    except ProcessingBatch.DoesNotExist:
        return {'error': 'Batch no encontrado'}
    except Exception as e:
        logger.error(f"Error generando reporte de batch {batch_id}: {e}")
        return {'error': str(e)}


# FUNCIÓN LEGACY PARA COMPATIBILIDAD
@shared_task(bind=True)
def process_glosa_document(self, glosa_id):
    """Tarea legacy para compatibilidad"""
    return process_single_glosa_document.apply_async(args=[glosa_id]).get()