# zentravision
# ==========================================
# COMANDOS DE INSTALACIÓN Y CONFIGURACIÓN
# ==========================================

"""
# 1. Crear proyecto
django-admin startproject zentravision
cd zentravision

# 2. Crear aplicaciones
mkdir apps
python manage.py startapp core apps/core
mkdir apps/extractor

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar base de datos
python manage.py makemigrations
python manage.py migrate

# 5. Crear superusuario
python manage.py createsuperuser

# 6. Iniciar Redis (para Celery)
redis-server

# 7. Iniciar Celery Worker (en otra terminal)
celery -A zentravision worker --loglevel=info

# 8. Iniciar Celery Beat (en otra terminal)
celery -A zentravision beat --loglevel=info

# 9. Ejecutar servidor
python manage.py runserver
"""