# apps/core/management/commands/check_database.py

from django.core.management.base import BaseCommand
from apps.core.models import GlosaDocument
import json

class Command(BaseCommand):
    help = 'Verifica datos en la base de datos'

    def add_arguments(self, parser):
        parser.add_argument('--glosa-id', type=str, help='ID específico de glosa')
        parser.add_argument('--latest', action='store_true', help='Mostrar último documento')

    def handle(self, *args, **options):
        if options.get('glosa_id'):
            try:
                glosa = GlosaDocument.objects.get(id=options['glosa_id'])
                self.show_glosa_details(glosa)
            except GlosaDocument.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Glosa {options['glosa_id']} no encontrada"))
                
        elif options.get('latest'):
            glosa = GlosaDocument.objects.order_by('-created_at').first()
            if glosa:
                self.show_glosa_details(glosa)
            else:
                self.stdout.write("No hay glosas en la base de datos")
                
        else:
            # Mostrar todas las glosas
            glosas = GlosaDocument.objects.all().order_by('-created_at')
            self.stdout.write(f"=== GLOSAS EN BASE DE DATOS ({glosas.count()}) ===")
            
            for glosa in glosas:
                self.stdout.write(f"\n{glosa.id}")
                self.stdout.write(f"  Archivo: {glosa.original_filename}")
                self.stdout.write(f"  Estado: {glosa.status}")
                self.stdout.write(f"  Creado: {glosa.created_at}")
                
                if glosa.extracted_data:
                    procedures = glosa.extracted_data.get('procedures', [])
                    self.stdout.write(f"  Procedimientos: {len(procedures)}")
                    
                    if procedures:
                        self.stdout.write("  Códigos:")
                        for proc in procedures[:5]:  # Mostrar primeros 5
                            self.stdout.write(f"    - {proc.get('codigo', 'N/A')}: {proc.get('descripcion', 'N/A')[:50]}...")

    def show_glosa_details(self, glosa):
        self.stdout.write(f"=== DETALLE DE GLOSA {glosa.id} ===")
        self.stdout.write(f"Archivo: {glosa.original_filename}")
        self.stdout.write(f"Estado: {glosa.status}")
        self.stdout.write(f"Estrategia: {glosa.strategy}")
        self.stdout.write(f"Tamaño: {glosa.file_size} bytes")
        self.stdout.write(f"Creado: {glosa.created_at}")
        self.stdout.write(f"Actualizado: {glosa.updated_at}")
        
        if glosa.error_message:
            self.stdout.write(f"Error: {glosa.error_message}")
        
        if glosa.extracted_data:
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
                for i, proc in enumerate(procedures):
                    self.stdout.write(f"\n{i+1}. Código: {proc.get('codigo', 'N/A')}")
                    self.stdout.write(f"   Descripción: {proc.get('descripcion', 'N/A')}")
                    self.stdout.write(f"   Cantidad: {proc.get('cantidad', 0)}")
                    self.stdout.write(f"   Valor total: ${proc.get('valor_total', 0):,.0f}")
                    self.stdout.write(f"   Valor pagado: ${proc.get('valor_pagado', 0):,.0f}")
                    self.stdout.write(f"   Valor objetado: ${proc.get('valor_objetado', 0):,.0f}")
                    self.stdout.write(f"   Estado: {proc.get('estado', 'N/A')}")
                    
                    if proc.get('observacion'):
                        obs = proc['observacion'][:100] + '...' if len(proc['observacion']) > 100 else proc['observacion']
                        self.stdout.write(f"   Observación: {obs}")
            else:
                self.stdout.write("No hay procedimientos extraídos")
            
            # Mostrar JSON completo si es necesario
            self.stdout.write(f"\n=== JSON COMPLETO ===")
            print(json.dumps(glosa.extracted_data, indent=2, ensure_ascii=False))
        else:
            self.stdout.write("No hay datos extraídos")