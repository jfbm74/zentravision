# Zentravision - Extractor de Glosas Médicas SOAT

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Django](https://img.shields.io/badge/django-4.2.7-green.svg)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-orange.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

Zentravision es una aplicación web desarrollada en Django que permite la **extracción automática de datos de glosas médicas SOAT colombianas** usando tecnologías de OCR e Inteligencia Artificial avanzada.

## 🌟 Características Principales

- **🤖 Extracción Inteligente**: Procesamiento híbrido con OCR + OpenAI GPT-4o-mini
- **📄 División Automática de PDFs**: Detección y procesamiento de documentos con múltiples pacientes
- **⚡ Procesamiento Asíncrono**: Manejo eficiente con Celery + Redis para archivos grandes
- **📊 Dashboard Interactivo**: Interfaz moderna con estadísticas en tiempo real
- **📦 Gestión de Batches**: Sistema completo para manejar documentos múltiples
- **📈 Múltiples Formatos**: Exportación en JSON, CSV, y descargas masivas en ZIP
- **🔍 Panel de Administración Avanzado**: Gestión completa con visualización detallada de información del paciente, procedimientos y resumen financiero

## 🚀 Tecnologías Utilizadas

- **Backend**: Django 4.2.7, Django REST Framework
- **Frontend**: Bootstrap 5, Chart.js, Font Awesome
- **OCR**: PyMuPDF para extracción de texto
- **IA**: OpenAI GPT-4o-mini para análisis inteligente
- **Base de Datos**: PostgreSQL (producción), SQLite (desarrollo)
- **Cache/Cola**: Redis + Celery para procesamiento asíncrono
- **División PDF**: Sistema propio con PyMuPDF
- **Deployment**: Gunicorn + WhiteNoise para archivos estáticos

## 📁 Estructura del Proyecto

```
zentravision/
├── apps/
│   ├── core/                           # Aplicación principal
│   │   ├── models.py                   # Modelos: GlosaDocument, ProcessingBatch, ProcessingLog
│   │   ├── views.py                    # Vistas asíncronas para documentos únicos y batches
│   │   ├── admin.py                    # Panel de administración con visualización avanzada
│   │   ├── forms.py                    # Formularios de carga
│   │   ├── urls.py                     # URLs: /api/glosas/, /api/batches/
│   │   └── management/commands/        # Comandos: check_database, test_pdf_splitter, cleanup_batches
│   ├── extractor/                      # Motor de extracción
│   │   ├── medical_claim_extractor_fixed.py  # Extractor híbrido principal
│   │   ├── pdf_splitter.py            # Divisor automático de PDFs múltiples
│   │   ├── tasks.py                    # Tareas Celery para procesamiento asíncrono
│   │   └── utils.py                    # Utilidades y validadores médicos
│   └── templates/                      # Templates HTML
│       ├── dashboard.html              # Dashboard principal
│       ├── batch_detail.html           # Vista detallada de batches
│       ├── batch_list.html             # Lista de batches
│       ├── glosa_detail.html           # Detalle de documento individual
│       ├── glosa_list.html             # Lista de glosas
│       └── upload.html                 # Formulario de carga
├── zentravision/                       # Configuración Django
│   ├── settings.py                     # Configuración con Celery y Redis
│   ├── celery.py                       # Configuración de Celery
│   └── urls.py                         # URLs principales
├── requirements.txt                    # Dependencias completas
└── manage.py                          # Comando de gestión Django
```

## 🔧 Instalación Rápida

### Prerrequisitos

- Python 3.8 o superior
- Redis (para procesamiento asíncrono)
- Cuenta de OpenAI con API key (GPT-4o-mini)

### Pasos de Instalación

1. **Clonar el repositorio**
```bash
git clone https://github.com/tu-usuario/zentravision.git
cd zentravision
```

2. **Crear entorno virtual**
```bash
python -m venv myenv_py312
source myenv_py312/bin/activate  # Linux/Mac
# o
myenv_py312\Scripts\activate     # Windows
```

3. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

4. **Configurar variables de entorno**
```bash
# Crear archivo .env en la raíz del proyecto
```

Editar `.env` con tus configuraciones:
```env
SECRET_KEY=tu-clave-secreta-muy-larga-y-segura
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
OPENAI_API_KEY=sk-proj-tu-api-key-de-openai
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
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

7. **Instalar y configurar Redis**
```bash
# macOS
brew install redis
brew services start redis

# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis-server

# Verificar que funciona
redis-cli ping  # Debe responder: PONG
```

8. **Ejecutar la aplicación**

**Terminal 1 - Django:**
```bash
python manage.py runserver
```

**Terminal 2 - Celery Worker:**
```bash
celery -A zentravision worker --loglevel=info
```

**Terminal 3 - Celery Beat (opcional):**
```bash
celery -A zentravision beat --loglevel=info
```

## 📖 Uso de la Aplicación

### Subir Glosas

1. Accede a `http://localhost:8000`
2. Inicia sesión con tu usuario
3. Ve a **"Subir Glosa"** en el menú
4. Selecciona tu archivo PDF de glosa SOAT
5. Elige la estrategia de extracción:
   - **🎯 Híbrida** (recomendada): OCR + IA para máxima precisión
   - **🤖 Solo IA**: Procesamiento exclusivo con OpenAI
   - **📝 Solo OCR**: Extracción tradicional basada en patrones

### Tipos de Documentos Soportados

#### 📄 Documentos Individuales
- Un solo paciente por PDF
- Procesamiento directo e inmediato
- Extracción completa de procedimientos y observaciones

#### 📚 Documentos Múltiples (Batches)
- **Detección automática** de múltiples pacientes
- **División inteligente** del PDF por secciones
- **Procesamiento asíncrono** en segundo plano
- **Gestión de batches** con progreso en tiempo real
- **Descargas masivas** consolidadas

### Información Extraída

- **👤 Información del Paciente**: Nombre completo, documento de identidad, edad
- **🏥 Información de Póliza**: Número de póliza, liquidación, reclamación, fechas
- **⚕️ Procedimientos Médicos**: Códigos CUPS, descripciones detalladas, cantidades, valores
- **💰 Resumen Financiero**: Valores reclamados, objetados, aceptados con porcentajes
- **🩺 Diagnósticos**: Códigos CIE-10 con descripciones automáticas
- **🏢 Información IPS**: Nombre y NIT de la institución prestadora
- **📝 Observaciones de Glosas**: Motivos de objeción y justificaciones detalladas

## 🔍 Comandos de Gestión

### Verificar Base de Datos
```bash
# Ver todas las glosas y batches
python manage.py check_database

# Ver información específica de batches
python manage.py check_database --batches

# Ver glosa específica
python manage.py check_database --glosa-id UUID

# Ver última glosa procesada
python manage.py check_database --latest
```

### Probar División de PDFs
```bash
# Probar divisor con archivo específico
python manage.py test_pdf_splitter /ruta/al/archivo.pdf

# Validar formato únicamente
python manage.py test_pdf_splitter /ruta/al/archivo.pdf --validate-only

# Guardar secciones divididas
python manage.py test_pdf_splitter /ruta/al/archivo.pdf --output-dir ./test_output
```

### Probar Extractor
```bash
# Probar extractor con archivo PDF
python manage.py test_extractor /ruta/al/archivo.pdf

# Usar estrategia específica
python manage.py test_extractor /ruta/al/archivo.pdf --strategy hybrid

# Guardar resultado en archivo
python manage.py test_extractor /ruta/al/archivo.pdf --output resultado.json
```

### Limpieza y Mantenimiento
```bash
# Limpiar batches antiguos (más de 30 días)
python manage.py cleanup_batches --days 30

# Modo dry-run (solo mostrar qué se haría)
python manage.py cleanup_batches --days 30 --dry-run

# Incluir limpieza de archivos huérfanos
python manage.py cleanup_batches --days 30 --cleanup-files
```

## 📊 API Endpoints

### Glosas Individuales
- `GET /api/` - Dashboard principal con estadísticas en tiempo real
- `GET /api/glosas/` - Listar glosas con filtros avanzados
- `POST /api/upload/` - Subir nueva glosa (procesamiento asíncrono)
- `GET /api/glosas/{id}/` - Detalle de glosa individual
- `GET /api/glosas/{id}/status/` - Estado de procesamiento en tiempo real
- `POST /api/glosas/{id}/reprocess/` - Reprocesar glosa

### Batches de Documentos Múltiples
- `GET /api/batches/` - Listar batches con estado de progreso
- `GET /api/batches/{id}/` - Detalle de batch con progreso en tiempo real
- `POST /api/batches/{id}/reprocess/` - Reprocesar batch completo

### Descargas
- `GET /download/{id}/json/` - Datos extraídos como JSON
- `GET /download/{id}/csv/` - Procedimientos en formato Excel IPS (UTF-8)
- `GET /download/{id}/original/` - Archivo PDF original

### Descargas Masivas (Batches)
- `GET /download/batch/{id}/consolidated_csv/` - CSV consolidado con todos los pacientes
- `GET /download/batch/{id}/zip_json/` - ZIP con archivos JSON individuales
- `GET /download/batch/{id}/zip_csv/` - ZIP con archivos CSV individuales

### Panel de Administración
- `/admin/core/glosadocument/` - Gestión avanzada de documentos con visualización detallada
- `/admin/core/processingbatch/` - Monitoreo de batches de procesamiento
- `/admin/core/processinglog/` - Logs detallados de procesamiento

## 🚀 Configuración para Producción

### Variables de Entorno para Producción
```env
DEBUG=False
SECRET_KEY=clave-super-secreta-para-produccion
DATABASE_URL=postgresql://user:password@localhost:5432/zentravision_db
OPENAI_API_KEY=sk-proj-tu-api-key-real
REDIS_URL=redis://redis-server:6379/0
ALLOWED_HOSTS=tu-dominio.com,www.tu-dominio.com
```

### Usando Docker (Recomendado)

1. **Crear Dockerfile**
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["gunicorn", "zentravision.wsgi:application", "--bind", "0.0.0.0:8000"]
```

2. **Docker Compose**
```yaml
version: '3.8'
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
      - db
  
  redis:
    image: redis:7-alpine
  
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: zentravision
      POSTGRES_USER: zentravision
      POSTGRES_PASSWORD: password
  
  celery:
    build: .
    command: celery -A zentravision worker --loglevel=info
    depends_on:
      - redis
      - db
```

### Configuración Manual

1. **PostgreSQL para Producción**
```bash
sudo apt install postgresql postgresql-contrib
sudo -u postgres createdb zentravision_db
```

2. **Redis para Producción**
```bash
sudo apt install redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

3. **Supervisor para Celery**
```ini
[program:zentravision_celery]
command=/path/to/venv/bin/celery -A zentravision worker --loglevel=info
directory=/path/to/zentravision
user=zentravision
autostart=true
autorestart=true
stderr_logfile=/var/log/zentravision/celery.err.log
stdout_logfile=/var/log/zentravision/celery.out.log
```

4. **Nginx + Gunicorn**
```bash
pip install gunicorn
gunicorn zentravision.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

## 🛠️ Desarrollo

### Estructura de Modelos Principales

```python
# GlosaDocument - Documento principal con soporte para batches
class GlosaDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    original_file = models.FileField(upload_to='uploads/glosas/%Y/%m/')
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField()
    status = models.CharField(max_length=20)  # pending, processing, completed, error
    strategy = models.CharField(max_length=20)  # hybrid, ai_only, ocr_only
    extracted_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    
    # Campos para manejo de documentos múltiples
    parent_document = models.ForeignKey('self', null=True, blank=True)
    is_master_document = models.BooleanField(default=False)
    patient_section_number = models.PositiveIntegerField(null=True)
    total_sections = models.PositiveIntegerField(null=True)
    
    # Propiedades utilitarias
    @property
    def liquidacion_numero(self):
        # Extrae número de liquidación de extracted_data
    
    @property
    def valor_reclamacion(self):
        # Extrae valor de reclamación de extracted_data

# ProcessingBatch - Gestión de batches de documentos múltiples
class ProcessingBatch(models.Model):
    master_document = models.OneToOneField(GlosaDocument)
    total_documents = models.PositiveIntegerField()
    completed_documents = models.PositiveIntegerField(default=0)
    failed_documents = models.PositiveIntegerField(default=0)
    batch_status = models.CharField(max_length=20)  # splitting, processing, completed, error
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    @property
    def progress_percentage(self):
        # Calcula porcentaje de progreso
    
# ProcessingLog - Logs detallados de procesamiento
class ProcessingLog(models.Model):
    glosa = models.ForeignKey(GlosaDocument, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10)  # INFO, WARNING, ERROR
    message = models.TextField()
```

### Arquitectura del Extractor

```python
# Extractor principal con múltiples estrategias
class MedicalClaimExtractor:
    def extract_from_pdf(self, pdf_path: str, strategy: str = 'hybrid'):
        # 1. Extracción de texto con PyMuPDF
        # 2. Procesamiento con regex (OCR tradicional)
        # 3. Análisis con OpenAI GPT-4o-mini (IA)
        # 4. Merge inteligente de resultados
        # 5. Validación y limpieza de datos
```

## 📈 Monitoreo y Rendimiento

### Métricas de la Aplicación
- **Tiempo promedio de procesamiento**: ~15 segundos por paciente
- **Precisión de extracción**: >95% con estrategia híbrida
- **Soporte de documentos**: Hasta 50 pacientes por PDF
- **Formatos soportados**: PDF con texto extraíble
- **Tamaño máximo**: 10MB por archivo

### Logs de Sistema
```bash
# Logs de Django
tail -f logs/django.log

# Logs de Celery
tail -f logs/celery.log

# Logs de Redis
redis-cli monitor
```

### Dashboard de Estadísticas
- Total de glosas procesadas
- Batches completados vs fallidos
- Tiempo promedio de procesamiento
- Valor total de reclamaciones procesadas
- Gráficos de progreso en tiempo real

## 🔒 Seguridad y Validaciones

- **Autenticación obligatoria** para todas las funcionalidades
- **Validación de archivos**: Solo PDFs, máximo 10MB
- **Sanitización de datos** extraídos y inputs de usuario
- **Protección CSRF** en todos los formularios
- **Logs de auditoría** para todas las operaciones
- **Validación de códigos médicos** (CUPS, CIE-10)
- **Limitación de rate** para APIs externas

## 🤝 Contribución

1. Fork el repositorio
2. Crear rama para nueva característica:
   ```bash
   git checkout -b feature/nombre-caracteristica
   ```
3. Hacer commits descriptivos:
   ```bash
   git commit -m "feat: agregar extracción de diagnósticos adicionales"
   ```
4. Push a la rama:
   ```bash
   git push origin feature/nombre-caracteristica
   ```
5. Crear Pull Request con descripción detallada

### Estándares de Código
- **PEP 8** para Python
- **Docstrings** en todas las funciones públicas
- **Type hints** cuando sea apropiado
- **Tests unitarios** para funcionalidades críticas
- **Logs descriptivos** para debugging

## 📞 Soporte y Contacto

- **Documentación**: [Wiki del proyecto](https://github.com/tu-usuario/zentravision/wiki)
- **Issues**: [GitHub Issues](https://github.com/tu-usuario/zentravision/issues)
- **Discusiones**: [GitHub Discussions](https://github.com/tu-usuario/zentravision/discussions)
- **Email**: soporte@zentravision.com

## 📄 Licencia

Este proyecto está bajo la **Licencia MIT** - ver el archivo [LICENSE](LICENSE) para más detalles.

## 🏆 Casos de Uso Exitosos

- **IPS Medianas**: Procesamiento de 100+ glosas diarias
- **Aseguradoras**: Análisis masivo de reclamaciones SOAT
- **Auditorías Médicas**: Validación automática de procedimientos
- **Consultorías**: Análisis de patrones de objeción

## 🔄 Changelog

### v1.3.0 (2025-07-29) - 🚀 VERSIÓN ACTUAL
- ✅ **Panel de Administración Django Mejorado**: Visualización detallada de información del paciente y procedimientos
- ✅ **División automática de PDFs múltiples**
- ✅ **Sistema de batches con procesamiento asíncrono**
- ✅ **Gestión completa de documentos padre/hijo**
- ✅ **Descargas masivas (CSV consolidado, ZIP)**
- ✅ **OpenAI GPT-4o-mini integrado**
- ✅ **Extracción de observaciones de glosas**
- ✅ **Dashboard mejorado con estadísticas de batches**
- ✅ **Comandos de gestión y limpieza**
- ✅ **Soporte mejorado para caracteres especiales en CSV**
- ✅ **Logs de procesamiento detallados con niveles INFO/WARNING/ERROR**

### v1.2.0 (2025-07-10)
- ✅ **División automática de PDFs múltiples**
- ✅ **Sistema de batches con procesamiento asíncrono**
- ✅ **Gestión completa de documentos padre/hijo**
- ✅ **Descargas masivas (CSV consolidado, ZIP)**
- ✅ **Dashboard mejorado con estadísticas de batches**
- ✅ **Comandos de gestión y limpieza**

### v1.1.0 (2025-01-15)
- Mejoras en extracción de procedimientos
- Soporte para códigos CUPS compuestos
- Validaciones médicas automáticas
- Exportación en formato Excel IPS

### v1.0.0 (2025-01-10)
- Lanzamiento inicial
- Extracción básica de glosas SOAT
- Integración con OpenAI GPT-4
- Dashboard básico
- Exportación JSON/CSV

---

<div align="center">

**🔬 Zentravision** - *Extracción inteligente de glosas médicas SOAT*

*Desarrollado por Zentratek con ❤️ para Bonsana IPS*

![Made with Python](https://img.shields.io/badge/Made%20with-Python-blue?style=for-the-badge&logo=python)
![Powered by OpenAI](https://img.shields.io/badge/Powered%20by-OpenAI-orange?style=for-the-badge&logo=openai)
![Built with Django](https://img.shields.io/badge/Built%20with-Django-green?style=for-the-badge&logo=django)

</div>