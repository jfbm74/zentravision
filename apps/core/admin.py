from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
import json
from .models import GlosaDocument, ProcessingLog

class ProcessingLogInline(admin.TabularInline):
    model = ProcessingLog
    extra = 0
    readonly_fields = ['timestamp', 'level', 'message']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False

@admin.register(GlosaDocument)
class GlosaDocumentAdmin(admin.ModelAdmin):
    list_display = [
        'original_filename', 
        'user', 
        'status_badge', 
        'strategy', 
        'liquidacion_numero',
        'valor_reclamacion_formatted',
        'file_size_formatted',
        'created_at',
        'updated_at'
    ]
    
    list_filter = [
        'status', 
        'strategy', 
        'created_at', 
        'updated_at'
    ]
    
    search_fields = [
        'original_filename', 
        'user__username', 
        'user__email',
        'extracted_data'
    ]
    
    readonly_fields = [
        'id', 
        'created_at', 
        'updated_at', 
        'file_size_formatted',
        'liquidacion_numero',
        'valor_reclamacion_formatted',
        'extracted_data_formatted'
    ]
    
    fieldsets = (
        ('Información del Documento', {
            'fields': ('id', 'user', 'original_filename', 'original_file', 'file_size_formatted')
        }),
        ('Estado del Procesamiento', {
            'fields': ('status', 'strategy', 'created_at', 'updated_at')
        }),
        ('Datos Extraídos', {
            'fields': ('liquidacion_numero', 'valor_reclamacion_formatted', 'extracted_data_formatted'),
            'classes': ('collapse',)
        }),
        ('Errores', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        })
    )
    
    inlines = [ProcessingLogInline]
    
    def status_badge(self, obj):
        """Muestra el estado con colores"""
        colors = {
            'pending': '#ffc107',      # Amarillo
            'processing': '#17a2b8',   # Azul
            'completed': '#28a745',    # Verde
            'error': '#dc3545'         # Rojo
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 12px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Estado'
    
    def file_size_formatted(self, obj):
        """Formatea el tamaño del archivo en formato legible"""
        if obj.file_size:
            if obj.file_size < 1024:
                return f"{obj.file_size} B"
            elif obj.file_size < 1024 * 1024:
                return f"{obj.file_size / 1024:.1f} KB"
            else:
                return f"{obj.file_size / (1024 * 1024):.1f} MB"
        return "N/A"
    file_size_formatted.short_description = 'Tamaño del Archivo'
    
    def valor_reclamacion_formatted(self, obj):
        """Formatea el valor de reclamación como moneda"""
        valor = obj.valor_reclamacion
        if valor:
            return f"${valor:,.2f}"
        return "N/A"
    valor_reclamacion_formatted.short_description = 'Valor Reclamación'
    
    def extracted_data_formatted(self, obj):
        """Muestra los datos extraídos en formato JSON legible"""
        if obj.extracted_data:
            try:
                formatted_json = json.dumps(obj.extracted_data, indent=2, ensure_ascii=False)
                return format_html(
                    '<pre style="background-color: #f8f9fa; padding: 10px; border-radius: 5px; font-size: 12px; max-height: 400px; overflow-y: auto;">{}</pre>',
                    formatted_json
                )
            except:
                return str(obj.extracted_data)
        return "Sin datos extraídos"
    extracted_data_formatted.short_description = 'Datos Extraídos'
    
    def get_queryset(self, request):
        """Optimiza las consultas incluyendo el usuario"""
        return super().get_queryset(request).select_related('user')
    
    def has_add_permission(self, request):
        """Desactiva la opción de agregar desde admin (solo a través de la app)"""
        return False

@admin.register(ProcessingLog)
class ProcessingLogAdmin(admin.ModelAdmin):
    list_display = [
        'glosa_filename',
        'level_badge',
        'message_preview',
        'timestamp'
    ]
    
    list_filter = [
        'level',
        'timestamp',
        'glosa__status'
    ]
    
    search_fields = [
        'message',
        'glosa__original_filename',
        'glosa__user__username'
    ]
    
    readonly_fields = [
        'glosa',
        'timestamp',
        'level',
        'message'
    ]
    
    def glosa_filename(self, obj):
        """Muestra el nombre del archivo de la glosa"""
        return obj.glosa.original_filename
    glosa_filename.short_description = 'Archivo'
    
    def level_badge(self, obj):
        """Muestra el nivel de log con colores"""
        colors = {
            'INFO': '#17a2b8',      # Azul
            'WARNING': '#ffc107',   # Amarillo
            'ERROR': '#dc3545'      # Rojo
        }
        color = colors.get(obj.level, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.level
        )
    level_badge.short_description = 'Nivel'
    
    def message_preview(self, obj):
        """Muestra una vista previa del mensaje"""
        if len(obj.message) > 100:
            return obj.message[:100] + '...'
        return obj.message
    message_preview.short_description = 'Mensaje'
    
    def get_queryset(self, request):
        """Optimiza las consultas incluyendo la glosa y el usuario"""
        return super().get_queryset(request).select_related('glosa', 'glosa__user')
    
    def has_add_permission(self, request):
        """Desactiva la opción de agregar desde admin"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Desactiva la opción de modificar desde admin"""
        return False

# Personalización del sitio admin
admin.site.site_header = "Administración de Glosas"
admin.site.site_title = "Glosas Admin"
admin.site.index_title = "Panel de Administración"