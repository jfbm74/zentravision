import os
from celery import Celery

# Establecer el módulo de configuración de Django para Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zentravision.settings')

app = Celery('zentravision')

# Configuración usando settings de Django
app.config_from_object('django.conf:settings', namespace='CELERY')

# Autodescubrir tareas en las aplicaciones Django
app.autodiscover_tasks()

# Lista explícita de aplicaciones para asegurar que se descubran las tareas
app.autodiscover_tasks(['apps.extractor'])

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')