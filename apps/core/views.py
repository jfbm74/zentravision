# ==========================================
# apps/core/views.py
# ==========================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, Http404, HttpResponse
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.db.models import Q
import json
import os
from .models import GlosaDocument, ProcessingLog
from .forms import GlosaUploadForm
from apps.extractor.tasks import process_glosa_document

@login_required
def dashboard(request):
    """Vista principal del dashboard"""
    
    # Estadísticas del usuario
    total_docs = GlosaDocument.objects.filter(user=request.user).count()
    completed_docs = GlosaDocument.objects.filter(user=request.user, status='completed').count()
    processing_docs = GlosaDocument.objects.filter(user=request.user, status='processing').count()
    error_docs = GlosaDocument.objects.filter(user=request.user, status='error').count()
    
    # Documentos recientes
    recent_docs = GlosaDocument.objects.filter(user=request.user)[:5]
    
    context = {
        'stats': {
            'total': total_docs,
            'completed': completed_docs,
            'processing': processing_docs,
            'errors': error_docs,
        },
        'recent_docs': recent_docs,
    }
    
    return render(request, 'dashboard.html', context)

@login_required
def upload_glosa(request):
    """Vista para subir nuevas glosas"""
    
    if request.method == 'POST':
        form = GlosaUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            glosa = form.save(commit=False)
            glosa.user = request.user
            glosa.original_filename = request.FILES['original_file'].name
            glosa.file_size = request.FILES['original_file'].size
            glosa.save()
            
            # Iniciar procesamiento asíncrono
            process_glosa_document.delay(str(glosa.id))
            
            messages.success(request, f'Documento "{glosa.original_filename}" subido exitosamente. Se está procesando...')
            return redirect('dashboard')
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = GlosaUploadForm()
    
    return render(request, 'upload.html', {'form': form})

@method_decorator(login_required, name='dispatch')
class GlosaListView(ListView):
    """Vista de lista de glosas del usuario"""
    
    model = GlosaDocument
    template_name = 'glosa_list.html'
    context_object_name = 'glosas'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = GlosaDocument.objects.filter(user=self.request.user)
        
        # Filtros
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(original_filename__icontains=search) |
                Q(extracted_data__header__liquidacion_numero__icontains=search)
            )
        
        return queryset.order_by('-created_at')

@login_required
def glosa_detail(request, glosa_id):
    """Vista de detalle de una glosa específica"""
    
    glosa = get_object_or_404(GlosaDocument, id=glosa_id, user=request.user)
    logs = ProcessingLog.objects.filter(glosa=glosa)[:10]
    
    context = {
        'glosa': glosa,
        'logs': logs,
    }
    
    return render(request, 'glosa_detail.html', context)

@login_required
@require_http_methods(["GET"])
def download_file(request, glosa_id, file_type):
    """Vista para descargar archivos procesados"""
    
    glosa = get_object_or_404(GlosaDocument, id=glosa_id, user=request.user)
    
    if file_type == 'json' and glosa.json_output:
        file_path = glosa.json_output.path
        filename = f"glosa_{glosa.liquidacion_numero}.json"
        content_type = 'application/json'
    elif file_type == 'csv' and glosa.csv_output:
        file_path = glosa.csv_output.path
        filename = f"glosa_{glosa.liquidacion_numero}.csv"
        content_type = 'text/csv'
    else:
        raise Http404("Archivo no encontrado")
    
    if os.path.exists(file_path):
        with open(file_path, 'rb') as file:
            response = HttpResponse(file.read(), content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
    else:
        raise Http404("Archivo no encontrado en el sistema")

@login_required
def api_glosa_status(request, glosa_id):
    """API para obtener el estado de una glosa"""
    
    glosa = get_object_or_404(GlosaDocument, id=glosa_id, user=request.user)
    
    data = {
        'id': str(glosa.id),
        'status': glosa.status,
        'progress': 100 if glosa.status == 'completed' else (50 if glosa.status == 'processing' else 0),
        'has_results': bool(glosa.extracted_data),
        'error_message': glosa.error_message,
    }
    
    return JsonResponse(data)

@login_required
@require_http_methods(["POST"])
def reprocess_glosa(request, glosa_id):
    """Vista para reprocesar una glosa"""
    
    glosa = get_object_or_404(GlosaDocument, id=glosa_id, user=request.user)
    
    if glosa.status in ['completed', 'error']:
        glosa.status = 'pending'
        glosa.extracted_data = None
        glosa.error_message = None
        glosa.save()
        
        # Reiniciar procesamiento
        process_glosa_document.delay(str(glosa.id))
        
        messages.success(request, 'Documento enviado para reprocesamiento.')
    else:
        messages.warning(request, 'El documento ya está siendo procesado.')
    
    return redirect('glosa_detail', glosa_id=glosa_id)