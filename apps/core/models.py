from django.db import models
from django.contrib.auth.models import User
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
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Glosa {self.original_filename}"
    
    @property
    def liquidacion_numero(self):
        if self.extracted_data and 'header' in self.extracted_data:
            return self.extracted_data['header'].get('liquidacion_numero', 'N/A')
        return 'N/A'
    
    @property
    def valor_reclamacion(self):
        if self.extracted_data and 'totales' in self.extracted_data:
            return self.extracted_data['totales'].get('valor_reclamacion', 0)
        return 0

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
