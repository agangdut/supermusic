FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt backend/requirements.txt backend/pyproject.toml ./
COPY backend/requirements.txt* ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY data/ ./data/

# Create necessary directories
RUN mkdir -p data/raw data/interim data/processed data/samples static

# Environment variables
ENV PYTHONPATH=/app
ENV SM_DATA_DIR=/app/data
ENV SM_RAW_DIR=/app/data/raw
ENV SM_INTERIM_DIR=/app/data/interim
ENV SM_PROCESSED_DIR=/app/data/processed

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

