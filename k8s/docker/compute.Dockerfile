# FIDASIM Compute Worker Docker Image
FROM ubuntu:22.04

# Avoid interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gfortran \
    libopenmpi-dev \
    openmpi-bin \
    libhdf5-openmpi-dev \
    libnetcdf-dev \
    libnetcdff-dev \
    liblapack-dev \
    libblas-dev \
    python3 \
    python3-pip \
    python3-dev \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Set FIDASIM directory
ENV FIDASIM_DIR=/opt/fidasim

# Create FIDASIM directory structure
RUN mkdir -p ${FIDASIM_DIR}/lib/python ${FIDASIM_DIR}/tables

# NOTE: In production deployment, uncomment and adjust these lines:
# COPY --from=fidasim-build /opt/fidasim/fidasim ${FIDASIM_DIR}/fidasim
# COPY --from=fidasim-build /opt/fidasim/lib ${FIDASIM_DIR}/lib
# COPY --from=fidasim-build /opt/fidasim/tables/atomic_tables.h5 ${FIDASIM_DIR}/tables/

# For development/testing, create placeholder
RUN echo '#!/bin/bash\necho "FIDASIM placeholder"' > ${FIDASIM_DIR}/fidasim && \
    chmod +x ${FIDASIM_DIR}/fidasim

# Install Python dependencies
RUN pip3 install --no-cache-dir \
    numpy==1.24.3 \
    scipy==1.10.1 \
    h5py==3.9.0 \
    netCDF4==1.6.4 \
    redis==4.5.5 \
    matplotlib==3.7.1

# Copy worker script
COPY worker/worker.py /app/worker.py

# Copy FIDASIM Python libraries (placeholder)
# COPY lib/python ${FIDASIM_DIR}/lib/python

# Create directories
RUN mkdir -p /inputs /outputs /tmp/worker

# Create non-root user
RUN useradd -m -u 1000 fidasim && \
    chown -R fidasim:fidasim /app /inputs /outputs /tmp/worker

# Set Python path
ENV PYTHONPATH=${FIDASIM_DIR}/lib/python:${PYTHONPATH}

USER fidasim
WORKDIR /app

# Default OMP threads
ENV OMP_NUM_THREADS=1

# Health check (simple file creation to verify worker is responsive)
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
    CMD touch /tmp/worker/health || exit 1

# Run the worker
CMD ["python3", "/app/worker.py"]