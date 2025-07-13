# apps/core/urls.py - URLS COMPLETAS CON APIS DE MONITOREO EN TIEMPO REAL

from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # ========================================================================
    # AUTENTICACIÓN
    # ========================================================================
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # ========================================================================
    # DASHBOARD PRINCIPAL
    # ========================================================================
    path('', views.dashboard, name='dashboard'),
    
    # ========================================================================
    # GESTIÓN DE GLOSAS INDIVIDUALES
    # ========================================================================
    path('upload/', views.upload_glosa, name='upload_glosa'),
    path('glosas/', views.glosa_list, name='glosa_list'),
    path('glosas/<uuid:glosa_id>/', views.glosa_detail, name='glosa_detail'),
    path('glosas/<uuid:glosa_id>/reprocess/', views.reprocess_glosa, name='reprocess_glosa'),
    
    # ========================================================================
    # GESTIÓN DE BATCHES (DOCUMENTOS MÚLTIPLES)
    # ========================================================================
    path('batches/', views.batch_list, name='batch_list'),
    path('batches/<uuid:batch_id>/', views.batch_detail, name='batch_detail'),
    path('batches/<uuid:batch_id>/reprocess/', views.reprocess_batch, name='reprocess_batch'),
    path('batches/<uuid:batch_id>/download/<str:file_type>/', views.download_batch_files, name='download_batch_files'),
    
    # ========================================================================
    # DESCARGAS INDIVIDUALES
    # ========================================================================
    path('download/<uuid:glosa_id>/<str:file_type>/', views.download_file, name='download_file'),
    
    # ========================================================================
    # APIs DE MONITOREO EN TIEMPO REAL - NUEVAS
    # ========================================================================
    path('api/glosas/<uuid:glosa_id>/status/', views.api_glosa_status, name='api_glosa_status'),
    path('api/batches/<uuid:batch_id>/status/', views.api_batch_status, name='api_batch_status'),
]

# ============================================================================
# DOCUMENTACIÓN DE FORMATOS DE DESCARGA DISPONIBLES
# ============================================================================

"""
FORMATOS DE DESCARGA INDIVIDUALES:
- 'json': Datos extraídos en formato JSON estructurado
- 'csv': CSV en formato Excel IPS (compatible con sistemas hospitalarios)
- 'original': Archivo PDF original sin procesar

FORMATOS DE DESCARGA PARA BATCHES:
- 'consolidated_csv': CSV consolidado con todos los pacientes en un archivo
- 'zip_json': ZIP conteniendo archivos JSON individuales de cada paciente
- 'zip_csv': ZIP conteniendo archivos CSV individuales de cada paciente

APIs DE MONITOREO:
- GET /api/glosas/{id}/status/ : Estado en tiempo real de una glosa individual
- GET /api/batches/{id}/status/ : Estado en tiempo real de un batch completo
  
EJEMPLO DE USO DE APIS:
fetch('/api/batches/12345/status/')
.then(response => response.json())
.then(data => {
    console.log('Progreso:', data.progress_percentage + '%');
    console.log('Completados:', data.completed_documents);
    console.log('Total:', data.total_documents);
});

RESPUESTA DE API BATCH:
{
    "batch_id": "uuid",
    "batch_status": "processing|completed|error",
    "total_documents": 48,
    "completed_documents": 32,
    "failed_documents": 2,
    "progress_percentage": 66.7,
    "is_complete": false,
    "has_errors": true,
    "estimated_remaining_seconds": 180,
    "children": [
        {
            "id": "uuid",
            "section_number": 1,
            "status": "completed",
            "patient_name": "Juan Pérez",
            "total_amount": 150000,
            "procedures_count": 5
        }
    ]
}
"""