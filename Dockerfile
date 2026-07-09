FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory
WORKDIR /app

# Install system dependencies
# faiss-cpu requires libgomp1. We also install curl for healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt first to leverage Docker caching
COPY backend/requirements.txt /app/backend/

# Install Python dependencies
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend and frontend source directories
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

# Set working directory to the backend folder
WORKDIR /app/backend

# Expose the FastAPI port
EXPOSE 8000

# Start the application using Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
