# FIDASIM Controller Service Docker Image
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir \
    flask==2.3.2 \
    redis==4.5.5 \
    kubernetes==26.1.0 \
    numpy==1.24.3 \
    scipy==1.10.1

# Copy controller application
COPY fidasim-controller.py /app/controller.py

# Create non-root user
RUN useradd -m -u 1000 fidasim && \
    chown -R fidasim:fidasim /app

USER fidasim

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/available-resources')" || exit 1

# Run the controller
CMD ["python", "controller.py"]