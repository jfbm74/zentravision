from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid

class GlosaDocument(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('processing', 'Procesando'),
        ('completed', 'Completado'),
        ('error', 'Error'),
    ]
    
    STRATEGY_CHOICES = [
        ('hybrid', 'Híbrida'),
        ('ai_only', 'Solo IA'),
        ('ocr_only', 'Solo OCR'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='glosas')
    original_file = models.FileField(upload_to='uploads/glosas/%Y/%m/')
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES, default='hybrid')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    extracted_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    
    # NUEVOS CAMPOS PARA MANEJO DE PDFs MÚLTIPLES
    parent_document = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='child_documents'
    )
    is_master_document = models.BooleanField(default=False)
    patient_section_number = models.PositiveIntegerField(null=True, blank=True)
    total_sections = models.PositiveIntegerField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at', 'patient_section_number']
    
    def __str__(self):
        if self.is_master_document:
            return f"Glosa Múltiple {self.original_filename}"
        elif self.parent_document:
            return f"Glosa {self.original_filename} - Paciente {self.patient_section_number}"
        return f"Glosa {self.original_filename}"
    
    @property
    def liquidacion_numero(self):
        if self.extracted_data:
            # Nuevo formato
            if 'policy_info' in self.extracted_data:
                return self.extracted_data['policy_info'].get('numero_liquidacion', 'N/A')
            # Formato anterior (retrocompatibilidad)
            elif 'header' in self.extracted_data:
                return self.extracted_data['header'].get('liquidacion_numero', 'N/A')
        return 'N/A'
    
    @property
    def valor_reclamacion(self):
        if self.extracted_data:
            # Nuevo formato
            if 'financial_summary' in self.extracted_data:
                return self.extracted_data['financial_summary'].get('total_reclamado', 0)
            # Formato anterior (retrocompatibilidad)
            elif 'totales' in self.extracted_data:
                return self.extracted_data['totales'].get('valor_reclamacion', 0)
        return 0
    
    @property
    def is_multi_patient_document(self):
        """Verifica si es un documento con múltiples pacientes"""
        return self.is_master_document and self.child_documents.exists()
    
    @property
    def get_all_related_documents(self):
        """Obtiene todos los documentos relacionados (padre + hijos)"""
        if self.is_master_document:
            return [self] + list(self.child_documents.all())
        elif self.parent_document:
            return [self.parent_document] + list(self.parent_document.child_documents.all())
        return [self]
    
    @property
    def get_processing_batch(self):
        """Obtiene el batch de procesamiento si existe"""
        if self.is_master_document:
            return getattr(self, 'processing_batch', None)
        elif self.parent_document:
            return getattr(self.parent_document, 'processing_batch', None)
        return None
    
    def get_child_status_summary(self):
        """Obtiene resumen de estados de documentos hijos"""
        if not self.is_master_document:
            return None
        
        children = self.child_documents.all()
        if not children:
            return None
        
        return {
            'total': children.count(),
            'completed': children.filter(status='completed').count(),
            'processing': children.filter(status='processing').count(),
            'error': children.filter(status='error').count(),
            'pending': children.filter(status='pending').count(),
        }

class ProcessingBatch(models.Model):
    """Modelo para manejar lotes de procesamiento de PDFs múltiples"""
    
    BATCH_STATUS_CHOICES = [
        ('splitting', 'Dividiendo PDF'),
        ('processing', 'Procesando'),
        ('completed', 'Completado'),
        ('error', 'Error'),
        ('partial_error', 'Completado con errores'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    master_document = models.OneToOneField(
        GlosaDocument, 
        on_delete=models.CASCADE,
        related_name='processing_batch'
    )
    total_documents = models.PositiveIntegerField()
    completed_documents = models.PositiveIntegerField(default=0)
    failed_documents = models.PositiveIntegerField(default=0)
    batch_status = models.CharField(
        max_length=20,
        choices=BATCH_STATUS_CHOICES,
        default='splitting'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Batch {self.master_document.original_filename} ({self.completed_documents}/{self.total_documents})"
    
    @property
    def progress_percentage(self):
        """Calcula el porcentaje de progreso del batch"""
        if self.total_documents == 0:
            return 0
        return round((self.completed_documents / self.total_documents) * 100, 1)
    
    @property
    def is_complete(self):
        """Verifica si el batch está completamente procesado"""
        return self.batch_status in ['completed', 'partial_error']
    
    @property
    def has_errors(self):
        """Verifica si hay errores en el batch"""
        return self.failed_documents > 0 or self.batch_status == 'error'
    
    def update_progress(self):
        """Actualiza el progreso del batch basado en los documentos hijos"""
        master = self.master_document
        children = master.child_documents.all()
        
        self.total_documents = children.count()
        self.completed_documents = children.filter(status='completed').count()
        self.failed_documents = children.filter(status='error').count()
        
        # Actualizar estado del batch
        if self.completed_documents + self.failed_documents >= self.total_documents:
            if self.failed_documents == 0:
                self.batch_status = 'completed'
            elif self.completed_documents > 0:
                self.batch_status = 'partial_error'
            else:
                self.batch_status = 'error'
            
            if not self.completed_at:
                self.completed_at = timezone.now()
        elif self.completed_documents > 0 or self.failed_documents > 0:
            self.batch_status = 'processing'
        
        self.save()
        
        # Actualizar estado del documento maestro
        if self.batch_status == 'completed':
            master.status = 'completed'
        elif self.batch_status == 'partial_error':
            master.status = 'completed'  # Completado con errores
        elif self.batch_status == 'error':
            master.status = 'error'
        
        master.save()

class ProcessingLog(models.Model):
    glosa = models.ForeignKey(GlosaDocument, on_delete=models.CASCADE, related_name='logs')
    timestamp = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10, choices=[
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
    ])
    message = models.TextField()
    
    class Meta:
        ordering = ['-timestamp']