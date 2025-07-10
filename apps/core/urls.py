# ==========================================
# apps/core/urls.py
# ==========================================
# ==========================================
# apps/core/urls.py - MEJORADO
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
    
    # Gestión de glosas
    path('upload/', views.upload_glosa, name='upload_glosa'),
    path('glosas/', views.glosa_list, name='glosa_list'),
    path('glosas/<uuid:glosa_id>/', views.glosa_detail, name='glosa_detail'),
    path('glosas/<uuid:glosa_id>/reprocess/', views.reprocess_glosa, name='reprocess_glosa'),
    
    # Descargas - MEJORADO con nuevos formatos
    path('download/<uuid:glosa_id>/<str:file_type>/', views.download_file, name='download_file'),
    
    # API endpoints
    path('api/glosas/<uuid:glosa_id>/status/', views.api_glosa_status, name='api_glosa_status'),
]

# Formatos de descarga disponibles:
# - 'json': Datos extraídos en formato JSON
# - 'csv': CSV en formato Excel IPS (NUEVO - formato principal)
# - 'csv_legacy': CSV en formato anterior (para compatibilidad)
# - 'original': Archivo PDF original