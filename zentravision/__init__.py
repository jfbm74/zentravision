# Esto asegura que Celery se importe cuando Django inicia
from .celery import app as celery_app

__all__ = ('celery_app',)