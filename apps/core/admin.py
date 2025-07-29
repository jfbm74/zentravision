# apps/core/admin.py - VERSIÓN FINAL LIMPIA Y FUNCIONAL

from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Q
from django.utils import timezone
import json
import re
from .models import GlosaDocument, ProcessingLog, ProcessingBatch

# ============================================================================
# CONFIGURACIÓN GENERAL DEL ADMIN
# ============================================================================

admin.site.site_header = "🏥 Zentravision - Administración de Glosas SOAT"
admin.site.site_title = "Zentravision Admin"
admin.site.index_title = "Panel de Administración - Extractor de Glosas Médicas"

# ============================================================================
# INLINES PARA RELACIONES
# ============================================================================

class ProcessingLogInline(admin.TabularInline):
    model = ProcessingLog
    extra = 0
    readonly_fields = ['timestamp', 'level', 'message_short']
    fields = ['timestamp', 'level', 'message_short']
    can_delete = False
    max_num = 5
    
    def message_short(self, obj):
        if obj and obj.message:
            if len(obj.message) > 60:
                return obj.message[:60] + '...'
            return obj.message
        return "Sin mensaje"
    message_short.short_description = 'Mensaje'
    
    def has_add_permission(self, request, obj=None):
        return False

class ChildDocumentsInline(admin.TabularInline):
    model = GlosaDocument
    fk_name = 'parent_document'
    extra = 0
    readonly_fields = ['patient_section_number', 'original_filename', 'status', 'created_at']
    fields = ['patient_section_number', 'original_filename', 'status', 'created_at']
    can_delete = False
    max_num = 10
    verbose_name = "Documento Hijo"
    verbose_name_plural = "Documentos Hijos (Pacientes)"
    
    def has_add_permission(self, request, obj=None):
        return False

# ============================================================================
# ADMIN PARA GLOSA DOCUMENT (MEJORADO PERO ESTABLE)
# ============================================================================

class GlosaDocumentAdmin(admin.ModelAdmin):
    list_display = [
        'filename_display',
        'user_display', 
        'status_display', 
        'strategy_display',
        'document_type_display',
        'patient_display',
        'procedures_display',
        'financial_display',
        'size_display',
        'time_display',
        'created_at'
    ]
    
    list_filter = [
        'status', 
        'strategy', 
        'is_master_document',
        'created_at', 
        ('user', admin.RelatedOnlyFieldListFilter)
    ]
    
    search_fields = [
        'original_filename', 
        'user__username', 
        'user__email'
    ]
    
    readonly_fields = [
        'id', 
        'created_at', 
        'updated_at', 
        'extracted_data_display'
    ]
    
    fieldsets = (
        ('📄 Información Básica', {
            'fields': ('id', 'user', 'original_filename', 'original_file', 'status', 'strategy')
        }),
        ('⏰ Fechas', {
            'fields': ('created_at', 'updated_at')
        }),
        ('👥 Estructura', {
            'fields': ('is_master_document', 'parent_document', 'patient_section_number', 'total_sections'),
            'classes': ('collapse',)
        }),
        ('📋 Datos Extraídos', {
            'fields': ('extracted_data_display',),
            'classes': ('collapse',)
        }),
        ('❌ Errores', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        })
    )
    
    inlines = [ChildDocumentsInline, ProcessingLogInline]
    
    # Métodos de display simplificados y seguros
    def filename_display(self, obj):
        try:
            if len(obj.original_filename) > 25:
                return obj.original_filename[:22] + '...'
            return obj.original_filename
        except:
            return "Sin nombre"
    filename_display.short_description = 'Archivo'
    
    def user_display(self, obj):
        try:
            return format_html(
                '<strong>{}</strong><br><small>{}</small>',
                obj.user.username,
                obj.user.email or 'Sin email'
            )
        except:
            return "Sin usuario"
    user_display.short_description = 'Usuario'
    
    def status_display(self, obj):
        try:
            colors = {
                'pending': '#ffc107',
                'processing': '#17a2b8',
                'completed': '#28a745',
                'error': '#dc3545'
            }
            icons = {
                'pending': '⏳',
                'processing': '⚙️',
                'completed': '✅',
                'error': '❌'
            }
            color = colors.get(obj.status, '#6c757d')
            icon = icons.get(obj.status, '❓')
            return format_html(
                '<span style="background-color: {}; color: white; padding: 3px 6px; border-radius: 3px; font-size: 11px;">{} {}</span>',
                color, icon, obj.get_status_display()
            )
        except:
            return obj.status
    status_display.short_description = 'Estado'
    
    def strategy_display(self, obj):
        try:
            colors = {'hybrid': '#6f42c1', 'ai_only': '#fd7e14', 'ocr_only': '#20c997'}
            icons = {'hybrid': '🔄', 'ai_only': '🤖', 'ocr_only': '📝'}
            color = colors.get(obj.strategy, '#6c757d')
            icon = icons.get(obj.strategy, '❓')
            return format_html(
                '<span style="background-color: {}; color: white; padding: 2px 5px; border-radius: 3px; font-size: 10px;">{} {}</span>',
                color, icon, obj.get_strategy_display()
            )
        except:
            return obj.strategy
    strategy_display.short_description = 'Estrategia'
    
    def document_type_display(self, obj):
        try:
            if obj.is_master_document:
                count = obj.child_documents.count() if hasattr(obj, 'child_documents') else 0
                return format_html(
                    '<span style="background-color: #6610f2; color: white; padding: 2px 5px; border-radius: 3px; font-size: 10px;">📚 Múltiple ({})</span>',
                    count
                )
            elif obj.parent_document:
                return format_html(
                    '<span style="background-color: #0d6efd; color: white; padding: 2px 5px; border-radius: 3px; font-size: 10px;">👤 Paciente {}</span>',
                    obj.patient_section_number or '?'
                )
            else:
                return format_html(
                    '<span style="background-color: #198754; color: white; padding: 2px 5px; border-radius: 3px; font-size: 10px;">📄 Individual</span>'
                )
        except:
            return "Desconocido"
    document_type_display.short_description = 'Tipo'
    
    def patient_display(self, obj):
        try:
            if not obj.extracted_data:
                return format_html('<em style="color: #6c757d;">Sin datos</em>')
            
            # Buscar información del paciente en diferentes claves posibles
            patient = None
            policy_info = None
            
            if 'patient_info' in obj.extracted_data:
                patient = obj.extracted_data['patient_info']
            elif 'paciente' in obj.extracted_data:
                patient = obj.extracted_data['paciente']
            elif 'header' in obj.extracted_data:
                patient = obj.extracted_data['header']
            
            # Buscar información de póliza para datos adicionales
            if 'policy_info' in obj.extracted_data:
                policy_info = obj.extracted_data['policy_info']
            elif 'poliza' in obj.extracted_data:
                policy_info = obj.extracted_data['poliza']
            
            if not patient or not isinstance(patient, dict):
                # DEBUG: Mostrar qué claves están disponibles
                available_keys = list(obj.extracted_data.keys())
                keys_str = ', '.join(available_keys[:3])
                if len(available_keys) > 3:
                    keys_str += '...'
                return format_html(
                    '<em style="color: #17a2b8;" title="Claves: {}">Debug: {}</em>', 
                    ', '.join(available_keys), 
                    keys_str
                )
            
            # Extraer información del paciente
            name = (patient.get('nombre') or 
                   patient.get('name') or 
                   patient.get('paciente_nombre') or 'N/A')
            
            doc = (patient.get('documento') or 
                  patient.get('cedula') or 
                  patient.get('identificacion') or 
                  patient.get('id') or 'N/A')
            
            doc_type = (patient.get('tipo_documento') or 
                       patient.get('tipo_id') or 
                       patient.get('tipo') or 'CC')
            
            # Extraer información adicional de póliza si está disponible
            poliza_num = 'N/A'
            liquidacion_num = 'N/A'
            fecha_siniestro = 'N/A'
            
            if policy_info and isinstance(policy_info, dict):
                poliza_num = (policy_info.get('poliza') or 
                             policy_info.get('numero_poliza') or 'N/A')
                liquidacion_num = (policy_info.get('numero_liquidacion') or 
                                  policy_info.get('liquidacion') or 'N/A')
                fecha_siniestro = (policy_info.get('fecha_siniestro') or 
                                  policy_info.get('fecha_accidente') or 'N/A')
            
            # Formatear nombre si es muy largo
            display_name = name
            if isinstance(name, str) and len(name) > 20:
                display_name = name[:17] + '...'
            
            # Formatear números largos
            if len(str(liquidacion_num)) > 15:
                liquidacion_display = str(liquidacion_num)[:12] + '...'
            else:
                liquidacion_display = liquidacion_num
            
            # Crear HTML con información completa
            html = f'''
            <div class="patient-info" style="font-size: 11px;">
                <strong style="color: #2c3e50;">{display_name}</strong><br>
                <span style="color: #7f8c8d;">{doc_type}: {doc}</span><br>
                <small style="color: #27ae60;">
                    <strong>Póliza:</strong> {poliza_num}<br>
                    <strong>Liq:</strong> {liquidacion_display}
            '''
            
            # Agregar fecha si está disponible
            if fecha_siniestro != 'N/A':
                html += f'<br><strong>Fecha:</strong> {fecha_siniestro}'
            
            html += '</small></div>'
            
            return format_html(html)
            
        except Exception as e:
            # Log del error para debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error en patient_display para glosa {obj.id}: {str(e)}")
            
            return format_html(
                '<em style="color: #dc3545;" title="{}">Error: {}</em>', 
                str(e)[:50]
            )
    patient_display.short_description = '👤 Información del Paciente'
    
    def procedures_display(self, obj):
        """
        Muestra información de procedimientos con manejo de errores mejorado
        """
        try:
            if not obj.extracted_data:
                return format_html('<span class="text-muted">Sin datos</span>')
            
            # DEBUG: Mostrar las claves disponibles
            available_keys = list(obj.extracted_data.keys())
            procedures = None
            
            # Buscar procedimientos en diferentes claves posibles
            if 'procedures' in obj.extracted_data:
                procedures = obj.extracted_data['procedures']
            elif 'procedimientos' in obj.extracted_data:
                procedures = obj.extracted_data['procedimientos']
            
            if not procedures or not isinstance(procedures, list):
                # DEBUG: Mostrar información de debugging
                keys_str = ', '.join(available_keys[:3])
                if len(available_keys) > 3:
                    keys_str += '...'
                return format_html(
                    '<span class="text-warning">Debug: Claves disponibles: {}</span>',
                    keys_str
                )
            
            total = len(procedures)
            if total == 0:
                return format_html('<span class="text-muted">0 procedimientos</span>')
            
            objetados = 0
            total_objetado = 0
            
            for proc in procedures:
                if isinstance(proc, dict):
                    valor_objetado = proc.get('valor_objetado', 0)
                    
                    # Limpiar y convertir valor objetado
                    if isinstance(valor_objetado, str):
                        try:
                            valor_objetado = float(valor_objetado.replace(',', '').replace('$', '').replace(' ', ''))
                        except ValueError:
                            valor_objetado = 0
                    elif not isinstance(valor_objetado, (int, float)):
                        valor_objetado = 0
                    
                    if valor_objetado > 0:
                        objetados += 1
                        total_objetado += valor_objetado
            
            # Formatear respuesta con colores
            if objetados == 0:
                return format_html(
                    '<span class="badge bg-success">{} procedimientos</span>',
                    total
                )
            else:
                porcentaje_objetado = (objetados / total) * 100
                color_class = 'bg-danger' if porcentaje_objetado > 50 else 'bg-warning'
                
                # Formatear números antes de pasarlos a format_html
                porcentaje_str = f"{porcentaje_objetado:.1f}"
                valor_str = f"{total_objetado:,.0f}"
                
                return format_html(
                    '<span class="badge {}">{} total ({} objetados - {}%)</span><br>'
                    '<small class="text-muted">Valor objetado: ${}</small>',
                    color_class,
                    total,
                    objetados,
                    porcentaje_str,
                    valor_str
                )
        
        except Exception as e:
            # Log del error para debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error en procedures_display para glosa {obj.id}: {str(e)}")
            
            return format_html(
                '<span class="text-danger">Error: {}</span>',
                str(e)[:50]
            )

    procedures_display.short_description = '📋 Procedimientos'
    procedures_display.admin_order_field = 'extracted_data'
    
    def financial_display(self, obj):
        """
        Muestra resumen financiero con manejo de errores mejorado
        """
        try:
            if not obj.extracted_data:
                return format_html('<em style="color: #6c757d;">Sin datos</em>')
            
            # DEBUG: Mostrar las claves disponibles
            available_keys = list(obj.extracted_data.keys())
            financial = None
            
            # Buscar información financiera en diferentes claves posibles
            if 'financial_summary' in obj.extracted_data:
                financial = obj.extracted_data['financial_summary']
            elif 'totales' in obj.extracted_data:
                financial = obj.extracted_data['totales']
            
            if not financial:
                # DEBUG: Mostrar información de debugging
                keys_str = ', '.join(available_keys[:3])
                if len(available_keys) > 3:
                    keys_str += '...'
                return format_html(
                    '<em style="color: #17a2b8;" title="Claves: {}">Debug: {}</em>',
                    ', '.join(available_keys), 
                    keys_str
                )
            
            # Obtener valores con múltiples nombres posibles
            total = (financial.get('total_reclamado', 0) or
                    financial.get('valor_reclamacion', 0) or 0)
            objetado = (financial.get('total_objetado', 0) or
                       financial.get('valor_objetado', 0) or 0)
            
            # Limpiar y convertir valores si son strings
            if isinstance(total, str):
                try:
                    total = float(total.replace(',', '').replace('$', '').replace(' ', ''))
                except ValueError:
                    total = 0
            
            if isinstance(objetado, str):
                try:
                    objetado = float(objetado.replace(',', '').replace('$', '').replace(' ', ''))
                except ValueError:
                    objetado = 0
            
            # Asegurar que son números
            total = float(total) if total else 0
            objetado = float(objetado) if objetado else 0
            
            # Calcular valores derivados
            aceptado = total - objetado
            porcentaje_objetado = (objetado / total * 100) if total > 0 else 0
            
            # Determinar color basado en el porcentaje objetado
            if porcentaje_objetado == 0:
                color_class = 'success'
                icon = '✅'
            elif porcentaje_objetado <= 25:
                color_class = 'info'
                icon = '🟢'
            elif porcentaje_objetado <= 50:
                color_class = 'warning'
                icon = '🟡'
            else:
                color_class = 'danger'
                icon = '🔴'
            
            # Formatear números antes de pasarlos a format_html
            porcentaje_str = f"{porcentaje_objetado:.1f}"
            total_str = f"{total:,.0f}"
            objetado_str = f"{objetado:,.0f}"
            aceptado_str = f"{aceptado:,.0f}"
            
            # Formatear respuesta con información completa
            return format_html(
                '<div class="financial-summary">'
                '<span class="badge bg-{} mb-1">{} {}% objetado</span><br>'
                '<small class="text-muted">'
                '<strong>Total:</strong> ${}<br>'
                '<strong>Objetado:</strong> ${}<br>'
                '<strong>Aceptado:</strong> ${}'
                '</small>'
                '</div>',
                color_class,
                icon,
                porcentaje_str,
                total_str,
                objetado_str,
                aceptado_str
            )
        
        except Exception as e:
            # Log del error para debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error en financial_display para glosa {obj.id}: {str(e)}")
            
            return format_html(
                '<span class="text-danger">Error financiero: {}</span>',
                str(e)[:30]
            )

    financial_display.short_description = '💰 Resumen Financiero'
    financial_display.admin_order_field = 'extracted_data'
    
    def size_display(self, obj):
        try:
            if obj.file_size:
                if obj.file_size < 1024 * 1024:
                    return "{:.0f} KB".format(obj.file_size / 1024)
                else:
                    return "{:.1f} MB".format(obj.file_size / (1024 * 1024))
            return "N/A"
        except:
            return "Error"
    size_display.short_description = 'Tamaño'
    
    def time_display(self, obj):
        try:
            if obj.status == 'completed' and obj.created_at and obj.updated_at:
                delta = obj.updated_at - obj.created_at
                total_seconds = int(delta.total_seconds())
                if total_seconds < 60:
                    return "{}s".format(total_seconds)
                else:
                    minutes = total_seconds // 60
                    seconds = total_seconds % 60
                    return "{}m {}s".format(minutes, seconds)
            return "-"
        except:
            return "Error"
    time_display.short_description = 'Tiempo'
    
    def extracted_data_display(self, obj):
        try:
            if obj.extracted_data:
                formatted_json = json.dumps(obj.extracted_data, indent=2, ensure_ascii=False)
                return format_html(
                    '<pre style="background-color: #f8f9fa; padding: 10px; border-radius: 5px; font-size: 11px; max-height: 400px; overflow-y: auto;">{}</pre>',
                    formatted_json
                )
            return "Sin datos extraídos"
        except:
            return "Error mostrando datos"
    extracted_data_display.short_description = 'Datos Extraídos'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'parent_document')
    
    def has_add_permission(self, request):
        return False

# ============================================================================
# ADMIN PARA PROCESSING BATCH
# ============================================================================

class ProcessingBatchAdmin(admin.ModelAdmin):
    list_display = [
        'batch_id_display',
        'master_filename_display',  
        'user_display',
        'status_display',
        'progress_display',
        'documents_display',
        'created_at'
    ]
    
    list_filter = [
        'batch_status',
        'created_at',
        ('master_document__user', admin.RelatedOnlyFieldListFilter)
    ]
    
    search_fields = [
        'master_document__original_filename',
        'master_document__user__username'
    ]
    
    readonly_fields = [
        'id', 'master_document', 'created_at', 'completed_at'
    ]
    
    def batch_id_display(self, obj):
        try:
            return str(obj.id)[:8] + '...'
        except:
            return "Error"
    batch_id_display.short_description = 'Batch ID'
    
    def master_filename_display(self, obj):
        try:
            filename = obj.master_document.original_filename
            if len(filename) > 30:
                return filename[:27] + '...'
            return filename
        except:
            return "Sin archivo"
    master_filename_display.short_description = 'Archivo Maestro'
    
    def user_display(self, obj):
        try:
            return obj.master_document.user.username
        except:
            return "Sin usuario"
    user_display.short_description = 'Usuario'
    
    def status_display(self, obj):
        try:
            colors = {
                'splitting': '#17a2b8',
                'processing': '#ffc107', 
                'completed': '#28a745',
                'error': '#dc3545',
                'partial_error': '#fd7e14'
            }
            color = colors.get(obj.batch_status, '#6c757d')
            return format_html(
                '<span style="background-color: {}; color: white; padding: 3px 6px; border-radius: 3px; font-size: 11px;">{}</span>',
                color, obj.get_batch_status_display()
            )
        except:
            return obj.batch_status
    status_display.short_description = 'Estado'
    
    def progress_display(self, obj):
        try:
            percentage = obj.progress_percentage
            return "{}%".format(percentage)
        except:
            return "0%"
    progress_display.short_description = 'Progreso'
    
    def documents_display(self, obj):
        try:
            return format_html(
                'Total: {}<br>✅ {} ❌ {}',
                obj.total_documents,
                obj.completed_documents, 
                obj.failed_documents
            )
        except:
            return "Error"
    documents_display.short_description = 'Documentos'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('master_document', 'master_document__user')
    
    def has_add_permission(self, request):
        return False

# ============================================================================
# ADMIN PARA PROCESSING LOG
# ============================================================================

class ProcessingLogAdmin(admin.ModelAdmin):
    list_display = [
        'timestamp_display',
        'glosa_filename_display',
        'user_display',
        'level_display', 
        'message_preview_display'
    ]
    
    list_filter = [
        'level',
        'timestamp',
        ('glosa__user', admin.RelatedOnlyFieldListFilter)
    ]
    
    search_fields = [
        'message',
        'glosa__original_filename',
        'glosa__user__username'
    ]
    
    readonly_fields = ['glosa', 'timestamp', 'level', 'message']
    
    def timestamp_display(self, obj):
        try:
            return obj.timestamp.strftime('%d/%m/%Y %H:%M')
        except:
            return "Sin fecha"
    timestamp_display.short_description = 'Fecha/Hora'
    
    def glosa_filename_display(self, obj):
        try:
            filename = obj.glosa.original_filename
            if len(filename) > 20:
                return filename[:17] + '...'
            return filename
        except:
            return "Sin archivo"
    glosa_filename_display.short_description = 'Archivo'
    
    def user_display(self, obj):
        try:
            return obj.glosa.user.username
        except:
            return "Sin usuario"
    user_display.short_description = 'Usuario'
    
    def level_display(self, obj):
        try:
            colors = {'INFO': '#17a2b8', 'WARNING': '#ffc107', 'ERROR': '#dc3545'}
            color = colors.get(obj.level, '#6c757d')
            return format_html(
                '<span style="background-color: {}; color: white; padding: 2px 5px; border-radius: 3px; font-size: 10px;">{}</span>',
                color, obj.level
            )
        except:
            return obj.level
    level_display.short_description = 'Nivel'
    
    def message_preview_display(self, obj):
        try:
            message = obj.message
            if len(message) > 100:
                return message[:100] + '...'
            return message
        except:
            return "Sin mensaje"
    message_preview_display.short_description = 'Mensaje'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('glosa', 'glosa__user')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False

# ============================================================================
# REGISTRO DE MODELOS
# ============================================================================

# Registrar modelos
admin.site.register(GlosaDocument, GlosaDocumentAdmin)
admin.site.register(ProcessingBatch, ProcessingBatchAdmin)
admin.site.register(ProcessingLog, ProcessingLogAdmin)

# Confirmación de registro
print("✅ Admin registrado exitosamente:")
print("   - GlosaDocument con funcionalidades avanzadas")
print("   - ProcessingBatch con monitoreo de progreso")
print("   - ProcessingLog con análisis de mensajes")