# ==========================================
# apps/core/forms.py - MODIFICADO PARA ESTRATEGIA POR DEFECTO "SOLO IA"
# ==========================================

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Submit, Div, HTML
from crispy_forms.bootstrap import FormActions
from .models import GlosaDocument

class GlosaUploadForm(forms.ModelForm):
    """Formulario para subir documentos de glosas"""
    
    class Meta:
        model = GlosaDocument
        fields = ['original_file', 'strategy']
        widgets = {
            'original_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf',
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # CAMBIO: Establecer 'ai_only' como valor por defecto
        self.fields['strategy'].initial = 'ai_only'
        
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_enctype = 'multipart/form-data'
        self.helper.layout = Layout(
            HTML('<div class="card">'),
            HTML('<div class="card-header"><h5><i class="fas fa-upload"></i> Subir Glosa Médica</h5></div>'),
            HTML('<div class="card-body">'),
            
            Div(
                Field('original_file', css_class='form-control-lg'),
                HTML('<small class="form-text text-muted">Solo archivos PDF. Máximo 10MB.</small>'),
                css_class='mb-3'
            ),
            
            Div(
                Field('strategy'),
                HTML('<small class="form-text text-muted">Solo IA ofrece la mejor precisión para glosas SOAT.</small>'),
                css_class='mb-3'
            ),
            
            HTML('</div>'),
            HTML('<div class="card-footer">'),
            FormActions(
                Submit('submit', 'Procesar Documento', css_class='btn btn-primary btn-lg'),
            ),
            HTML('</div>'),
            HTML('</div>'),
        )
    
    def clean_original_file(self):
        file = self.cleaned_data.get('original_file')
        
        if file:
            # Validar tipo de archivo
            if not file.name.lower().endswith('.pdf'):
                raise forms.ValidationError('Solo se permiten archivos PDF.')
            
            # Validar tamaño
            if file.size > 10 * 1024 * 1024:  # 10MB
                raise forms.ValidationError('El archivo no puede superar los 10MB.')
        
        return file