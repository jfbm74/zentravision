# apps/core/management/commands/check_database.py - ACTUALIZADO

from django.core.management.base import BaseCommand
from apps.core.models import GlosaDocument, ProcessingBatch
import json

class Command(BaseCommand):
    help = 'Verifica datos en la base de datos incluyendo batches'

    def add_arguments(self, parser):
        parser.add_argument('--glosa-id', type=str, help='ID específico de glosa')
        parser.add_argument('--batch-id', type=str, help='ID específico de batch')
        parser.add_argument('--latest', action='store_true', help='Mostrar último documento')
        parser.add_argument('--batches', action='store_true', help='Mostrar información de batches')

    def handle(self, *args, **options):
        if options.get('glosa_id'):
            try:
                glosa = GlosaDocument.objects.get(id=options['glosa_id'])
                self.show_glosa_details(glosa)
            except GlosaDocument.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Glosa {options['glosa_id']} no encontrada"))
                
        elif options.get('batch_id'):
            try:
                batch = ProcessingBatch.objects.get(id=options['batch_id'])
                self.show_batch_details(batch)
            except ProcessingBatch.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Batch {options['batch_id']} no encontrado"))
                
        elif options.get('latest'):
            glosa = GlosaDocument.objects.order_by('-created_at').first()
            if glosa:
                self.show_glosa_details(glosa)
            else:
                self.stdout.write("No hay glosas en la base de datos")
                
        elif options.get('batches'):
            self.show_batches_summary()
                
        else:
            # Mostrar todas las glosas
            self.show_all_glosas()

    def show_all_glosas(self):
        # Documentos únicos (padres o sin padre)
        unique_glosas = GlosaDocument.objects.filter(parent_document__isnull=True).order_by('-created_at')
        
        self.stdout.write(f"=== GLOSAS EN BASE DE DATOS ({unique_glosas.count()}) ===")
        
        for glosa in unique_glosas:
            self.stdout.write(f"\n{glosa.id}")
            self.stdout.write(f"  Archivo: {glosa.original_filename}")
            self.stdout.write(f"  Estado: {glosa.status}")
            self.stdout.write(f"  Tipo: {'Múltiple' if glosa.is_master_document else 'Individual'}")
            self.stdout.write(f"  Creado: {glosa.created_at}")
            
            if glosa.is_master_document:
                children = glosa.child_documents.all()
                self.stdout.write(f"  Pacientes: {children.count()}")
                batch = getattr(glosa, 'processing_batch', None)
                if batch:
                    self.stdout.write(f"  Batch: {batch.batch_status} ({batch.completed_documents}/{batch.total_documents})")
            else:
                if glosa.extracted_data:
                    procedures = glosa.extracted_data.get('procedures', [])
                    self.stdout.write(f"  Procedimientos: {len(procedures)}")

    def show_glosa_details(self, glosa):
        self.stdout.write(f"=== DETALLE DE GLOSA {glosa.id} ===")
        self.stdout.write(f"Archivo: {glosa.original_filename}")
        self.stdout.write(f"Estado: {glosa.status}")
        self.stdout.write(f"Estrategia: {glosa.strategy}")
        self.stdout.write(f"Tamaño: {glosa.file_size} bytes")
        self.stdout.write(f"Creado: {glosa.created_at}")
        self.stdout.write(f"Actualizado: {glosa.updated_at}")
        
        # Información de tipo de documento
        if glosa.is_master_document:
            self.stdout.write(f"Tipo: Documento Múltiple")
            self.stdout.write(f"Total secciones: {glosa.total_sections}")
            
            # Información del batch
            batch = getattr(glosa, 'processing_batch', None)
            if batch:
                self.stdout.write(f"\n=== INFORMACIÓN DEL BATCH ===")
                self.stdout.write(f"ID Batch: {batch.id}")
                self.stdout.write(f"Estado: {batch.batch_status}")
                self.stdout.write(f"Documentos totales: {batch.total_documents}")
                self.stdout.write(f"Completados: {batch.completed_documents}")
                self.stdout.write(f"Fallidos: {batch.failed_documents}")
                self.stdout.write(f"Progreso: {batch.progress_percentage}%")
            
            # Información de documentos hijos
            children = glosa.child_documents.all()
            if children:
                self.stdout.write(f"\n=== DOCUMENTOS HIJOS ({children.count()}) ===")
                for child in children:
                    self.stdout.write(f"\nPaciente {child.patient_section_number}:")
                    self.stdout.write(f"  ID: {child.id}")
                    self.stdout.write(f"  Estado: {child.status}")
                    if child.extracted_data and 'patient_info' in child.extracted_data:
                        patient_name = child.extracted_data['patient_info'].get('nombre', 'N/A')
                        self.stdout.write(f"  Paciente: {patient_name}")
                    if child.error_message:
                        self.stdout.write(f"  Error: {child.error_message}")
        
        elif glosa.parent_document:
            self.stdout.write(f"Tipo: Documento Hijo (Paciente {glosa.patient_section_number})")
            self.stdout.write(f"Documento padre: {glosa.parent_document.id}")
            self.stdout.write(f"Sección: {glosa.patient_section_number}/{glosa.total_sections}")
        else:
            self.stdout.write(f"Tipo: Documento Individual")
        
        if glosa.error_message:
            self.stdout.write(f"Error: {glosa.error_message}")
        
        # Datos extraídos (solo para documentos no maestros)
        if glosa.extracted_data and not glosa.is_master_document:
            self.stdout.write("\n=== DATOS EXTRAÍDOS ===")
            
            # Información del paciente
            patient = glosa.extracted_data.get('patient_info', {})
            if patient:
                self.stdout.write(f"Paciente: {patient.get('nombre', 'N/A')}")
                self.stdout.write(f"Documento: {patient.get('tipo_documento', '')} {patient.get('documento', 'N/A')}")
            
            # Información financiera
            financial = glosa.extracted_data.get('financial_summary', {})
            if financial:
                self.stdout.write(f"Total reclamado: ${financial.get('total_reclamado', 0):,.0f}")
                self.stdout.write(f"Total objetado: ${financial.get('total_objetado', 0):,.0f}")
                self.stdout.write(f"Total aceptado: ${financial.get('total_aceptado', 0):,.0f}")
            
            # Procedimientos
            procedures = glosa.extracted_data.get('procedures', [])
            self.stdout.write(f"\n=== PROCEDIMIENTOS ({len(procedures)}) ===")
            
            if procedures:
                for i, proc in enumerate(procedures[:5]):  # Mostrar solo primeros 5
                    self.stdout.write(f"\n{i+1}. Código: {proc.get('codigo', 'N/A')}")
                    self.stdout.write(f"   Descripción: {proc.get('descripcion', 'N/A')}")
                    self.stdout.write(f"   Cantidad: {proc.get('cantidad', 0)}")
                    self.stdout.write(f"   Valor total: ${proc.get('valor_total', 0):,.0f}")
                    self.stdout.write(f"   Valor objetado: ${proc.get('valor_objetado', 0):,.0f}")
                    self.stdout.write(f"   Estado: {proc.get('estado', 'N/A')}")
                    
                    if proc.get('observacion'):
                        obs = proc['observacion'][:100] + '...' if len(proc['observacion']) > 100 else proc['observacion']
                        self.stdout.write(f"   Observación: {obs}")
                
                if len(procedures) > 5:
                    self.stdout.write(f"\n... y {len(procedures) - 5} procedimientos más")
            else:
                self.stdout.write("No hay procedimientos extraídos")

    def show_batch_details(self, batch):
        self.stdout.write(f"=== DETALLE DEL BATCH {batch.id} ===")
        self.stdout.write(f"Documento maestro: {batch.master_document.original_filename}")
        self.stdout.write(f"Estado: {batch.batch_status}")
        self.stdout.write(f"Total documentos: {batch.total_documents}")
        self.stdout.write(f"Completados: {batch.completed_documents}")
        self.stdout.write(f"Fallidos: {batch.failed_documents}")
        self.stdout.write(f"Progreso: {batch.progress_percentage}%")
        self.stdout.write(f"Creado: {batch.created_at}")
        if batch.completed_at:
            self.stdout.write(f"Completado: {batch.completed_at}")
        if batch.error_message:
            self.stdout.write(f"Error: {batch.error_message}")
        
        # Listar documentos hijos
        children = batch.master_document.child_documents.all().order_by('patient_section_number')
        self.stdout.write(f"\n=== DOCUMENTOS DEL BATCH ({children.count()}) ===")
        
        for child in children:
            self.stdout.write(f"\nPaciente {child.patient_section_number}:")
            self.stdout.write(f"  ID: {child.id}")
            self.stdout.write(f"  Estado: {child.status}")
            self.stdout.write(f"  Archivo: {child.original_filename}")
            
            if child.extracted_data and 'patient_info' in child.extracted_data:
                patient_info = child.extracted_data['patient_info']
                self.stdout.write(f"  Nombre: {patient_info.get('nombre', 'N/A')}")
                
            if child.extracted_data and 'financial_summary' in child.extracted_data:
                financial = child.extracted_data['financial_summary']
                self.stdout.write(f"  Valor reclamado: ${financial.get('total_reclamado', 0):,.0f}")
            
            if child.error_message:
                self.stdout.write(f"  Error: {child.error_message}")

    def show_batches_summary(self):
        batches = ProcessingBatch.objects.all().order_by('-created_at')
        
        self.stdout.write(f"=== BATCHES DE PROCESAMIENTO ({batches.count()}) ===")
        
        for batch in batches:
            self.stdout.write(f"\n{batch.id}")
            self.stdout.write(f"  Documento: {batch.master_document.original_filename}")
            self.stdout.write(f"  Estado: {batch.batch_status}")
            self.stdout.write(f"  Progreso: {batch.completed_documents}/{batch.total_documents} ({batch.progress_percentage}%)")
            self.stdout.write(f"  Creado: {batch.created_at}")
            if batch.completed_at:
                processing_time = (batch.completed_at - batch.created_at).total_seconds()
                self.stdout.write(f"  Tiempo total: {processing_time:.1f} segundos")

