# zentravision/celery.py - CONFIGURACIÓN SIMPLIFICADA Y CORREGIDA

import os
from celery import Celery

# Establecer el módulo de configuración de Django para Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zentravision.settings')

app = Celery('zentravision')

# CONFIGURACIÓN SIMPLIFICADA PARA DEBUGGING
app.conf.update(
    # Configuración básica de Redis/Broker
    broker_url='redis://localhost:6379/0',
    result_backend='redis://localhost:6379/0',
    
    # Configuración de workers SIMPLIFICADA
    worker_concurrency=3,  # Reducir a 2 para debugging
    worker_prefetch_multiplier=1,
    
    # Configuración de tareas
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='America/Bogota',
    enable_utc=True,
    
    # Configuración de timeouts
    task_soft_time_limit=1800,  # 30 minutos
    task_time_limit=2400,       # 40 minutos
    
    # Configuración de confiabilidad
    task_acks_late=True,
    worker_send_task_events=True,
    task_send_sent_event=True,
    
    # Configuración de resultados
    result_expires=3600,
    result_persistent=True,
    
    # USAR COLA POR DEFECTO (IMPORTANTE PARA DEBUGGING)
    # Removemos las colas especializadas temporalmente
    task_default_queue='celery',
    task_default_exchange='celery',
    task_default_routing_key='celery',
    
    # Rate limiting básico
    task_default_rate_limit='10/m',
    
    # Memory management
    worker_max_tasks_per_child=25,
    worker_max_memory_per_child=512000,  # 512MB
    
    # Debugging
    worker_log_color=True,
    worker_enable_remote_control=True,
)

# Auto-discovery de tareas Django
app.autodiscover_tasks()

# Lista explícita de aplicaciones
app.autodiscover_tasks(['apps.extractor'])

@app.task(bind=True)
def debug_task(self):
    """Tarea de debugging"""
    print(f'Request: {self.request!r}')
    return f'Debug task executed successfully on worker: {self.request.hostname}'

# Configuración para desarrollo
if os.environ.get('DJANGO_DEBUG', 'False').lower() == 'true':
    app.conf.update(
        worker_concurrency=1,  # Un solo worker en desarrollo
        task_always_eager=False,  # Mantener asíncrono
        task_eager_propagates=True,
        worker_log_format='[%(asctime)s: %(levelname)s] %(message)s',
    )

print("✅ Celery configurado correctamente")