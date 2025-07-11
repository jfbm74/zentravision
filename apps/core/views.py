from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, Http404
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from django.conf import settings
from django.core.files.base import ContentFile
import json
import os
import logging
import zipfile
import io

from .models import GlosaDocument, ProcessingLog, ProcessingBatch
from .forms import GlosaUploadForm

# Importar el extractor mejorado y el divisor de PDFs
from apps.extractor.medical_claim_extractor_fixed import MedicalClaimExtractor
from apps.extractor.pdf_splitter import GlosaPDFSplitter

logger = logging.getLogger(__name__)

@login_required
def dashboard(request):
    """Dashboard principal con estadísticas incluyendo batches"""
    try:
        # Estadísticas básicas (incluir solo documentos padre y únicos)
        all_glosas = GlosaDocument.objects.filter(user=request.user)
        
        # Documentos únicos (no contar los hijos)
        unique_glosas = all_glosas.filter(
            Q(parent_document__isnull=True)  # Documentos sin padre
        )
        
        total_glosas = unique_glosas.count()
        completed_glosas = unique_glosas.filter(status='completed').count()
        processing_glosas = unique_glosas.filter(status='processing').count()
        error_glosas = unique_glosas.filter(status='error').count()
        
        # Glosas recientes (incluir batches)
        recent_glosas = unique_glosas.order_by('-created_at')[:5]
        
        # Estadísticas de batches
        total_batches = ProcessingBatch.objects.filter(
            master_document__user=request.user
        ).count()
        
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
            'total_batches': total_batches,
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
        # Incluir todos los documentos completados (padres e hijos)
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
    """Subida y procesamiento de glosas con división automática"""
    if request.method == 'POST':
        form = GlosaUploadForm(request.POST, request.FILES)
        
        if form.is_valid():
            try:
                # Crear el objeto GlosaDocument maestro
                master_glosa = form.save(commit=False)
                master_glosa.user = request.user
                master_glosa.status = 'processing'
                
                uploaded_file = request.FILES['original_file']
                master_glosa.original_filename = uploaded_file.name
                master_glosa.file_size = uploaded_file.size
                
                master_glosa.save()
                
                # Log de inicio
                ProcessingLog.objects.create(
                    glosa=master_glosa,
                    message="Iniciando análisis del documento",
                    level='INFO'
                )
                
                # Procesar división y extracción
                return process_pdf_splitting(request, master_glosa)
                
            except Exception as e:
                logger.error(f"Error subiendo glosa: {str(e)}")
                messages.error(request, f"Error procesando el archivo: {str(e)}")
                return redirect('upload_glosa')
        else:
            messages.error(request, "Error en el formulario. Revisa los datos.")
    else:
        form = GlosaUploadForm()
    
    return render(request, 'upload.html', {'form': form})

def process_pdf_splitting(request, master_glosa):
    """Procesa la división del PDF y crea documentos hijos si es necesario"""
    try:
        # Inicializar divisor
        splitter = GlosaPDFSplitter()
        
        # Validar formato del PDF
        is_valid, validation_message = splitter.validate_pdf_format(master_glosa.original_file.path)
        
        if not is_valid:
            ProcessingLog.objects.create(
                glosa=master_glosa,
                message=f"Formato de PDF no válido: {validation_message}",
                level='WARNING'
            )
            # Continuar con procesamiento normal
        
        # Intentar dividir PDF
        try:
            sections = splitter.split_pdf(master_glosa.original_file.path)
        except Exception as e:
            logger.warning(f"Error dividiendo PDF, procesando como documento único: {e}")
            sections = []
        
        if len(sections) <= 0:
            # PDF de un solo paciente - procesar normalmente
            ProcessingLog.objects.create(
                glosa=master_glosa,
                message="Documento de un solo paciente detectado",
                level='INFO'
            )
            
            master_glosa.is_master_document = False
            master_glosa.save()
            
            success = process_glosa_document_sync(master_glosa.id)
            if success:
                messages.success(request, f'Glosa "{master_glosa.original_filename}" procesada correctamente')
                return redirect('glosa_detail', glosa_id=master_glosa.id)
            else:
                messages.warning(request, f'Glosa subida pero hubo problemas en el procesamiento')
                return redirect('glosa_detail', glosa_id=master_glosa.id)
        
        else:
            # PDF múltiple - procesar como batch
            ProcessingLog.objects.create(
                glosa=master_glosa,
                message=f"Documento múltiple detectado: {len(sections)} pacientes",
                level='INFO'
            )
            
            return process_multi_patient_document(request, master_glosa, sections)
            
    except Exception as e:
        logger.error(f"Error en proceso de división: {e}")
        master_glosa.status = 'error'
        master_glosa.error_message = str(e)
        master_glosa.save()
        
        ProcessingLog.objects.create(
            glosa=master_glosa,
            message=f"Error dividiendo PDF: {str(e)}",
            level='ERROR'
        )
        
        messages.error(request, f"Error procesando PDF: {str(e)}")
        return redirect('glosa_detail', glosa_id=master_glosa.id)

def process_multi_patient_document(request, master_glosa, sections):
    """Crea y procesa documentos hijos para cada paciente"""
    try:
        # Marcar como documento maestro
        master_glosa.is_master_document = True
        master_glosa.total_sections = len(sections)
        master_glosa.save()
        
        # Crear batch de procesamiento
        batch = ProcessingBatch.objects.create(
            master_document=master_glosa,
            total_documents=len(sections),
            batch_status='splitting'
        )
        
        ProcessingLog.objects.create(
            glosa=master_glosa,
            message=f"Creando batch con {len(sections)} documentos",
            level='INFO'
        )
        
        # Crear documentos hijos
        child_documents = []
        
        for i, (pdf_content, section_filename, metadata) in enumerate(sections):
            try:
                # Crear documento hijo
                child_glosa = GlosaDocument.objects.create(
                    user=master_glosa.user,
                    parent_document=master_glosa,
                    status='pending',
                    strategy=master_glosa.strategy,
                    original_filename=f"{master_glosa.original_filename}_paciente_{i+1}",
                    file_size=len(pdf_content),
                    patient_section_number=i+1,
                    total_sections=len(sections)
                )
                
                # Guardar archivo PDF dividido
                child_glosa.original_file.save(
                    section_filename,
                    ContentFile(pdf_content),
                    save=True
                )
                
                child_documents.append(child_glosa)
                
                ProcessingLog.objects.create(
                    glosa=child_glosa,
                    message=f"Documento hijo creado (sección {i+1}/{len(sections)})",
                    level='INFO'
                )
                
            except Exception as e:
                logger.error(f"Error creando documento hijo {i+1}: {e}")
                batch.failed_documents += 1
                batch.save()
                continue
        
        if len(child_documents) == 0:
            raise Exception("No se pudo crear ningún documento hijo")
        
        # Iniciar procesamiento asíncrono
        from apps.extractor.tasks import process_batch_documents
        process_batch_documents.delay(batch.id)
        
        ProcessingLog.objects.create(
            glosa=master_glosa,
            message=f"Procesamiento asíncrono iniciado para {len(child_documents)} documentos",
            level='INFO'
        )
        
        messages.success(
            request, 
            f'PDF dividido en {len(child_documents)} pacientes. Procesamiento iniciado en segundo plano.'
        )
        return redirect('batch_detail', batch_id=batch.id)
        
    except Exception as e:
        logger.error(f"Error procesando documento múltiple: {e}")
        master_glosa.status = 'error'
        master_glosa.error_message = str(e)
        master_glosa.save()
        
        if 'batch' in locals():
            batch.batch_status = 'error'
            batch.error_message = str(e)
            batch.save()
        
        messages.error(request, f"Error procesando documento múltiple: {str(e)}")
        return redirect('glosa_detail', glosa_id=master_glosa.id)

def process_glosa_document_sync(glosa_id):
    """Procesa un documento de glosa de forma síncrona"""
    try:
        glosa = GlosaDocument.objects.get(id=glosa_id)
        
        ProcessingLog.objects.create(
            glosa=glosa,
            message="Iniciando extracción de datos",
            level='INFO'
        )
        
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
        
        # Inicializar el extractor
        openai_api_key = settings.OPENAI_API_KEY
        extractor = MedicalClaimExtractor(openai_api_key=openai_api_key)
        
        strategy = glosa.strategy if hasattr(glosa, 'strategy') else 'hybrid'
        
        ProcessingLog.objects.create(
            glosa=glosa,
            message=f"Extrayendo datos con estrategia: {strategy}",
            level='INFO'
        )
        
        # Extraer datos
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
        glosa.save()
        
        # Log de éxito
        extraction_stats = result.get('extraction_details', {})
        ProcessingLog.objects.create(
            glosa=glosa,
            message=f"Procesamiento completado en {processing_time:.2f}s. "
                   f"Campos extraídos: {extraction_stats.get('campos_extraidos', 0)}",
            level='INFO'
        )
        
        logger.info(f"Glosa {glosa_id} procesada exitosamente en {processing_time:.2f}s")
        return True
        
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

@login_required
def glosa_list(request):
    """Lista de glosas mejorada que maneja documentos padre e hijos"""
    # Mostrar solo documentos padre (únicos) por defecto
    glosas = GlosaDocument.objects.filter(
        user=request.user,
        parent_document__isnull=True  # Solo documentos sin padre
    ).order_by('-created_at')
    
    # Filtros
    status_filter = request.GET.get('status')
    search_query = request.GET.get('search')
    document_type = request.GET.get('type', 'all')  # all, single, multiple
    
    if status_filter:
        glosas = glosas.filter(status=status_filter)
    
    if document_type == 'single':
        glosas = glosas.filter(is_master_document=False)
    elif document_type == 'multiple':
        glosas = glosas.filter(is_master_document=True)
    
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
        'glosas': page_obj.object_list,
        'status_filter': status_filter,
        'search_query': search_query,
        'document_type': document_type,
        'total_count': glosas.count(),
        'is_paginated': page_obj.has_other_pages()
    }
    
    return render(request, 'glosa_list.html', context)

@login_required
def glosa_detail(request, glosa_id):
    """Detalle de glosa que maneja documentos padre e hijos"""
    glosa = get_object_or_404(GlosaDocument, id=glosa_id, user=request.user)
    
    # Obtener logs de procesamiento
    logs = ProcessingLog.objects.filter(glosa=glosa).order_by('-timestamp')
    
    # Datos extraídos
    extracted_data = glosa.extracted_data or {}
    
    # Información adicional
    liquidacion_numero = _get_liquidacion_numero(glosa)
    valor_reclamacion = _get_valor_reclamacion(glosa)
    
    # Si es documento maestro, obtener información de hijos
    child_documents = None
    batch = None
    if glosa.is_master_document:
        child_documents = glosa.child_documents.all().order_by('patient_section_number')
        batch = getattr(glosa, 'processing_batch', None)
    
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
        'child_documents': child_documents,
        'batch': batch,
    }
    
    return render(request, 'glosa_detail.html', context)

@login_required
def batch_detail(request, batch_id):
    """Vista detallada del batch de procesamiento"""
    batch = get_object_or_404(
        ProcessingBatch, 
        id=batch_id, 
        master_document__user=request.user
    )
    
    # Actualizar progreso del batch
    batch.update_progress()
    
    child_documents = batch.master_document.child_documents.all().order_by('patient_section_number')
    
    context = {
        'batch': batch,
        'master_document': batch.master_document,
        'child_documents': child_documents,
    }
    
    return render(request, 'batch_detail.html', context)

@login_required
def batch_list(request):
    """Lista de batches de procesamiento"""
    batches = ProcessingBatch.objects.filter(
        master_document__user=request.user
    ).order_by('-created_at')
    
    # Filtros
    status_filter = request.GET.get('status')
    if status_filter:
        batches = batches.filter(batch_status=status_filter)
    
    # Paginación
    paginator = Paginator(batches, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'batches': page_obj.object_list,
        'status_filter': status_filter,
        'is_paginated': page_obj.has_other_pages()
    }
    
    return render(request, 'batch_list.html', context)

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
    """Reprocesar una glosa"""
    if request.method == 'POST':
        glosa = get_object_or_404(GlosaDocument, id=glosa_id, user=request.user)
        
        # Si es documento maestro, reprocesar todos los hijos
        if glosa.is_master_document:
            return reprocess_batch(request, glosa.get_processing_batch.id)
        
        # Reprocesar documento individual
        glosa.status = 'processing'
        glosa.error_message = None
        glosa.save()
        
        ProcessingLog.objects.create(
            glosa=glosa,
            message="Reprocesamiento solicitado por el usuario",
            level='INFO'
        )
        
        success = process_glosa_document_sync(glosa.id)
        
        if success:
            messages.success(request, 'Glosa reprocesada correctamente')
        else:
            messages.error(request, 'Error reprocesando la glosa')
    
    return redirect('glosa_detail', glosa_id=glosa_id)

@login_required
def reprocess_batch(request, batch_id):
    """Reprocesar un batch completo"""
    batch = get_object_or_404(
        ProcessingBatch, 
        id=batch_id, 
        master_document__user=request.user
    )
    
    # Reiniciar estado del batch
    batch.batch_status = 'processing'
    batch.completed_documents = 0
    batch.failed_documents = 0
    batch.completed_at = None
    batch.save()
    
    # Reiniciar documentos hijos
    child_documents = batch.master_document.child_documents.all()
    child_documents.update(status='pending', error_message=None)
    
    # Iniciar reprocesamiento
    from apps.extractor.tasks import process_batch_documents
    process_batch_documents.delay(batch.id)
    
    messages.success(request, f'Reprocesamiento iniciado para {child_documents.count()} documentos')
    return redirect('batch_detail', batch_id=batch.id)

@login_required
def download_file(request, glosa_id, file_type):
    """Descargar archivos relacionados con la glosa"""
    glosa = get_object_or_404(GlosaDocument, id=glosa_id, user=request.user)
    
    if file_type == 'json':
        response = HttpResponse(
            json.dumps(glosa.extracted_data, indent=2, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )
        response['Content-Disposition'] = f'attachment; filename="{glosa.original_filename}_extracted.json"'
        return response
    
    elif file_type == 'csv':
        if glosa.extracted_data:
            try:
                extractor = MedicalClaimExtractor()
                csv_content = extractor.generate_excel_format_csv(glosa.extracted_data)
                
                response = HttpResponse(csv_content, content_type='text/csv; charset=utf-8')
                response['Content-Disposition'] = f'attachment; filename="{glosa.original_filename}_IPS_format.csv"'
                return response
            except Exception as e:
                logger.error(f"Error generando CSV: {e}")
                return _generate_empty_csv(glosa)
        else:
            return _generate_empty_csv(glosa)
    
    elif file_type == 'original':
        if glosa.original_file and os.path.exists(glosa.original_file.path):
            with open(glosa.original_file.path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="{glosa.original_filename}"'
                return response
    
    raise Http404("Archivo no encontrado")

@login_required
def download_batch_files(request, batch_id, file_type):
    """Descarga masiva de archivos del batch"""
    batch = get_object_or_404(
        ProcessingBatch, 
        id=batch_id, 
        master_document__user=request.user
    )
    
    if file_type == 'consolidated_csv':
        return generate_consolidated_csv(batch)
    elif file_type == 'zip_json':
        return generate_batch_zip(batch, 'json')
    elif file_type == 'zip_csv':
        return generate_batch_zip(batch, 'csv')
    
    raise Http404("Tipo de archivo no soportado")


def generate_consolidated_csv(batch):
    """
    Genera un CSV consolidado con todos los pacientes del batch
    CORRECCIÓN: Uso del extractor para generar CSV individual antes de combinar
    """
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Headers consolidados (mismos que en CSV individual + número de sección)
    headers = [
        'NUMERO_SECCION', 'NOMBRE PACIENTE', '# ID', 'FACTURA', 'FECHA FACTURA', 
        'VALOR TOTAL GLOSA', 'CÓDIGO ITEM', 'DETALLE DE GLOSA', 'VALOR ITEM', 
        'VALOR ACEPTADO', 'VALOR NO ACEPTADO', 'RESPUESTA IPS', 'CLASIFICACIÓN GLOSA', 
        'FECHA RECIBIDO GLOSA', 'DIAS GLOSA', 'FECHA RADICADO RESPUESTA', 
        'DIAS RESPUESTA', 'CÓDIGO RADICACIÓN', 'FUNCIONARIO', 'Entidad',
        'DESCRIPCIÓN PROCEDIMIENTO'
    ]
    writer.writerow(headers)
    
    # Procesar cada documento hijo completado
    for child_doc in batch.master_document.child_documents.filter(status='completed').order_by('patient_section_number'):
        if child_doc.extracted_data:
            try:
                # CORRECCIÓN: Usar el extractor para generar CSV correctamente formateado
                extractor = MedicalClaimExtractor()
                csv_content = extractor.generate_excel_format_csv(child_doc.extracted_data)
                
                # CORRECCIÓN: Parsear el CSV usando csv.reader en lugar de split
                csv_reader = csv.reader(StringIO(csv_content))
                csv_lines = list(csv_reader)
                
                # Skip header (primera línea) y procesar datos
                if len(csv_lines) > 1:
                    for line in csv_lines[1:]:  # Skip header
                        if line and any(cell.strip() for cell in line):  # Solo líneas con contenido
                            # CORRECCIÓN: Agregar número de sección al inicio de la fila
                            row_data = [child_doc.patient_section_number] + line
                            
                            # CORRECCIÓN: Asegurar que tenemos exactamente 21 columnas
                            while len(row_data) < 21:
                                row_data.append('')
                            
                            # Truncar si hay más columnas de las esperadas
                            if len(row_data) > 21:
                                row_data = row_data[:21]
                            
                            writer.writerow(row_data)
                            
            except Exception as e:
                logger.error(f"Error procesando documento {child_doc.id} para CSV consolidado: {e}")
                
                # CORRECCIÓN: Agregar fila con datos básicos si falla la extracción
                patient_info = child_doc.extracted_data.get('patient_info', {})
                financial = child_doc.extracted_data.get('financial_summary', {})
                
                basic_row = [
                    child_doc.patient_section_number,
                    patient_info.get('nombre', ''),
                    patient_info.get('documento', ''),
                    '',  # FACTURA
                    '',  # FECHA FACTURA
                    financial.get('total_reclamado', 0),
                    '',  # CÓDIGO ITEM
                    'Error procesando datos',  # DETALLE DE GLOSA
                    0,   # VALOR ITEM
                    0,   # VALOR ACEPTADO
                    0,   # VALOR NO ACEPTADO
                    '',  # RESPUESTA IPS
                    '',  # CLASIFICACIÓN GLOSA
                    '',  # FECHA RECIBIDO GLOSA
                    '',  # DIAS GLOSA
                    '',  # FECHA RADICADO RESPUESTA
                    '',  # DIAS RESPUESTA
                    '',  # CÓDIGO RADICACIÓN
                    '',  # FUNCIONARIO
                    '',  # Entidad
                    ''   # DESCRIPCIÓN PROCEDIMIENTO
                ]
                writer.writerow(basic_row)
                continue
    
    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="batch_{batch.id}_consolidated.csv"'
    return response



def generate_batch_zip(batch, file_type):
    """
    Genera un ZIP con todos los archivos del batch
    CORRECCIÓN: Mejorar el manejo de archivos y validación
    """
    import zipfile
    import io
    
    zip_buffer = io.BytesIO()
    
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            files_added = 0
            
            for child_doc in batch.master_document.child_documents.filter(status='completed').order_by('patient_section_number'):
                try:
                    if not child_doc.extracted_data:
                        logger.warning(f"Documento {child_doc.id} no tiene datos extraídos")
                        continue
                    
                    if file_type == 'json':
                        # CORRECCIÓN: Generar JSON con codificación UTF-8 apropiada
                        json_content = json.dumps(
                            child_doc.extracted_data, 
                            indent=2, 
                            ensure_ascii=False,
                            default=str  # Para manejar objetos no serializables
                        )
                        filename = f"paciente_{child_doc.patient_section_number:02d}_{child_doc.original_filename}.json"
                        zip_file.writestr(filename, json_content.encode('utf-8'))
                        files_added += 1
                    
                    elif file_type == 'csv':
                        # CORRECCIÓN: Usar extractor para generar CSV correctamente
                        extractor = MedicalClaimExtractor()
                        csv_content = extractor.generate_excel_format_csv(child_doc.extracted_data)
                        filename = f"paciente_{child_doc.patient_section_number:02d}_{child_doc.original_filename}.csv"
                        zip_file.writestr(filename, csv_content.encode('utf-8'))
                        files_added += 1
                        
                except Exception as e:
                    logger.error(f"Error agregando archivo {child_doc.id} al ZIP: {e}")
                    continue
            
            if files_added == 0:
                # CORRECCIÓN: Agregar archivo de información si no hay archivos
                info_content = f"""Información del Batch
=====================================

ID del Batch: {batch.id}
Documento Original: {batch.master_document.original_filename}
Fecha de Procesamiento: {batch.created_at.strftime('%d/%m/%Y %H:%M')}
Total de Documentos: {batch.total_documents}
Documentos Completados: {batch.completed_documents}
Documentos con Error: {batch.failed_documents}

Nota: No se encontraron archivos {file_type.upper()} válidos para incluir en este ZIP.
"""
                zip_file.writestr("README.txt", info_content.encode('utf-8'))
                
        logger.info(f"ZIP generado exitosamente: {files_added} archivos incluidos")
        
    except Exception as e:
        logger.error(f"Error creando ZIP para batch {batch.id}: {e}")
        # Crear ZIP de error
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            error_content = f"Error generando archivos: {str(e)}"
            zip_file.writestr("ERROR.txt", error_content.encode('utf-8'))
    
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="batch_{batch.id}_{file_type}_files.zip"'
    return response


# ============================================================================
# MEJORA ADICIONAL: Función auxiliar para validar CSV individual
# ============================================================================

def validate_csv_structure(csv_content: str) -> bool:
    """
    Valida que el CSV tenga la estructura correcta
    """
    try:
        import csv
        from io import StringIO
        
        csv_reader = csv.reader(StringIO(csv_content))
        lines = list(csv_reader)
        
        if len(lines) < 2:  # Debe tener al menos header + 1 fila
            return False
        
        header = lines[0]
        expected_columns = 20  # Sin incluir NUMERO_SECCION
        
        if len(header) != expected_columns:
            logger.warning(f"CSV header tiene {len(header)} columnas, esperadas {expected_columns}")
            return False
        
        # Validar que las filas de datos tengan el número correcto de columnas
        for i, row in enumerate(lines[1:], 1):
            if len(row) != expected_columns:
                logger.warning(f"Fila {i} tiene {len(row)} columnas, esperadas {expected_columns}")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error validando estructura CSV: {e}")
        return False
    


# ============================================================================
# FUNCIÓN DE DEBUGGING PARA INSPECCIONAR PROBLEMAS
# ============================================================================

def debug_csv_generation(batch_id):
    """
    Función de debugging para inspeccionar problemas en la generación de CSV
    Uso: Llamar desde Django shell o comando de management
    """
    try:
        batch = ProcessingBatch.objects.get(id=batch_id)
        print(f"=== DEBUG BATCH {batch_id} ===")
        print(f"Documento maestro: {batch.master_document.original_filename}")
        print(f"Total documentos: {batch.total_documents}")
        print(f"Completados: {batch.completed_documents}")
        
        for child_doc in batch.master_document.child_documents.filter(status='completed'):
            print(f"\n--- Paciente {child_doc.patient_section_number} ---")
            print(f"ID: {child_doc.id}")
            print(f"Status: {child_doc.status}")
            
            if child_doc.extracted_data:
                # Generar CSV individual
                extractor = MedicalClaimExtractor()
                csv_content = extractor.generate_excel_format_csv(child_doc.extracted_data)
                
                # Analizar estructura
                lines = csv_content.strip().split('\n')
                print(f"Líneas CSV: {len(lines)}")
                
                if lines:
                    header = lines[0].split(',')
                    print(f"Columnas header: {len(header)}")
                    print(f"Header: {header[:5]}...")  # Primeras 5 columnas
                    
                    if len(lines) > 1:
                        first_row = lines[1].split(',')
                        print(f"Columnas primera fila: {len(first_row)}")
                        print(f"Primera fila: {first_row[:5]}...")
                        
                        # Validar estructura
                        is_valid = validate_csv_structure(csv_content)
                        print(f"CSV válido: {is_valid}")
                
                # Información financiera
                financial = child_doc.extracted_data.get('financial_summary', {})
                procedures = child_doc.extracted_data.get('procedures', [])
                print(f"Procedimientos: {len(procedures)}")
                print(f"Total reclamado: {financial.get('total_reclamado', 0)}")
            else:
                print("Sin datos extraídos")
        
        print("\n=== FIN DEBUG ===")
        
    except Exception as e:
        print(f"Error en debug: {e}")
        import traceback
        traceback.print_exc()



def _generate_empty_csv(glosa):
    """Genera CSV vacío con headers correctos"""
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    headers = [
        'NOMBRE PACIENTE', '# ID', 'FACTURA', 'FECHA FACTURA', 'VALOR TOTAL GLOSA',
        'CÓDIGO ITEM', 'DETALLE DE GLOSA', 'VALOR ITEM', 'VALOR ACEPTADO', 
        'VALOR NO ACEPTADO', 'RESPUESTA IPS', 'CLASIFICACIÓN GLOSA', 
        'FECHA RECIBIDO GLOSA', 'DIAS GLOSA', 'FECHA RADICADO RESPUESTA', 
        'DIAS RESPUESTA', 'CÓDIGO RADICACIÓN', 'FUNCIONARIO', 'Entidad',
        'DESCRIPCIÓN PROCEDIMIENTO'
    ]
    writer.writerow(headers)
    writer.writerow([''] * len(headers))
    
    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{glosa.original_filename}_empty.csv"'
    return response

# API Views
@login_required
def api_glosa_status(request, glosa_id):
    """API endpoint para obtener estado de una glosa"""
    try:
        glosa = GlosaDocument.objects.get(id=glosa_id, user=request.user)
        
        data = {
            'status': glosa.status,
            'original_filename': glosa.original_filename,
            'created_at': glosa.created_at.isoformat(),
            'updated_at': glosa.updated_at.isoformat(),
            'has_extracted_data': bool(glosa.extracted_data),
            'error_message': glosa.error_message,
            'is_master_document': glosa.is_master_document,
            'patient_section_number': glosa.patient_section_number,
        }
        
        # Información de batch si es documento maestro
        if glosa.is_master_document:
            batch = getattr(glosa, 'processing_batch', None)
            if batch:
                data['batch_info'] = {
                    'batch_id': str(batch.id),
                    'total_documents': batch.total_documents,
                    'completed_documents': batch.completed_documents,
                    'failed_documents': batch.failed_documents,
                    'batch_status': batch.batch_status,
                    'progress_percentage': batch.progress_percentage,
                }
        
        # Información extraída si está disponible
        if glosa.extracted_data:
            patient_info = glosa.extracted_data.get('patient_info', {})
            financial = glosa.extracted_data.get('financial_summary', {})
            
            data.update({
                'patient_name': patient_info.get('nombre', ''),
                'total_amount': financial.get('total_reclamado', 0),
                'total_procedures': len(glosa.extracted_data.get('procedures', [])),
            })
        
        return JsonResponse(data)
        
    except GlosaDocument.DoesNotExist:
        return JsonResponse({'error': 'Glosa no encontrada'}, status=404)