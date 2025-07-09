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

# Importar el extractor mejorado
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
        
        # Cálculos financieros agregados
        financial_stats = _calculate_financial_stats(request.user)
        
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
            'success_rate': round((completed_glosas / total_glosas * 100) if total_glosas > 0 else 0, 1),
            'financial_stats': financial_stats,
        }
        
        return render(request, 'dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Error en dashboard: {str(e)}")
        messages.error(request, "Error cargando el dashboard")
        return render(request, 'dashboard.html', {'total_glosas': 0})

def _calculate_financial_stats(user):
    """Calcula estadísticas financieras agregadas"""
    try:
        glosas = GlosaDocument.objects.filter(user=user, status='completed')
        
        total_reclamado = 0
        total_objetado = 0
        total_aceptado = 0
        
        for glosa in glosas:
            if glosa.extracted_data and 'financial_summary' in glosa.extracted_data:
                financial = glosa.extracted_data['financial_summary']
                total_reclamado += financial.get('total_reclamado', 0)
                total_objetado += financial.get('total_objetado', 0)
                total_aceptado += financial.get('total_aceptado', 0)
        
        return {
            'total_reclamado': total_reclamado,
            'total_objetado': total_objetado,
            'total_aceptado': total_aceptado,
            'promedio_objetado': (total_objetado / total_reclamado * 100) if total_reclamado > 0 else 0
        }
    except Exception as e:
        logger.error(f"Error calculando estadísticas financieras: {e}")
        return {
            'total_reclamado': 0,
            'total_objetado': 0,
            'total_aceptado': 0,
            'promedio_objetado': 0
        }

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
                
                # Extraer información del archivo
                uploaded_file = request.FILES['original_file']
                glosa.original_filename = uploaded_file.name
                glosa.file_size = uploaded_file.size
                
                glosa.save()
                
                # Log de inicio
                ProcessingLog.objects.create(
                    glosa=glosa,
                    message="Iniciando procesamiento del documento",
                    level='INFO'
                )
                
                # Procesar el documento inmediatamente (síncrono)
                success = process_glosa_document_sync(glosa.id)
                
                if success:
                    messages.success(request, f'Glosa "{glosa.original_filename}" procesada correctamente')
                    return redirect('glosa_detail', glosa_id=glosa.id)
                else:
                    messages.warning(request, f'Glosa "{glosa.original_filename}" subida, pero hubo problemas en el procesamiento')
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
    Procesa un documento de glosa de forma síncrona con el extractor mejorado
    """
    try:
        glosa = GlosaDocument.objects.get(id=glosa_id)
        
        # Log de inicio
        try:
            ProcessingLog.objects.create(
                glosa=glosa,
                message="Iniciando extracción de datos con algoritmos mejorados",
                level='INFO'
            )
        except:
            logger.info("Iniciando extracción de datos (ProcessingLog no disponible)")
        
        # Obtener la ruta del archivo
        file_path = glosa.original_file.path
        
        if not os.path.exists(file_path):
            ProcessingLog.objects.create(
                glosa=glosa,
                message="Archivo no encontrado en el sistema",
                level='ERROR'
            )
            glosa.status = 'error'
            glosa.error_message = "Archivo no encontrado"
            glosa.save()
            return False
        
        # Inicializar el extractor mejorado
        openai_api_key = getattr(settings, 'OPENAI_API_KEY', None)
        extractor = MedicalClaimExtractor(openai_api_key=openai_api_key)
        
        # Determinar estrategia de extracción
        strategy = glosa.strategy if hasattr(glosa, 'strategy') else 'hybrid'
        
        ProcessingLog.objects.create(
            glosa=glosa,
            message=f"Extrayendo datos con estrategia: {strategy}",
            level='INFO'
        )
        
        # Extraer datos con el nuevo extractor
        start_time = timezone.now()
        result = extractor.extract_from_pdf(file_path, strategy=strategy)
        end_time = timezone.now()
        
        processing_time = (end_time - start_time).total_seconds()
        
        if result.get('error'):
            ProcessingLog.objects.create(
                glosa=glosa,
                message=f"Error en extracción: {result['error']}",
                level='ERROR'
            )
            glosa.status = 'error'
            glosa.error_message = result['error']
            glosa.extracted_data = result
            glosa.save()
            return False
        
        # Guardar datos extraídos
        glosa.extracted_data = result
        glosa.status = 'completed'
        glosa.updated_at = timezone.now()
        
        # Extraer campos específicos para facilitar consultas
        _update_glosa_fields_from_extraction(glosa, result)
        
        glosa.save()
        
        # Log de éxito con estadísticas
        extraction_stats = result.get('extraction_details', {})
        ProcessingLog.objects.create(
            glosa=glosa,
            message=f"Procesamiento completado en {processing_time:.2f}s. "
                   f"Campos extraídos: {extraction_stats.get('campos_extraidos', 0)}, "
                   f"Calidad: {extraction_stats.get('calidad_extraccion', 'desconocida')}",
            level='INFO'
        )
        
        logger.info(f"Glosa {glosa_id} procesada exitosamente en {processing_time:.2f}s")
        return True
        
    except GlosaDocument.DoesNotExist:
        logger.error(f"Glosa {glosa_id} no encontrada")
        return False
        
    except Exception as e:
        logger.error(f"Error procesando glosa {glosa_id}: {str(e)}")
        
        try:
            glosa = GlosaDocument.objects.get(id=glosa_id)
            glosa.status = 'error'
            glosa.error_message = str(e)
            glosa.save()
            
            ProcessingLog.objects.create(
                glosa=glosa,
                message=f"Error inesperado: {str(e)}",
                level='ERROR'
            )
        except:
            pass
            
        return False

def _update_glosa_fields_from_extraction(glosa, extraction_result):
    """Actualiza campos del modelo con datos extraídos para facilitar consultas"""
    try:
        # Información del paciente
        patient_info = extraction_result.get('patient_info', {})
        if hasattr(glosa, 'patient_name'):
            glosa.patient_name = patient_info.get('nombre', '')[:255]
        if hasattr(glosa, 'patient_document'):
            glosa.patient_document = patient_info.get('documento', '')[:50]
        
        # Información de la póliza
        policy_info = extraction_result.get('policy_info', {})
        if hasattr(glosa, 'policy_number'):
            glosa.policy_number = policy_info.get('poliza', '')[:100]
        if hasattr(glosa, 'claim_number'):
            glosa.claim_number = policy_info.get('numero_reclamacion', '')[:100]
        
        # Información financiera
        financial = extraction_result.get('financial_summary', {})
        if hasattr(glosa, 'total_amount'):
            glosa.total_amount = financial.get('total_reclamado', 0.0)
        if hasattr(glosa, 'objected_amount'):
            glosa.objected_amount = financial.get('total_objetado', 0.0)
        if hasattr(glosa, 'accepted_amount'):
            glosa.accepted_amount = financial.get('total_aceptado', 0.0)
        
        # Estadísticas de extracción
        extraction_details = extraction_result.get('extraction_details', {})
        if hasattr(glosa, 'extraction_quality'):
            glosa.extraction_quality = extraction_details.get('calidad_extraccion', 'desconocida')
        if hasattr(glosa, 'extracted_fields_count'):
            glosa.extracted_fields_count = extraction_details.get('campos_extraidos', 0)
        
    except Exception as e:
        logger.warning(f"Error actualizando campos del modelo: {e}")

@login_required
def glosa_list(request):
    """Lista de glosas con filtros y búsqueda mejorados"""
    glosas = GlosaDocument.objects.filter(user=request.user).order_by('-created_at')
    
    # Filtros
    status_filter = request.GET.get('status')
    search_query = request.GET.get('search')
    
    if status_filter:
        glosas = glosas.filter(status=status_filter)
    
    if search_query:
        glosas = glosas.filter(
            Q(original_filename__icontains=search_query) |
            Q(extracted_data__patient_info__nombre__icontains=search_query) |
            Q(extracted_data__policy_info__poliza__icontains=search_query) |
            Q(extracted_data__policy_info__numero_reclamacion__icontains=search_query)
        )
    
    # Paginación
    paginator = Paginator(glosas, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'glosas': page_obj.object_list,  # Para compatibilidad con el template
        'status_filter': status_filter,
        'search_query': search_query,
        'total_count': glosas.count(),
        'is_paginated': page_obj.has_other_pages()
    }
    
    return render(request, 'glosa_list.html', context)

@login_required
def glosa_detail(request, glosa_id):
    """Detalle de una glosa específica con información mejorada"""
    glosa = get_object_or_404(GlosaDocument, id=glosa_id, user=request.user)
    
    # Obtener logs de procesamiento
    logs = ProcessingLog.objects.filter(glosa=glosa).order_by('-timestamp')
    
    # Procesar datos extraídos para mostrar
    extracted_data = glosa.extracted_data or {}
    
    # Preparar información adicional para el template
    liquidacion_numero = _get_liquidacion_numero(glosa)
    valor_reclamacion = _get_valor_reclamacion(glosa)
    
    context = {
        'glosa': glosa,
        'logs': logs,
        'extracted_data': extracted_data,
        'patient_info': extracted_data.get('patient_info', {}),
        'policy_info': extracted_data.get('policy_info', {}),
        'procedures': extracted_data.get('procedures', []),
        'financial_summary': extracted_data.get('financial_summary', {}),
        'diagnostics': extracted_data.get('diagnostics', []),
        'ips_info': extracted_data.get('ips_info', {}),
        'extraction_details': extracted_data.get('extraction_details', {}),
        'metadata': extracted_data.get('metadata', {}),
        'liquidacion_numero': liquidacion_numero,
        'valor_reclamacion': valor_reclamacion,
    }
    
    return render(request, 'glosa_detail.html', context)

def _get_liquidacion_numero(glosa):
    """Obtiene número de liquidación de los datos extraídos"""
    if glosa.extracted_data and 'policy_info' in glosa.extracted_data:
        return glosa.extracted_data['policy_info'].get('numero_liquidacion', 'N/A')
    return 'N/A'

def _get_valor_reclamacion(glosa):
    """Obtiene valor de reclamación de los datos extraídos"""
    if glosa.extracted_data and 'financial_summary' in glosa.extracted_data:
        return glosa.extracted_data['financial_summary'].get('total_reclamado', 0)
    return 0

@login_required
def reprocess_glosa(request, glosa_id):
    """Reprocesar una glosa con el extractor mejorado"""
    if request.method == 'POST':
        glosa = get_object_or_404(GlosaDocument, id=glosa_id, user=request.user)
        
        # Cambiar estado a procesando
        glosa.status = 'processing'
        glosa.error_message = None  # Limpiar errores previos
        glosa.save()
        
        ProcessingLog.objects.create(
            glosa=glosa,
            message="Reprocesamiento solicitado por el usuario",
            level='INFO'
        )
        
        # Procesar de forma síncrona con extractor mejorado
        success = process_glosa_document_sync(glosa.id)
        
        if success:
            messages.success(request, 'Glosa reprocesada correctamente con algoritmos mejorados')
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
            content_type='application/json; charset=utf-8'
        )
        response['Content-Disposition'] = f'attachment; filename="{glosa.original_filename}_extracted.json"'
        return response
    
    elif file_type == 'csv':
        # Generar CSV de procedimientos si existen
        import csv
        from io import StringIO
        
        output = StringIO()
        
        procedures = glosa.extracted_data.get('procedures', [])
        if procedures:
            writer = csv.writer(output)
            
            # Headers
            writer.writerow([
                'Código', 'Descripción', 'Cantidad', 'Valor Unitario', 
                'Valor Total', 'Valor Objetado', 'Estado'
            ])
            
            # Data
            for proc in procedures:
                writer.writerow([
                    proc.get('codigo', ''),
                    proc.get('descripcion', ''),
                    proc.get('cantidad', 0),
                    proc.get('valor_unitario', 0),
                    proc.get('valor_total', 0),
                    proc.get('valor_objetado', 0),
                    proc.get('estado', 'pendiente')
                ])
        
        response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{glosa.original_filename}_procedures.csv"'
        return response
    
    elif file_type == 'original':
        # Descargar archivo original
        if glosa.original_file and os.path.exists(glosa.original_file.path):
            with open(glosa.original_file.path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="{glosa.original_filename}"'
                return response
    
    raise Http404("Archivo no encontrado")

# API Views
@login_required
def api_glosa_status(request, glosa_id):
    """API endpoint para obtener estado de una glosa"""
    try:
        glosa = GlosaDocument.objects.get(id=glosa_id, user=request.user)
        
        # Calcular progreso basado en logs
        total_steps = 5  # Estimado de pasos de procesamiento
        completed_steps = ProcessingLog.objects.filter(
            glosa=glosa, 
            level='INFO'
        ).count()
        
        progress = min((completed_steps / total_steps) * 100, 100) if glosa.status == 'processing' else 100
        
        data = {
            'status': glosa.status,
            'original_filename': glosa.original_filename,
            'created_at': glosa.created_at.isoformat(),
            'updated_at': glosa.updated_at.isoformat(),
            'progress': progress,
            'has_extracted_data': bool(glosa.extracted_data),
            'error_message': glosa.error_message,
        }
        
        # Añadir información extraída si está disponible
        if glosa.extracted_data:
            patient_info = glosa.extracted_data.get('patient_info', {})
            financial = glosa.extracted_data.get('financial_summary', {})
            
            data.update({
                'patient_name': patient_info.get('nombre', ''),
                'total_amount': financial.get('total_reclamado', 0),
                'total_procedures': len(glosa.extracted_data.get('procedures', [])),
                'extraction_quality': glosa.extracted_data.get('extraction_details', {}).get('calidad_extraccion', 'unknown')
            })
        
        return JsonResponse(data)
        
    except GlosaDocument.DoesNotExist:
        return JsonResponse({'error': 'Glosa no encontrada'}, status=404)