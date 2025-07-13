# apps/extractor/tasks.py - TAREAS ASÍNCRONAS OPTIMIZADAS PARA PROCESAMIENTO PARALELO

from celery import shared_task, group, chord
from django.utils import timezone
from django.core.files.base import ContentFile
from django.conf import settings
import json
import traceback
import logging
import time
from apps.core.models import GlosaDocument, ProcessingLog, ProcessingBatch
from .medical_claim_extractor_fixed import MedicalClaimExtractor

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def process_batch_documents(self, batch_id):
    """
    TAREA PRINCIPAL MEJORADA: Procesa todos los documentos de un batch EN PARALELO
    """
    try:
        logger.info(f"Iniciando procesamiento PARALELO de batch {batch_id}")
        
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
        
        ProcessingLog.objects.create(
            glosa=master_document,
            level='INFO',
            message=f'Creando {len(child_ids)} tareas PARALELAS para procesamiento'
        )
        
        # Crear grupo de tareas que se ejecutarán en paralelo
        job = group(process_single_glosa_document.s(child_id) for child_id in child_ids)
        result = job.apply_async()
        
        # Esperar a que todas las tareas paralelas terminen
        logger.info(f"Esperando resultados de {len(child_ids)} tareas paralelas...")
        start_time = time.time()
        
        # Usar timeout para evitar espera infinita
        try:
            results = result.get(timeout=3600, propagate=False)  # 1 hora máximo
        except Exception as e:
            logger.error(f"Timeout o error esperando resultados: {e}")
            results = [False] * len(child_ids)
        
        processing_time = time.time() - start_time
        logger.info(f"Procesamiento paralelo completado en {processing_time:.2f} segundos")
        
        # Procesar resultados
        successful_count = 0
        failed_count = 0
        
        for i, (child_id, success) in enumerate(zip(child_ids, results)):
            try:
                if success:
                    successful_count += 1
                    ProcessingLog.objects.create(
                        glosa=master_document,
                        level='INFO',
                        message=f'Documento {i+1} procesado exitosamente (ID: {child_id})'
                    )
                else:
                    failed_count += 1
                    ProcessingLog.objects.create(
                        glosa=master_document,
                        level='ERROR',
                        message=f'Error procesando documento {i+1} (ID: {child_id})'
                    )
            except Exception as e:
                failed_count += 1
                logger.error(f"Error procesando resultado para {child_id}: {e}")
        
        # Actualizar batch con resultados finales
        batch.completed_documents = successful_count
        batch.failed_documents = failed_count
        batch.update_progress()  # Esto actualiza estados finales
        
        # Log final con estadísticas
        ProcessingLog.objects.create(
            glosa=master_document,
            level='INFO',
            message=f'Batch completado en {processing_time:.2f}s: {successful_count} exitosos, '
                   f'{failed_count} fallidos de {len(child_ids)} totales'
        )
        
        # Enviar notificación si está configurado el email
        if successful_count > 0:
            try:
                send_completion_notification.delay(str(batch.id), master_document.user.email)
            except Exception as e:
                logger.warning(f"No se pudo enviar notificación: {e}")
        
        logger.info(f"Batch {batch_id} completado: {successful_count}/{len(child_ids)} exitosos")
        
        return {
            'batch_id': str(batch_id),
            'completed': successful_count,
            'failed': failed_count,
            'total': len(child_ids),
            'status': batch.batch_status,
            'processing_time': processing_time
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
        
        # Retry con backoff exponencial
        raise self.retry(exc=e, countdown=300 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def process_single_glosa_document(self, glosa_id):
    """
    TAREA MEJORADA: Procesa un documento individual con optimizaciones para OpenAI
    """
    try:
        logger.info(f"Procesando documento individual {glosa_id}")
        
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
        
        # Inicializar extractor con verificación de API key
        openai_api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not openai_api_key:
            raise Exception("API Key de OpenAI no configurada en settings")
            
        extractor = MedicalClaimExtractor(openai_api_key=openai_api_key)
        
        # Determinar estrategia
        strategy = getattr(glosa, 'strategy', 'ai_only')  # Usar ai_only por defecto para mejor rendimiento
        
        ProcessingLog.objects.create(
            glosa=glosa,
            level='INFO',
            message=f'Extrayendo datos con estrategia: {strategy}'
        )
        
        # Procesar documento con medición de tiempo
        start_time = timezone.now()
        
        # Rate limiting manual para OpenAI (importante)
        if self.request.retries > 0:
            delay = min(60 * (2 ** self.request.retries), 300)  # Backoff exponencial
            logger.info(f"Aplicando delay de {delay}s antes de llamar OpenAI (intento {self.request.retries + 1})")
            time.sleep(delay)
        
        result = extractor.extract_from_pdf(glosa.original_file.path, strategy=strategy)
        end_time = timezone.now()
        
        processing_time = (end_time - start_time).total_seconds()
        
        # Verificar resultados
        if result.get('error'):
            raise Exception(f"Error en extracción: {result['error']}")
        
        # Validar que hay procedimientos extraídos
        procedures = result.get('procedures', [])
        if not procedures:
            logger.warning(f"No se encontraron procedimientos en documento {glosa_id}")
            ProcessingLog.objects.create(
                glosa=glosa,
                level='WARNING',
                message='No se encontraron procedimientos en el documento'
            )
        
        # Validar información crítica del paciente
        patient_info = result.get('patient_info', {})
        if not patient_info.get('nombre'):
            logger.warning(f"No se extrajo nombre del paciente en documento {glosa_id}")
        
        # Guardar datos extraídos
        glosa.extracted_data = result
        glosa.status = 'completed'
        glosa.updated_at = timezone.now()
        glosa.save()
        
        # Log de éxito con estadísticas detalladas
        extraction_stats = result.get('extraction_details', {})
        financial = result.get('financial_summary', {})
        
        ProcessingLog.objects.create(
            glosa=glosa,
            level='INFO',
            message=f'Procesamiento completado en {processing_time:.2f}s. '
                   f'Procedimientos: {len(procedures)}, '
                   f'Monto total: ${financial.get("total_reclamado", 0):,.0f}, '
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
                message=f'Error en procesamiento (intento {self.request.retries + 1}): {str(e)}'
            )
        except:
            pass
        
        # Retry inteligente para errores específicos
        error_str = str(e).lower()
        if any(keyword in error_str for keyword in ['api', 'timeout', 'connection', 'rate limit', 'quota']):
            if self.request.retries < self.max_retries:
                retry_delay = 60 + (self.request.retries * 30)  # Incrementar delay
                logger.info(f"Reintentando documento {glosa_id} en {retry_delay} segundos")
                raise self.retry(exc=e, countdown=retry_delay)
        
        return False


@shared_task
def monitor_batch_progress():
    """
    TAREA PERIÓDICA: Monitorea el progreso de batches activos
    """
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
                
                # Si cambió el estado significativamente, crear log
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
    """
    TAREA DE MANTENIMIENTO: Limpia batches antiguos completados
    """
    try:
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=30)
        
        old_batches = ProcessingBatch.objects.filter(
            completed_at__lt=cutoff_date,
            batch_status__in=['completed', 'partial_error']
        )
        
        deleted_count = 0
        for batch in old_batches:
            try:
                master_doc = batch.master_document
                filename = master_doc.original_filename
                
                # Esto eliminará el documento maestro y todos sus hijos
                master_doc.delete()
                deleted_count += 1
                
                logger.info(f"Eliminado batch antiguo: {filename}")
                
            except Exception as e:
                logger.error(f"Error eliminando batch {batch.id}: {e}")
                continue
        
        logger.info(f"Limpieza completada: {deleted_count} batches eliminados")
        return {'deleted_batches': deleted_count}
        
    except Exception as e:
        logger.error(f"Error en limpieza de batches: {e}")
        return {'error': str(e)}


@shared_task
def cleanup_orphaned_files():
    """
    TAREA DE MANTENIMIENTO: Limpia archivos huérfanos
    """
    try:
        from django.core.files.storage import default_storage
        import os
        
        logger.info("Iniciando limpieza de archivos huérfanos")
        
        orphaned_files = []
        
        for glosa in GlosaDocument.objects.all():
            if glosa.original_file:
                if not default_storage.exists(glosa.original_file.name):
                    orphaned_files.append(glosa.id)
        
        if orphaned_files:
            logger.warning(f"Encontrados {len(orphaned_files)} documentos con archivos faltantes")
            # Opcional: eliminar documentos huérfanos
            # GlosaDocument.objects.filter(id__in=orphaned_files).delete()
        
        logger.info("Limpieza de archivos completada")
        
        return {
            'missing_files': len(orphaned_files),
            'cleaned_files': 0
        }
        
    except Exception as e:
        logger.error(f"Error en limpieza de archivos: {e}")
        return {'error': str(e)}


@shared_task
def send_completion_notification(batch_id, user_email):
    """
    TAREA DE NOTIFICACIÓN: Envía email cuando se completa un batch
    """
    try:
        from django.core.mail import send_mail
        from django.conf import settings
        
        batch = ProcessingBatch.objects.get(id=batch_id)
        
        subject = f"Zentravision: Procesamiento completado - {batch.master_document.original_filename}"
        
        message = f"""
Estimado usuario,

Su documento {batch.master_document.original_filename} ha sido procesado completamente.

Resultados del procesamiento:
- Total de documentos: {batch.total_documents}
- Procesados exitosamente: {batch.completed_documents}
- Con errores: {batch.failed_documents}
- Estado final: {batch.get_batch_status_display()}
- Tiempo de procesamiento: {(batch.completed_at - batch.created_at).total_seconds():.0f} segundos

Puede ver los resultados detallados en: {getattr(settings, 'SITE_URL', 'http://localhost:8000')}/batches/{batch.id}/

Saludos,
Equipo Zentravision
"""
        
        send_mail(
            subject,
            message,
            getattr(settings, 'DEFAULT_FROM_EMAIL', 'zentravision@example.com'),
            [user_email],
            fail_silently=False,
        )
        
        logger.info(f"Notificación enviada a {user_email} para batch {batch_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error enviando notificación para batch {batch_id}: {e}")
        return False


@shared_task
def generate_batch_report(batch_id):
    """
    TAREA DE REPORTE: Genera un reporte completo de un batch procesado
    """
    try:
        batch = ProcessingBatch.objects.get(id=batch_id)
        
        if not batch.is_complete:
            return {'error': 'Batch no completado aún'}
        
        # Recopilar estadísticas detalladas
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


# FUNCIÓN AUXILIAR PARA COMPATIBILIDAD CON DOCUMENTOS INDIVIDUALES
def process_single_glosa_sync(glosa_id):
    """
    Función síncrona para compatibilidad con código existente
    En realidad delega a la tarea asíncrona
    """
    try:
        task = process_single_glosa_document.delay(glosa_id)
        # En contexto síncrono, esperamos el resultado
        return task.get(timeout=1800)  # 30 minutos máximo
    except Exception as e:
        logger.error(f"Error en procesamiento síncrono de {glosa_id}: {e}")
        return False


# TAREA LEGACY PARA COMPATIBILIDAD
@shared_task(bind=True)
def process_glosa_document(self, glosa_id):
    """
    Tarea legacy para compatibilidad con sistema anterior
    """
    return process_single_glosa_document(glosa_id)