# ==========================================
# apps/core/urls.py - ACTUALIZADO CON SOPORTE PARA BATCHES
# ==========================================

from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Autenticación
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # Dashboard principal
    path('', views.dashboard, name='dashboard'),
    
    # Gestión de glosas individuales
    path('upload/', views.upload_glosa, name='upload_glosa'),
    path('glosas/', views.glosa_list, name='glosa_list'),
    path('glosas/<uuid:glosa_id>/', views.glosa_detail, name='glosa_detail'),
    path('glosas/<uuid:glosa_id>/reprocess/', views.reprocess_glosa, name='reprocess_glosa'),
    
    # Gestión de batches (documentos múltiples)
    path('batches/', views.batch_list, name='batch_list'),
    path('batches/<uuid:batch_id>/', views.batch_detail, name='batch_detail'),
    path('batches/<uuid:batch_id>/reprocess/', views.reprocess_batch, name='reprocess_batch'),
    path('batches/<uuid:batch_id>/download/<str:file_type>/', views.download_batch_files, name='download_batch_files'),
    
    # Descargas individuales
    path('download/<uuid:glosa_id>/<str:file_type>/', views.download_file, name='download_file'),
    
    # API endpoints
    path('api/glosas/<uuid:glosa_id>/status/', views.api_glosa_status, name='api_glosa_status'),
]

# Formatos de descarga disponibles:
# 
# INDIVIDUALES:
# - 'json': Datos extraídos en formato JSON
# - 'csv': CSV en formato Excel IPS
# - 'original': Archivo PDF original
#
# BATCHES:
# - 'consolidated_csv': CSV consolidado con todos los pacientes
# - 'zip_json': ZIP con archivos JSON de cada paciente
# - 'zip_csv': ZIP con archivos CSV de cada paciente