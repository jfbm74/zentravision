# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Zentravision is a Django-based web application for automated extraction of Colombian SOAT medical claims data using OCR and AI (OpenAI GPT-4o-mini). It handles both single and multi-patient PDF documents with asynchronous processing via Celery and Redis.

## Common Development Commands

### Running the Application

```bash
# Activate virtual environment
source myenv_py312/bin/activate  # Linux/Mac

# Run Django development server
python manage.py runserver

# Run Celery worker (required for PDF processing)
celery -A zentravision worker --loglevel=info

# Run Celery beat (optional, for scheduled tasks)
celery -A zentravision beat --loglevel=info
```

### Database Operations

```bash
# Create and apply migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Check database status
python manage.py check_database
python manage.py check_database --batches
python manage.py check_database --glosa-id UUID
```

### Testing and Validation

```bash
# Test PDF splitter functionality
python manage.py test_pdf_splitter /path/to/file.pdf
python manage.py test_pdf_splitter /path/to/file.pdf --validate-only

# Test extractor
python manage.py test_extractor /path/to/file.pdf
python manage.py test_extractor /path/to/file.pdf --strategy hybrid
```

### Maintenance

```bash
# Clean old batches
python manage.py cleanup_batches --days 30
python manage.py cleanup_batches --days 30 --dry-run
```

## High-Level Architecture

### Core Components

1. **Django Web Framework (apps/core/)**
   - Models: `GlosaDocument`, `ProcessingBatch`, `ProcessingLog`
   - Views handle document uploads and batch processing
   - Admin interface for data management

2. **Extraction Engine (apps/extractor/)**
   - `medical_claim_extractor_fixed.py`: Hybrid extraction using OCR + OpenAI
   - `pdf_splitter.py`: Automatically splits multi-patient PDFs
   - `tasks.py`: Celery tasks for asynchronous processing

3. **Asynchronous Processing**
   - Celery with Redis broker for background PDF processing
   - Handles large files and batch operations efficiently
   - Progress tracking for multi-document batches

### Data Flow

1. User uploads PDF → `GlosaDocument` created with status='pending'
2. If multi-patient detected → `ProcessingBatch` created, PDF split into sections
3. Celery task processes each section asynchronously
4. Extraction strategies: hybrid (OCR+AI), ai_only, or ocr_only
5. Results stored in `extracted_data` JSONField

### Key Configuration

- Settings: `zentravision/settings.py` (uses environment variables via python-decouple)
- Celery: `zentravision/celery.py` (Redis on localhost:6379)
- Required environment variables:
  - `SECRET_KEY`
  - `DATABASE_URL` 
  - `OPENAI_API_KEY`
  - `REDIS_URL`/`CELERY_BROKER_URL`

### API Endpoints

- `/api/` - Dashboard
- `/api/upload/` - Upload documents
- `/api/glosas/` - List/manage individual documents
- `/api/batches/` - Manage batch processing
- `/download/{id}/json/` - Download extracted data
- `/download/{id}/csv/` - Download procedures in IPS format

### Important Implementation Details

- OCR uses PyMuPDF for text extraction
- OpenAI integration uses GPT-4o-mini model for intelligent analysis
- Supports CUPS medical procedure codes and CIE-10 diagnosis codes
- Handles Colombian SOAT claim format specifically
- Multi-patient PDFs are automatically detected and split
- All file uploads go to `uploads/glosas/%Y/%m/`
- Static files served via WhiteNoise in production