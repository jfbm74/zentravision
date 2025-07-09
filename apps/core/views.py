from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, Http404
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from django.conf import settings
import json
import os
import logging

from .models import GlosaDocument, ProcessingLog
from .forms import GlosaUploadForm

# Importar el extractor directamente para procesamiento síncrono
from apps.extractor.medical_claim_extractor import MedicalClaimExtractor

logger = logging.getLogger(__name__)

@login_required
def dashboard(request):
    """Dashboard principal con estadísticas"""
    try:
        # Estadísticas básicas
        total_glosas = GlosaDocument.objects.filter(user=request.user).count()
        completed_glosas = GlosaDocument.objects.filter(
            user=request.user, 
            status='completed'
        ).count()
        
        processing_glosas = GlosaDocument.objects.filter(
            user=request.user, 
            status='processing'
        ).count()
        
        error_glosas = GlosaDocument.objects.filter(
            user=request.user, 
            status='error'
        ).count()
        
        # Glosas recientes
        recent_glosas = GlosaDocument.objects.filter(
            user=request.user
        ).order_by('-created_at')[:5]
        
        # Datos para gráficos
        status_data = {
            'completed': completed_glosas,
            'processing': processing_glosas,
            'error': error_glosas,
            'pending': total_glosas - completed_glosas - processing_glosas - error_glosas
        }
        
        context = {
            'total_glosas': total_glosas,
            'completed_glosas': completed_glosas,
            'processing_glosas': processing_glosas,
            'error_glosas': error_glosas,
            'recent_glosas': recent_glosas,
            'status_data': json.dumps(status_data),
            'success_rate': round((completed_glosas / total_glosas * 100) if total_glosas > 0 else 0, 1)
        }
        
        return render(request, 'dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Error en dashboard: {str(e)}")
        messages.error(request, "Error cargando el dashboard")
        return render(request, 'dashboard.html', {'total_glosas': 0})

@login_required
def upload_glosa(request):
    """Subida y procesamiento de glosas"""
    if request.method == 'POST':
        form = GlosaUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            try:
                # Crear el objeto GlosaDocument
                glosa = form.save(commit=False)
                glosa.user = request.user
                glosa.status = 'processing'
                glosa.save()
                
                # Log de inicio
                ProcessingLog.objects.create(
                    glosa=glosa,
                    message="Iniciando procesamiento",
                    level='info'
                )
                
                # Procesar el documento inmediatamente (síncrono)
                success = process_glosa_document_sync(glosa.id)
                
                if success:
                    messages.success(request, f'Glosa "{glosa.file_name}" procesada correctamente')
                    return redirect('glosa_detail', glosa_id=glosa.id)
                else:
                    messages.warning(request, f'Glosa "{glosa.file_name}" subida, pero hubo problemas en el procesamiento')
                    return redirect('glosa_detail', glosa_id=glosa.id)
                    
            except Exception as e:
                logger.error(f"Error subiendo glosa: {str(e)}")
                messages.error(request, f"Error procesando el archivo: {str(e)}")
                return redirect('upload_glosa')
        else:
            messages.error(request, "Error en el formulario. Revisa los datos.")
    else:
        form = GlosaUploadForm()
    
    return render(request, 'upload.html', {'form': form})

def process_glosa_document_sync(glosa_id):
    """
    Procesa un documento de glosa de forma síncrona
    """
    try:
        glosa = GlosaDocument.objects.get(id=glosa_id)
        
        # Log de inicio (con manejo de errores)
        try:
            ProcessingLog.objects.create(
                glosa=glosa,
                message="Iniciando extracción de datos",
                level='info'
            )
        except:
            logger.info("Iniciando extracción de datos (ProcessingLog no disponible)")
        
        # Obtener la ruta del archivo
        file_path = glosa.original_file.path
        
        if not os.path.exists(file_path):
            ProcessingLog.objects.create(
                glosa=glosa,
                message="Archivo no encontrado",
                level='error'
            )
            glosa.status = 'error'
            glosa.save()
            return False
        
        # Inicializar el extractor
        extractor = MedicalClaimExtractor()
        
        # Determinar estrategia de extracción
        strategy = 'hybrid'  # Por defecto híbrida
        
        ProcessingLog.objects.create(
            glosa=glosa,
            message=f"Extrayendo datos con estrategia: {strategy}",
            level='info'
        )
        
        # Extraer datos
        result = extractor.extract_from_pdf(file_path, strategy=strategy)
        
        if result.get('error'):
            ProcessingLog.objects.create(
                glosa=glosa,
                message=f"Error en extracción: {result['error']}",
                level='error'
            )
            glosa.status = 'error'
            glosa.extracted_data = result
            glosa.save()
            return False
        
        # Guardar datos extraídos
        glosa.extracted_data = result
        glosa.status = 'completed'
        glosa.processed_at = timezone.now()
        
        # Extraer campos específicos para la base de datos
        patient_info = result.get('patient_info', {})
        policy_info = result.get('policy_info', {})
        financial_summary = result.get('financial_summary', {})
        
        # Actualizar campos del modelo (ajustar según el modelo real)
        if hasattr(glosa, 'patient_name'):
            glosa.patient_name = patient_info.get('nombre', '')
        if hasattr(glosa, 'patient_document'):
            glosa.patient_document = patient_info.get('documento', '')
        if hasattr(glosa, 'policy_number'):
            glosa.policy_number = policy_info.get('poliza_numero', '')
        if hasattr(glosa, 'claim_number'):
            glosa.claim_number = policy_info.get('reclamacion_numero', '')
        if hasattr(glosa, 'total_amount'):
            glosa.total_amount = financial_summary.get('total_reclamado', 0.0)
        if hasattr(glosa, 'objected_amount'):
            glosa.objected_amount = financial_summary.get('total_objetado', 0.0)
        
        glosa.save()
        
        ProcessingLog.objects.create(
            glosa=glosa,
            message="Procesamiento completado exitosamente",
            level='success'
        )
        
        logger.info(f"Glosa {glosa_id} procesada exitosamente")
        return True
        
    except GlosaDocument.DoesNotExist:
        logger.error(f"Glosa {glosa_id} no encontrada")
        return False
        
    except Exception as e:
        logger.error(f"Error procesando glosa {glosa_id}: {str(e)}")
        
        try:
            glosa = GlosaDocument.objects.get(id=glosa_id)
            glosa.status = 'error'
            glosa.save()
            
            ProcessingLog.objects.create(
                glosa=glosa,
                message=f"Error inesperado: {str(e)}",
                level='error'
            )
        except:
            pass
            
        return False

@login_required
def glosa_list(request):
    """Lista de glosas con filtros y búsqueda"""
    glosas = GlosaDocument.objects.filter(user=request.user).order_by('-created_at')
    
    # Filtros
    status_filter = request.GET.get('status')
    search_query = request.GET.get('search')
    
    if status_filter:
        glosas = glosas.filter(status=status_filter)
    
    if search_query:
        glosas = glosas.filter(
            Q(file_name__icontains=search_query) |
            Q(patient_name__icontains=search_query) |
            Q(policy_number__icontains=search_query) |
            Q(claim_number__icontains=search_query)
        )
    
    # Paginación
    paginator = Paginator(glosas, 10)  # 10 glosas por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search_query': search_query,
        'total_count': glosas.count()
    }
    
    return render(request, 'glosa_list.html', context)

@login_required
def glosa_detail(request, glosa_id):
    """Detalle de una glosa específica"""
    glosa = get_object_or_404(GlosaDocument, id=glosa_id, user=request.user)
    
    # Obtener logs de procesamiento
    logs = ProcessingLog.objects.filter(glosa=glosa).order_by('-created_at')
    
    # Procesar datos extraídos para mostrar
    extracted_data = glosa.extracted_data or {}
    
    context = {
        'glosa': glosa,
        'logs': logs,
        'extracted_data': extracted_data,
        'patient_info': extracted_data.get('patient_info', {}),
        'policy_info': extracted_data.get('policy_info', {}),
        'procedures': extracted_data.get('procedures', []),
        'financial_summary': extracted_data.get('financial_summary', {}),
        'extraction_details': extracted_data.get('extraction_details', {})
    }
    
    return render(request, 'glosa_detail.html', context)

@login_required
def reprocess_glosa(request, glosa_id):
    """Reprocesar una glosa"""
    if request.method == 'POST':
        glosa = get_object_or_404(GlosaDocument, id=glosa_id, user=request.user)
        
        # Cambiar estado a procesando
        glosa.status = 'processing'
        glosa.save()
        
        ProcessingLog.objects.create(
            glosa=glosa,
            message="Reprocesamiento solicitado por el usuario",
            level='info'
        )
        
        # Procesar de forma síncrona
        success = process_glosa_document_sync(glosa.id)
        
        if success:
            messages.success(request, 'Glosa reprocesada correctamente')
        else:
            messages.error(request, 'Error reprocesando la glosa')
    
    return redirect('glosa_detail', glosa_id=glosa_id)

@login_required
def download_file(request, glosa_id, file_type):
    """Descargar archivos relacionados con la glosa"""
    glosa = get_object_or_404(GlosaDocument, id=glosa_id, user=request.user)
    
    if file_type == 'json':
        # Descargar datos extraídos como JSON
        response = HttpResponse(
            json.dumps(glosa.extracted_data, indent=2, ensure_ascii=False),
            content_type='application/json'
        )
        response['Content-Disposition'] = f'attachment; filename="{glosa.file_name}_extracted.json"'
        return response
    
    elif file_type == 'original':
        # Descargar archivo original
        if glosa.file and os.path.exists(glosa.file.path):
            with open(glosa.file.path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="{glosa.file_name}"'
                return response
    
    raise Http404("Archivo no encontrado")

# API Views
@login_required
def api_glosa_status(request, glosa_id):
    """API endpoint para obtener estado de una glosa"""
    try:
        glosa = GlosaDocument.objects.get(id=glosa_id, user=request.user)
        
        data = {
            'status': glosa.status,
            'file_name': glosa.file_name,
            'uploaded_at': glosa.uploaded_at.isoformat(),
            'processed_at': glosa.processed_at.isoformat() if glosa.processed_at else None,
            'patient_name': glosa.patient_name,
            'total_amount': float(glosa.total_amount) if glosa.total_amount else 0,
            'has_extracted_data': bool(glosa.extracted_data)
        }
        
        return JsonResponse(data)
        
    except GlosaDocument.DoesNotExist:
        return JsonResponse({'error': 'Glosa no encontrada'}, status=404)