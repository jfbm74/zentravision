# ==========================================
# apps/core/urls.py
# ==========================================

from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Autenticación
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # Vistas principales
    path('', views.dashboard, name='dashboard'),
    path('upload/', views.upload_glosa, name='upload_glosa'),
    path('glosas/', views.GlosaListView.as_view(), name='glosa_list'),
    path('glosas/<uuid:glosa_id>/', views.glosa_detail, name='glosa_detail'),
    path('glosas/<uuid:glosa_id>/reprocess/', views.reprocess_glosa, name='reprocess_glosa'),
    
    # Descargas
    path('download/<uuid:glosa_id>/<str:file_type>/', views.download_file, name='download_file'),
    
    # API
    path('api/glosas/<uuid:glosa_id>/status/', views.api_glosa_status, name='api_glosa_status'),
]