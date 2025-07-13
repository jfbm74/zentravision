import os
from pathlib import Path
from decouple import config
import dj_database_url
from dotenv import load_dotenv 

# Cargar variables de entorno desde .env
load_dotenv()  

BASE_DIR = Path(__file__).resolve().parent.parent
SITE_URL = config('SITE_URL', default='http://localhost:8000')

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')

# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'crispy_forms',
    'crispy_bootstrap5',
    # 'django_celery_beat',
    # 'django_celery_results',
    'django_extensions',
]

LOCAL_APPS = [
    'apps.core',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'zentravision.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'apps' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'zentravision.wsgi.application'

# Database
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL'),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = config('STATIC_ROOT', default=str(BASE_DIR / 'staticfiles'))
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = config('MEDIA_ROOT', default=str(BASE_DIR / 'media'))

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20
}

# Celery Configuration
CELERY_BROKER_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# ============================================================================
# CONFIGURACIÓN DE OPENAI API
# ============================================================================

# API Key (CRÍTICO - debe estar configurado)
OPENAI_API_KEY = config('OPENAI_API_KEY', default='')

# Configuración de rate limiting
OPENAI_MAX_REQUESTS_PER_MINUTE = int(config('OPENAI_MAX_REQUESTS_PER_MINUTE', default='10'))
OPENAI_REQUEST_TIMEOUT = int(config('OPENAI_REQUEST_TIMEOUT', default='120'))  # 2 minutos

# Validación de API Key
if not OPENAI_API_KEY:
    import sys
    if 'runserver' in sys.argv or 'celery' in sys.argv:
        print("⚠️  ADVERTENCIA: OPENAI_API_KEY no está configurada!")
        print("   Configurar manualmente en el archivo .env")

# Límites de upload para PDFs grandes
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024   # 50MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024    # 50MB

# CORREGIDO: Directorio temporal que se crea en Ansible
FILE_UPLOAD_TEMP_DIR = config('FILE_UPLOAD_TEMP_DIR', default=str(BASE_DIR / 'tmp'))

# Crear directorio temporal si no existe
os.makedirs(FILE_UPLOAD_TEMP_DIR, exist_ok=True)

# URLs de autenticación
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# ============================================================================
# CONFIGURACIÓN DE LOGGING MEJORADA
# ============================================================================

# CORREGIDO: Directorio de logs que se crea en Ansible
LOGS_DIR = config('LOGS_DIR', default=str(BASE_DIR / 'logs'))
os.makedirs(LOGS_DIR, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
        'celery': {
            'format': '[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOGS_DIR, 'zentravision.log'),
            'formatter': 'verbose',
            'maxBytes': 10*1024*1024,  # 10MB
            'backupCount': 5,
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'celery_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOGS_DIR, 'celery.log'),
            'formatter': 'celery',
            'maxBytes': 10*1024*1024,  # 10MB
            'backupCount': 5,
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOGS_DIR, 'errors.log'),
            'formatter': 'verbose',
            'maxBytes': 10*1024*1024,  # 10MB
            'backupCount': 5,
        },
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console', 'file'],
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.core': {
            'handlers': ['file', 'console', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.extractor': {
            'handlers': ['file', 'console', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['celery_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery.task': {
            'handlers': ['celery_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# ============================================================================
# CONFIGURACIÓN DE CELERY PARA PROCESAMIENTO ASÍNCRONO
# ============================================================================

# URLs de broker y backend (Redis)
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')

# Configuración de timezone
CELERY_TIMEZONE = 'America/Bogota'
CELERY_ENABLE_UTC = True

# Configuración de serialización
CELERY_TASK_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_RESULT_SERIALIZER = 'json'

# Configuración de resultados
CELERY_RESULT_EXPIRES = 3600  # 1 hora
CELERY_RESULT_PERSISTENT = True

# Configuración de workers
CELERY_WORKER_CONCURRENCY = int(config('CELERY_WORKER_CONCURRENCY', default='4'))
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 50
CELERY_WORKER_MAX_MEMORY_PER_CHILD = 1024000  # 1GB

# Configuración de tareas
CELERY_TASK_SOFT_TIME_LIMIT = int(config('CELERY_TASK_SOFT_TIME_LIMIT', default='1800'))  # 30 minutos
CELERY_TASK_TIME_LIMIT = int(config('CELERY_TASK_TIME_LIMIT', default='2400'))  # 40 minutos
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# Rate limiting para OpenAI API
CELERY_TASK_DEFAULT_RATE_LIMIT = '8/m'  # 8 tareas por minuto

# ============================================================================
# CONFIGURACIÓN DE CACHE (OPCIONAL)
# ============================================================================

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': CELERY_BROKER_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'zentravision',
        'TIMEOUT': 300,  # 5 minutos por defecto
    }
}

# ============================================================================
# CONFIGURACIÓN DE SEGURIDAD PARA PRODUCCIÓN
# ============================================================================

# Configuración de sesiones
SESSION_COOKIE_AGE = 86400  # 24 horas
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# ============================================================================
# CONFIGURACIÓN ESPECÍFICA PARA DESARROLLO VS PRODUCCIÓN
# ============================================================================

if DEBUG:
    # Configuración para desarrollo
    CELERY_TASK_ALWAYS_EAGER = False  # Mantener asíncrono incluso en desarrollo
    CELERY_TASK_EAGER_PROPAGATES = True
    
    # Logging más detallado en desarrollo
    LOGGING['loggers']['apps.core']['level'] = 'DEBUG'
    LOGGING['loggers']['apps.extractor']['level'] = 'DEBUG'
    
else:
    # Configuración para producción
    
    # Seguridad (solo si están configuradas en .env)
    if config('SECURE_SSL_REDIRECT', default=False, cast=bool):
        SECURE_SSL_REDIRECT = True
        SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
        
    if config('SESSION_COOKIE_SECURE', default=False, cast=bool):
        SESSION_COOKIE_SECURE = True
        
    if config('CSRF_COOKIE_SECURE', default=False, cast=bool):
        CSRF_COOKIE_SECURE = True
    
    # Rate limiting más estricto en producción
    CELERY_TASK_DEFAULT_RATE_LIMIT = '6/m'  # Más conservador
    
    # Configuración de Celery para producción
    CELERY_WORKER_HIJACK_ROOT_LOGGER = False
    CELERY_WORKER_LOG_COLOR = False

# ============================================================================
# CONFIGURACIÓN DE MONITOREO (OPCIONAL)
# ============================================================================

# Configuración para métricas de rendimiento
PERFORMANCE_MONITORING = {
    'ENABLED': config('PERFORMANCE_MONITORING_ENABLED', default=False, cast=bool),
    'TRACK_CELERY_TASKS': True,
    'TRACK_API_CALLS': True,
    'TRACK_FILE_PROCESSING': True,
}

# ============================================================================
# CONFIGURACIÓN ADICIONAL PARA CELERY BEAT (TAREAS PERIÓDICAS)
# ============================================================================

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'monitor-batch-progress': {
        'task': 'apps.extractor.tasks.monitor_batch_progress',
        'schedule': 30.0,  # Cada 30 segundos
        'options': {'queue': 'monitoring'}
    },
    'cleanup-old-batches': {
        'task': 'apps.extractor.tasks.cleanup_old_batches',
        'schedule': crontab(hour=2, minute=0),  # Cada día a las 2 AM
        'options': {'queue': 'maintenance'}
    },
    'cleanup-orphaned-files': {
        'task': 'apps.extractor.tasks.cleanup_orphaned_files',
        'schedule': crontab(hour=3, minute=0),  # Cada día a las 3 AM
        'options': {'queue': 'maintenance'}
    },
}

# ============================================================================
# VALIDACIONES FINALES
# ============================================================================

# Solo validar configuraciones críticas en producción, no en desarrollo
if not DEBUG:
    CRITICAL_SETTINGS = {
        'SECRET_KEY': SECRET_KEY,
        'CELERY_BROKER_URL': CELERY_BROKER_URL,
    }

    missing_settings = [name for name, value in CRITICAL_SETTINGS.items() if not value]

    if missing_settings:
        print(f"⚠️  Configuraciones críticas faltantes: {missing_settings}")
        # No lanzar excepción para permitir que la aplicación arranque