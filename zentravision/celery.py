# zentravision/celery.py - CONFIGURACIÓN COMPLETA OPTIMIZADA PARA PROCESAMIENTO PARALELO

import os
from celery import Celery
from celery.signals import task_failure, task_success, after_task_publish

# Establecer el módulo de configuración de Django para Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zentravision.settings')

app = Celery('zentravision')

# Configuración optimizada para procesamiento de documentos médicos con OpenAI
app.conf.update(
    # Configuración de Redis/Broker
    broker_url='redis://localhost:6379/0',
    result_backend='redis://localhost:6379/0',
    
    # Configuración de workers para OpenAI API - OPTIMIZADA
    worker_concurrency=4,  # 4 workers paralelos (ajustar según CPU y límites OpenAI)
    worker_prefetch_multiplier=1,  # Solo 1 tarea por worker para evitar bloqueos de API
    
    # Configuración de tareas
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='America/Bogota',
    enable_utc=True,
    
    # Configuración para tareas de larga duración (importante para OpenAI)
    task_soft_time_limit=1800,  # 30 minutos soft limit
    task_time_limit=2400,       # 40 minutos hard limit
    worker_disable_rate_limits=True,
    
    # Configuración de confiabilidad
    task_acks_late=True,        # Confirmar tarea solo cuando termine exitosamente
    worker_send_task_events=True,
    task_send_sent_event=True,
    task_reject_on_worker_lost=True,
    
    # Configuración de resultados
    result_expires=3600,        # Resultados expiran en 1 hora
    result_persistent=True,
    result_backend_transport_options={
        'master_name': 'mymaster',
        'visibility_timeout': 3600,
    },
    
    # Configuración para evitar memory leaks con OpenAI y procesamiento de PDFs
    worker_max_tasks_per_child=50,  # Reiniciar worker cada 50 tareas
    worker_max_memory_per_child=1024000,  # 1GB max por worker (importante para PDFs grandes)
    
    # Rate limiting específico para OpenAI API (crítico)
    task_default_rate_limit='8/m',  # Máximo 8 tareas por minuto por worker
    
    # Configuración de colas especializadas
    task_routes={
        'apps.extractor.tasks.process_single_glosa_document': {
            'queue': 'glosa_processing',
            'routing_key': 'glosa_processing',
            'priority': 5
        },
        'apps.extractor.tasks.process_batch_documents': {
            'queue': 'batch_processing',
            'routing_key': 'batch_processing', 
            'priority': 7
        },
        'apps.extractor.tasks.monitor_batch_progress': {
            'queue': 'monitoring',
            'routing_key': 'monitoring',
            'priority': 3
        },
        'apps.extractor.tasks.cleanup_old_batches': {
            'queue': 'maintenance',
            'routing_key': 'maintenance',
            'priority': 1
        },
        'apps.extractor.tasks.send_completion_notification': {
            'queue': 'notifications',
            'routing_key': 'notifications',
            'priority': 4
        },
    },
    
    # Configuración de prioridades
    task_inherit_parent_priority=True,
    task_default_priority=5,
    worker_direct=True,
    
    # Configuración de reintentos
    task_default_retry_delay=300,  # 5 minutos entre reintentos
    task_max_retries=3,
    
    # Monitoreo y debugging
    worker_enable_remote_control=True,
    worker_state_db='/tmp/celery_worker.db',
    worker_log_color=False,
    
    # Configuración de serialización segura
    task_always_eager=False,  # False para producción, True para testing
    task_eager_propagates=True,
    
    # Configuración de compresión para tareas grandes
    task_compression='gzip',
    result_compression='gzip',
    
    # Configuración específica para batches grandes
    broker_transport_options={
        'priority_steps': list(range(10)),
        'sep': ':',
        'queue_order_strategy': 'priority',
    },
)

# Configuración de Celery Beat (tareas periódicas) - MEJORADA
app.conf.beat_schedule = {
    'monitor-batch-progress': {
        'task': 'apps.extractor.tasks.monitor_batch_progress',
        'schedule': 30.0,  # Cada 30 segundos
        'options': {
            'queue': 'monitoring',
            'priority': 3
        }
    },
    'cleanup-old-batches': {
        'task': 'apps.extractor.tasks.cleanup_old_batches',
        'schedule': 86400.0,  # Cada 24 horas a las 2 AM
        'options': {
            'queue': 'maintenance',
            'priority': 1
        }
    },
    'cleanup-orphaned-files': {
        'task': 'apps.extractor.tasks.cleanup_orphaned_files',
        'schedule': 43200.0,  # Cada 12 horas
        'options': {
            'queue': 'maintenance',
            'priority': 1
        }
    },
}

# Auto-discovery de tareas Django
app.autodiscover_tasks()

# Lista explícita de aplicaciones para asegurar que se descubran las tareas
app.autodiscover_tasks(['apps.extractor'])

@app.task(bind=True)
def debug_task(self):
    """Tarea de debugging"""
    print(f'Request: {self.request!r}')
    return f'Debug task executed on worker: {self.request.hostname}'

# Configuración de logging para Celery
@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Configurar tareas periódicas adicionales si es necesario"""
    # Aquí se pueden agregar tareas periódicas dinámicas
    pass

# Manejo de señales de Celery - CORREGIDO
@task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None, einfo=None, **kwargs):
    """Manejo de fallos de tareas"""
    print(f'Task {task_id} failed: {exception}')

@task_success.connect  
def on_task_success(sender=None, result=None, **kwargs):
    """Manejo de éxito de tareas"""
    print(f'Task {sender.request.id} succeeded')

# Configuración para desarrollo vs producción
if os.environ.get('DJANGO_DEBUG', 'False').lower() == 'true':
    # Configuración para desarrollo
    app.conf.update(
        worker_concurrency=2,  # Menos workers en desarrollo
        task_always_eager=False,  # Mantener asíncrono incluso en desarrollo
        task_eager_propagates=True,
    )
else:
    # Configuración para producción
    app.conf.update(
        worker_hijack_root_logger=False,
        worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
        worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',
    )