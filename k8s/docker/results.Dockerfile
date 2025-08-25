# FIDASIM Results Viewer Service Docker Image
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libhdf5-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir \
    flask==2.3.2 \
    flask-cors==4.0.0 \
    h5py==3.9.0 \
    numpy==1.24.3 \
    matplotlib==3.7.1 \
    plotly==5.14.1

# Copy results viewer application
COPY results/results_viewer.py /app/results_viewer.py

# Create directories
RUN mkdir -p /outputs /tmp/cache

# Create non-root user
RUN useradd -m -u 1000 fidasim && \
    chown -R fidasim:fidasim /app /outputs /tmp/cache

USER fidasim

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost/health')" || exit 1

# Run the results viewer
CMD ["python", "results_viewer.py"]