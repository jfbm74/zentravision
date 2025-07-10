# Zentravision - Extractor de Glosas Médicas

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Django](https://img.shields.io/badge/django-4.2.7-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

Zentravision es una aplicación web desarrollada en Django que permite la extracción automática de datos de glosas médicas SOAT colombianas usando tecnologías de OCR e Inteligencia Artificial.

## 📋 Características

- **Extracción Automática**: Procesamiento de PDFs de glosas médicas con múltiples estrategias
- **Integración con OpenAI**: Análisis inteligente de documentos usando GPT-4
- **Múltiples Formatos**: Exportación de datos en JSON, CSV y visualización web
- **Dashboard Interactivo**: Interfaz moderna con estadísticas y gráficos
- **Procesamiento Asíncrono**: Manejo eficiente de archivos grandes con Celery
- **Panel de Administración**: Gestión completa de documentos y logs

## 🚀 Tecnologías Utilizadas

- **Backend**: Django 4.2.7, Django REST Framework
- **Frontend**: Bootstrap 5, Chart.js, Font Awesome
- **OCR**: PyMuPDF para extracción de texto
- **IA**: OpenAI GPT-4 para análisis inteligente
- **Base de Datos**: PostgreSQL (producción), SQLite (desarrollo)
- **Cache/Cola**: Redis + Celery para procesamiento asíncrono
- **Deployment**: Gunicorn + WhiteNoise para archivos estáticos

## 📁 Estructura del Proyecto

```
zentravision/
├── apps/
│   ├── core/                           # Aplicación principal
│   │   ├── models.py                   # Modelos de datos
│   │   ├── views.py                    # Vistas y lógica de negocio
│   │   ├── admin.py                    # Configuración del admin
│   │   ├── forms.py                    # Formularios
│   │   ├── urls.py                     # URLs de la aplicación
│   │   └── management/commands/        # Comandos de gestión
│   ├── extractor/                      # Motor de extracción
│   │   ├── medical_claim_extractor_fixed.py  # Extractor principal
│   │   ├── tasks.py                    # Tareas de Celery
│   │   └── utils.py                    # Utilidades de procesamiento
│   └── templates/                      # Templates HTML
├── zentravision/                       # Configuración Django
├── requirements.txt                    # Dependencias
└── manage.py                          # Comando de gestión Django
```

## 🔧 Instalación

### Prerrequisitos

- Python 3.8 o superior
- PostgreSQL (opcional, para producción)
- Redis (para procesamiento asíncrono)
- Cuenta de OpenAI con API key

### Pasos de Instalación

1. **Clonar el repositorio**
```bash
git clone https://github.com/tu-usuario/zentravision.git
cd zentravision
```

2. **Crear entorno virtual**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o
venv\Scripts\activate     # Windows
```

3. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

4. **Configurar variables de entorno**
```bash
# Crear archivo .env en la raíz del proyecto
cp .env.example .env
```

Editar `.env` con tus configuraciones:
```env
SECRET_KEY=tu-clave-secreta-aqui
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
OPENAI_API_KEY=sk-tu-api-key-de-openai
REDIS_URL=redis://localhost:6379/0
ALLOWED_HOSTS=localhost,127.0.0.1
```

5. **Configurar base de datos**
```bash
python manage.py makemigrations
python manage.py migrate
```

6. **Crear superusuario**
```bash
python manage.py createsuperuser
```

7. **Ejecutar el servidor**
```bash
python manage.py runserver
```

## 🚀 Configuración para Producción

### Usando Docker (Recomendado)

```bash
# Construir imagen
docker build -t zentravision .

# Ejecutar contenedor
docker run -p 8000:8000 --env-file .env zentravision
```

### Configuración Manual

1. **Configurar PostgreSQL**
```bash
# Instalar PostgreSQL
sudo apt install postgresql postgresql-contrib

# Crear base de datos
sudo -u postgres createdb zentravision_db
```

2. **Configurar Redis**
```bash
# Instalar Redis
sudo apt install redis-server

# Iniciar servicio
sudo systemctl start redis-server
```

3. **Configurar Celery**
```bash
# Terminal 1: Worker
celery -A zentravision worker --loglevel=info

# Terminal 2: Beat scheduler
celery -A zentravision beat --loglevel=info
```

4. **Configurar servidor web**
```bash
# Instalar Gunicorn
pip install gunicorn

# Ejecutar servidor
gunicorn zentravision.wsgi:application --bind 0.0.0.0:8000
```

## 📖 Uso

### Subir Glosas

1. Accede a la aplicación en `http://localhost:8000`
2. Inicia sesión con tu usuario
3. Ve a "Subir Glosa" en el menú
4. Selecciona tu archivo PDF
5. Elige la estrategia de extracción:
   - **Híbrida**: OCR + IA (recomendada)
   - **Solo IA**: Procesamiento con OpenAI
   - **Solo OCR**: Extracción tradicional

### Estrategias de Extracción

- **Híbrida**: Combina OCR tradicional con análisis de IA para máxima precisión
- **Solo IA**: Utiliza OpenAI GPT-4 para análisis inteligente del documento
- **Solo OCR**: Extracción basada en patrones regulares y OCR

### Campos Extraídos

- **Información del Paciente**: Nombre, documento, edad
- **Información de Póliza**: Número de póliza, liquidación, reclamación
- **Procedimientos**: Códigos CUPS, descripciones, cantidades, valores
- **Resumen Financiero**: Valores reclamados, objetados, aceptados
- **Diagnósticos**: Códigos CIE-10 y descripciones
- **Información IPS**: Nombre y NIT de la institución

## 🔍 Comandos de Gestión

### Verificar Base de Datos
```bash
# Ver todas las glosas
python manage.py check_database

# Ver glosa específica
python manage.py check_database --glosa-id UUID

# Ver última glosa
python manage.py check_database --latest
```

### Probar Extractor
```bash
# Probar extractor con archivo PDF
python manage.py test_extractor /ruta/al/archivo.pdf

# Usar estrategia específica
python manage.py test_extractor /ruta/al/archivo.pdf --strategy hybrid

# Guardar resultado
python manage.py test_extractor /ruta/al/archivo.pdf --output resultado.json
```

## 📊 API Endpoints

### Glosas
- `GET /api/glosas/` - Listar glosas
- `POST /api/glosas/` - Crear nueva glosa
- `GET /api/glosas/{id}/` - Detalle de glosa
- `GET /api/glosas/{id}/status/` - Estado de procesamiento

### Descargas
- `GET /download/{id}/json/` - Descargar datos como JSON
- `GET /download/{id}/csv/` - Descargar procedimientos como CSV
- `GET /download/{id}/original/` - Descargar archivo original

## 🛠️ Desarrollo

### Configurar Entorno de Desarrollo

```bash
# Instalar dependencias de desarrollo
pip install -r requirements-dev.txt

# Ejecutar tests
python manage.py test

# Verificar calidad de código
flake8 .
black .
```

### Estructura de Modelos

```python
# GlosaDocument - Documento principal
class GlosaDocument(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    original_file = models.FileField(upload_to='uploads/glosas/')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES)
    extracted_data = models.JSONField(null=True, blank=True)
    # ... más campos

# ProcessingLog - Logs de procesamiento
class ProcessingLog(models.Model):
    glosa = models.ForeignKey(GlosaDocument, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10)
    message = models.TextField()
```

### Agregar Nuevas Características

1. **Nuevo Extractor**:
   - Crear clase en `apps/extractor/`
   - Implementar interface `extract_from_pdf()`
   - Registrar en `MedicalClaimExtractor`

2. **Nuevo Formato de Salida**:
   - Agregar función en `views.py`
   - Crear URL en `urls.py`
   - Actualizar templates

## 📈 Monitoreo y Logs

### Logs de Aplicación
```bash
# Ver logs en tiempo real
tail -f logs/zentravision.log

# Logs de Celery
tail -f logs/celery.log
```

### Métricas de Rendimiento
- Dashboard con estadísticas de procesamiento
- Tiempo promedio de extracción
- Tasa de éxito por estrategia
- Análisis de calidad de datos

## 🔒 Seguridad

- Autenticación requerida para todas las vistas
- Validación de tipos de archivo (solo PDF)
- Sanitización de datos extraídos
- Limitación de tamaño de archivo (10MB)
- Protección CSRF en formularios

## 🤝 Contribución

1. Fork el repositorio
2. Crear rama para nueva característica (`git checkout -b feature/nueva-caracteristica`)
3. Commit los cambios (`git commit -am 'Agregar nueva característica'`)
4. Push a la rama (`git push origin feature/nueva-caracteristica`)
5. Crear Pull Request

## 📞 Soporte

- **Documentación**: [Wiki del proyecto](https://github.com/tu-usuario/zentravision/wiki)
- **Issues**: [GitHub Issues](https://github.com/tu-usuario/zentravision/issues)
- **Email**: soporte@zentravision.com

## 📄 Licencia

Este proyecto está bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para más detalles.

## 🔄 Changelog

### v1.0.0 (2025-01-10)
- Lanzamiento inicial
- Extracción de glosas SOAT colombianas
- Integración con OpenAI GPT-4
- Dashboard interactivo
- Exportación en múltiples formatos

---

**Zentravision** - Extracción inteligente de glosas médicas