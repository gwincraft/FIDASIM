# FIDASIM Kubernetes Deployment

This directory contains the Kubernetes deployment configuration for running FIDASIM with dynamic scaling and optimal worker distribution.

## Overview

The system consists of several components:

1. **Controller Service** - Manages job scheduling and optimal worker distribution
2. **Frontend Service** - Web interface for job submission and monitoring
3. **Results Viewer** - Service for viewing and analyzing FIDASIM outputs
4. **Compute Workers** - Dynamically spawned pods that execute FIDASIM runs
5. **Redis** - Job queue and status tracking

## Architecture

The system uses a sophisticated scheduling algorithm that:
- Takes multi-core scaling curves as input
- Calculates optimal distribution of runs across workers
- Minimizes total wall time based on available resources
- Supports heterogeneous run complexities

## Quick Start

### Prerequisites

- Kubernetes cluster (1.20+)
- kubectl configured
- Docker registry access
- NFS or similar shared storage for PVCs

### Building Docker Images

```bash
cd docker
./build-images.sh
```

To push to a registry:
```bash
DOCKER_REGISTRY=myregistry VERSION=v1.0 PUSH_IMAGES=true ./build-images.sh
```

### Deploying to Kubernetes

1. Update the storage class in `deployment.yaml` to match your cluster:
```yaml
storageClassName: nfs-storage  # Change this to your storage class
```

2. Update the ingress host if using external access:
```yaml
host: fidasim.example.com  # Change to your domain
```

3. Deploy the application:
```bash
kubectl apply -f deployment.yaml
```

4. Check deployment status:
```bash
kubectl get pods -n fidasim
kubectl get svc -n fidasim
```

## Using the Web Interface

Access the web interface at `http://fidasim.example.com` (or via port-forward):

```bash
kubectl port-forward -n fidasim svc/fidasim-frontend-service 8080:80
```

Then open `http://localhost:8080` in your browser.

### Features

1. **Setup Tab** - Configure input files and run parameters
2. **Batch Runs Tab** - Configure parameter scans and batch jobs
3. **Monitor Tab** - Real-time job monitoring and progress tracking
4. **Scaling Tab** - Configure multi-core scaling curves

## Optimal Scheduling Algorithm

The controller uses a sophisticated algorithm to optimize job distribution:

```python
# Example scaling curve configuration
scaling_curve = {
    "cores": [1, 2, 4, 8, 16, 32, 64],
    "speedup": [1.0, 1.9, 3.6, 6.8, 12.5, 21.0, 32.0]
}
```

The algorithm:
1. Queries available cluster resources
2. Tests different worker configurations
3. Calculates expected completion time for each
4. Selects configuration that minimizes wall time
5. Distributes runs using greedy load balancing

## API Endpoints

The controller provides REST API endpoints:

- `POST /api/scaling-curve` - Update scaling curve
- `POST /api/submit-batch` - Submit batch job
- `GET /api/job-status/<job_name>` - Get job status
- `GET /api/available-resources` - Get cluster resources

Example job submission:
```json
{
    "name": "my-fidasim-job",
    "n_runs": 100,
    "run_configs": [...],
    "complexity": [1.0, 1.2, 0.8, ...]  // Relative complexity per run
}
```

## Monitoring

### Using kubectl

```bash
# View all jobs
kubectl get jobs -n fidasim

# View worker pods
kubectl get pods -n fidasim -l app=fidasim

# View logs
kubectl logs -n fidasim <pod-name>

# View job details
kubectl describe job -n fidasim <job-name>
```

### Using the Web Interface

The Monitor tab provides:
- Real-time progress bars
- Worker status
- Individual run completion tracking
- Cluster resource utilization

## Configuration

### Environment Variables

Controller:
- `REDIS_HOST` - Redis service hostname
- `MAX_NODES` - Maximum number of nodes to use
- `CORES_PER_NODE` - Default cores per node

Worker:
- `WORKER_ID` - Unique worker identifier
- `RUN_INDICES` - JSON array of run indices
- `OMP_NUM_THREADS` - OpenMP thread count
- `FIDASIM_DIR` - FIDASIM installation directory

### Persistent Volumes

The deployment uses two PVCs:
- `fidasim-input-pvc` - Input files (100Gi)
- `fidasim-output-pvc` - Output files (500Gi)

Adjust sizes in `deployment.yaml` as needed.

## Scaling

### Horizontal Pod Autoscaling

The frontend automatically scales based on load:
```yaml
minReplicas: 2
maxReplicas: 10
targetCPUUtilization: 70%
```

### Manual Scaling

Scale frontend replicas:
```bash
kubectl scale deployment -n fidasim fidasim-frontend --replicas=5
```

## Troubleshooting

### Pod Issues

```bash
# Check pod status
kubectl describe pod -n fidasim <pod-name>

# Check events
kubectl get events -n fidasim --sort-by='.lastTimestamp'
```

### Storage Issues

```bash
# Check PVC status
kubectl get pvc -n fidasim

# Check PV binding
kubectl describe pvc -n fidasim fidasim-input-pvc
```

### Network Issues

```bash
# Test service connectivity
kubectl run -n fidasim test-pod --image=busybox -it --rm -- /bin/sh
# Inside pod:
wget -O- http://fidasim-controller-service:5000/api/available-resources
```

## Performance Tuning

### Scaling Curve Optimization

1. Run benchmark tests at different core counts
2. Measure actual speedup
3. Update scaling curve via web interface or API
4. System will automatically use new curve for scheduling

### Resource Limits

Adjust in `deployment.yaml`:
```yaml
resources:
  requests:
    cpu: "64"
    memory: "256Gi"
  limits:
    cpu: "64"
    memory: "256Gi"
```

### Redis Performance

For large job queues, consider:
- Increasing Redis memory limits
- Enabling Redis persistence
- Using Redis cluster mode

## Security

### RBAC

The controller uses a ServiceAccount with minimal permissions:
- Create/manage Jobs in fidasim namespace
- Read node information
- Access pods and logs

### Network Policies

Consider adding NetworkPolicies to restrict traffic:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: fidasim-network-policy
  namespace: fidasim
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
```

## Development

### Local Testing

Use Docker Compose for local development:
```bash
docker-compose up
```

### Adding Features

1. Modify source code in respective directories
2. Rebuild Docker images
3. Deploy to development cluster
4. Test thoroughly
5. Deploy to production

## Support

For issues or questions:
1. Check logs: `kubectl logs -n fidasim <pod-name>`
2. Review events: `kubectl get events -n fidasim`
3. Check resource usage: `kubectl top pods -n fidasim`

## License

This Kubernetes deployment configuration is part of the FIDASIM project.