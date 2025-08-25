# FIDASIM Kubernetes Integration Guide

This document explains how to integrate the Kubernetes deployment with your existing FIDASIM installation.

## Prerequisites

Before deploying, you need:

1. **Built FIDASIM binaries** from the main repository
2. **Atomic tables file** (`atomic_tables.h5`)
3. **Python libraries** from `lib/python/fidasim`
4. **Test data files** (optional, for validation)

## Integration Steps

### 1. Build FIDASIM Compute Image

The compute worker Dockerfile needs to be updated with your actual FIDASIM build:

```dockerfile
# In docker/compute.Dockerfile, replace the placeholder section with:

# Copy FIDASIM binaries (adjust paths to match your build)
COPY --from=builder /path/to/fidasim/fidasim ${FIDASIM_DIR}/fidasim
COPY --from=builder /path/to/fidasim/lib ${FIDASIM_DIR}/lib
COPY --from=builder /path/to/fidasim/tables/atomic_tables.h5 ${FIDASIM_DIR}/tables/
```

Or use a multi-stage build:

```dockerfile
# Add this as first stage in compute.Dockerfile
FROM ubuntu:22.04 as fidasim-build

# Copy source code
COPY src /tmp/fidasim/src
COPY lib /tmp/fidasim/lib
COPY tables /tmp/fidasim/tables

# Build FIDASIM
WORKDIR /tmp/fidasim
RUN make

# Then in main stage:
COPY --from=fidasim-build /tmp/fidasim/fidasim ${FIDASIM_DIR}/
COPY --from=fidasim-build /tmp/fidasim/lib ${FIDASIM_DIR}/lib/
COPY --from=fidasim-build /tmp/fidasim/tables ${FIDASIM_DIR}/tables/
```

### 2. Update Worker Script

The `worker/worker.py` script has a complete integration point at line 18-21:

```python
# Already configured to use FIDASIM Python modules
FIDASIM_DIR = os.environ.get('FIDASIM_DIR', '/opt/fidasim')
sys.path.insert(0, os.path.join(FIDASIM_DIR, 'lib/python'))
import fidasim as fs
```

### 3. Configure Storage

Update the PVC storage classes in `deployment.yaml` to match your cluster:

```yaml
storageClassName: nfs-storage  # Change to your storage class
# Common options:
# - standard (for cloud providers)
# - local-path (for k3s/microk8s)
# - nfs-client (for NFS provisioner)
# - ceph-block (for Ceph/Rook)
```

### 4. Set Up Input Data

Mount your FIDASIM input files to the input PVC:

```bash
# Copy input files to the PVC
kubectl cp ./test_data fidasim/input-pod:/inputs/
kubectl cp ./atomic_tables.h5 fidasim/input-pod:/inputs/tables/
```

### 5. Configure Scaling Curves

Based on your FIDASIM performance benchmarks, update the default scaling curve:

```python
# In fidasim-controller.py:499-502
default_curve = {
    "cores": [1, 2, 4, 8, 16, 32, 64],
    "speedup": [1.0, 1.9, 3.6, 6.8, 12.5, 21.0, 32.0],  # Your measured values
}
```

## Testing Integration

### Local Testing with Docker Compose

1. Build images locally:
```bash
cd k8s
docker-compose build
```

2. Run test setup:
```bash
docker-compose up
```

3. Access web interface at `http://localhost:8080`

### Kubernetes Testing

1. Deploy to a test namespace:
```bash
kubectl create namespace fidasim-test
kubectl apply -f deployment.yaml -n fidasim-test
```

2. Run a test job:
```bash
curl -X POST http://controller-service:5000/api/submit-batch \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test-job",
    "n_runs": 4,
    "run_configs": [...]
  }'
```

## Production Considerations

### Security

1. **Never commit secrets** - Use Kubernetes secrets for sensitive data:
```bash
kubectl create secret generic fidasim-secrets \
  --from-literal=api-key=YOUR_KEY \
  -n fidasim
```

2. **Network policies** - Restrict pod-to-pod communication
3. **RBAC** - Limit service account permissions

### Performance

1. **Node affinity** - Pin compute pods to high-performance nodes:
```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: node-type
          operator: In
          values:
          - compute
```

2. **Resource limits** - Set appropriate CPU/memory limits based on your runs

3. **Storage performance** - Use fast storage for output PVC (SSD-backed)

### Monitoring

1. **Prometheus metrics** - Add metrics endpoint to controller
2. **Logging** - Configure centralized logging (ELK/Loki)
3. **Alerts** - Set up alerts for job failures

## Troubleshooting

### FIDASIM Binary Not Found

If worker pods fail with "fidasim: command not found":
1. Check Dockerfile COPY commands
2. Verify binary permissions: `chmod +x ${FIDASIM_DIR}/fidasim`
3. Check PATH environment variable

### Python Module Import Errors

If `import fidasim` fails:
1. Verify Python libraries are copied to `${FIDASIM_DIR}/lib/python`
2. Check PYTHONPATH in Dockerfile
3. Ensure Python version compatibility

### Storage Issues

If input/output files aren't accessible:
1. Check PVC is bound: `kubectl get pvc -n fidasim`
2. Verify mount paths in pod spec
3. Check file permissions in containers

## Support

For integration issues specific to this Kubernetes deployment:
- Check the README.md for general deployment help
- Review worker logs: `kubectl logs -n fidasim <worker-pod>`
- Verify controller status: `kubectl logs -n fidasim deployment/fidasim-controller`

For FIDASIM-specific issues:
- Consult the main FIDASIM documentation
- Check FIDASIM GitHub issues