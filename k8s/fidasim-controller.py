#!/usr/bin/env python3
"""
FIDASIM Kubernetes Job Controller
==================================
Optimally schedules FIDASIM runs based on scaling curves and available resources
"""

import os
import json
import math
import numpy as np
from typing import List, Dict, Tuple
from dataclasses import dataclass
from kubernetes import client, config
from kubernetes.client import V1Job, V1JobSpec, V1PodTemplateSpec
from kubernetes.client import V1PodSpec, V1Container, V1ResourceRequirements
from kubernetes.client import V1ObjectMeta, V1Volume, V1VolumeMount
from kubernetes.client import V1PersistentVolumeClaimVolumeSource
import redis
from flask import Flask, request, jsonify
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@dataclass
class ScalingCurve:
    """Multi-core scaling performance curve"""
    cores: List[int]
    speedup: List[float]  # Relative to single core
    efficiency: List[float]  # Speedup / cores
    
    def __init__(self, curve_data: Dict):
        """Initialize from curve data dict with format:
        {
            "cores": [1, 2, 4, 8, 16, 32, 64],
            "speedup": [1.0, 1.9, 3.6, 6.8, 12.5, 21.0, 32.0],
            "efficiency": [1.0, 0.95, 0.90, 0.85, 0.78, 0.66, 0.50]
        }
        """
        self.cores = curve_data["cores"]
        self.speedup = curve_data["speedup"]
        self.efficiency = curve_data.get("efficiency", 
                                       [s/c for s, c in zip(self.speedup, self.cores)])
    
    def interpolate_speedup(self, n_cores: int) -> float:
        """Interpolate speedup for given number of cores"""
        return np.interp(n_cores, self.cores, self.speedup)
    
    def interpolate_efficiency(self, n_cores: int) -> float:
        """Interpolate efficiency for given number of cores"""
        return np.interp(n_cores, self.cores, self.efficiency)


class FIDASIMScheduler:
    """Optimally schedules FIDASIM jobs on Kubernetes"""
    
    def __init__(self, scaling_curve: ScalingCurve, max_nodes: int = 10, 
                 cores_per_node: int = 64, memory_per_node: int = 256):
        self.scaling_curve = scaling_curve
        self.max_nodes = max_nodes
        self.cores_per_node = cores_per_node
        self.memory_per_node = memory_per_node
        
        # Initialize Kubernetes client
        try:
            config.load_incluster_config()  # For running inside cluster
        except:
            config.load_kube_config()  # For local development
        
        self.batch_api = client.BatchV1Api()
        self.core_api = client.CoreV1Api()
        
        # Redis for job queue
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'redis-service'),
            port=6379,
            decode_responses=True
        )
    
    def get_available_resources(self) -> Tuple[int, int]:
        """Query cluster for available CPU cores and memory (GB)"""
        nodes = self.core_api.list_node()
        
        total_cpu = 0
        total_memory = 0
        available_cpu = 0
        available_memory = 0
        
        for node in nodes.items:
            # Get capacity
            capacity = node.status.capacity
            total_cpu += int(capacity['cpu'])
            total_memory += int(capacity['memory'].replace('Ki', '')) // (1024 * 1024)
            
            # Get available (allocatable - used)
            allocatable = node.status.allocatable
            alloc_cpu = int(allocatable['cpu'])
            alloc_memory = int(allocatable['memory'].replace('Ki', '')) // (1024 * 1024)
            
            # Get current usage from metrics
            # Note: This requires metrics-server to be installed
            try:
                metrics = self.core_api.list_pod_for_all_namespaces()
                node_pods = [p for p in metrics.items if p.spec.node_name == node.metadata.name]
                
                used_cpu = sum(self._get_pod_cpu_request(pod) for pod in node_pods)
                used_memory = sum(self._get_pod_memory_request(pod) for pod in node_pods)
                
                available_cpu += max(0, alloc_cpu - used_cpu)
                available_memory += max(0, alloc_memory - used_memory)
            except:
                # If metrics not available, use conservative estimate
                available_cpu += int(alloc_cpu * 0.7)
                available_memory += int(alloc_memory * 0.7)
        
        return available_cpu, available_memory
    
    def _get_pod_cpu_request(self, pod) -> int:
        """Extract CPU request from pod spec"""
        cpu = 0
        for container in pod.spec.containers:
            if container.resources and container.resources.requests:
                cpu_str = container.resources.requests.get('cpu', '0')
                if cpu_str.endswith('m'):
                    cpu += int(cpu_str[:-1]) / 1000
                else:
                    cpu += int(cpu_str)
        return int(cpu)
    
    def _get_pod_memory_request(self, pod) -> int:
        """Extract memory request from pod spec in GB"""
        memory = 0
        for container in pod.spec.containers:
            if container.resources and container.resources.requests:
                mem_str = container.resources.requests.get('memory', '0')
                if mem_str.endswith('Gi'):
                    memory += int(mem_str[:-2])
                elif mem_str.endswith('Mi'):
                    memory += int(mem_str[:-2]) / 1024
        return int(memory)
    
    def calculate_optimal_distribution(self, n_runs: int, 
                                      run_complexity: List[float] = None) -> Dict:
        """
        Calculate optimal distribution of runs across workers
        
        Args:
            n_runs: Number of FIDASIM runs to execute
            run_complexity: Relative complexity of each run (default: all equal)
        
        Returns:
            Distribution plan with worker configurations
        """
        if run_complexity is None:
            run_complexity = [1.0] * n_runs
        
        available_cpu, available_memory = self.get_available_resources()
        
        logger.info(f"Available resources: {available_cpu} CPUs, {available_memory}GB RAM")
        logger.info(f"Scheduling {n_runs} runs")
        
        # Calculate optimal worker configurations
        plans = []
        
        # Try different worker configurations
        for n_workers in range(1, min(n_runs + 1, available_cpu + 1)):
            for cores_per_worker in self.scaling_curve.cores:
                if cores_per_worker * n_workers > available_cpu:
                    continue
                
                # Calculate memory per worker (assuming linear scaling)
                memory_per_worker = min(
                    available_memory // n_workers,
                    cores_per_worker * 4  # 4GB per core as baseline
                )
                
                # Calculate completion time
                runs_per_worker = math.ceil(n_runs / n_workers)
                speedup = self.scaling_curve.interpolate_speedup(cores_per_worker)
                efficiency = self.scaling_curve.interpolate_efficiency(cores_per_worker)
                
                # Base time unit (relative)
                base_time = sum(run_complexity) / n_runs
                
                # Time per run with speedup
                time_per_run = base_time / speedup
                
                # Total wall time (accounting for load imbalance)
                total_time = runs_per_worker * time_per_run
                
                # Penalize inefficient configurations
                cost = total_time / efficiency
                
                plans.append({
                    'n_workers': n_workers,
                    'cores_per_worker': cores_per_worker,
                    'memory_per_worker': memory_per_worker,
                    'runs_per_worker': runs_per_worker,
                    'speedup': speedup,
                    'efficiency': efficiency,
                    'total_time': total_time,
                    'cost': cost,
                    'total_cores': n_workers * cores_per_worker
                })
        
        # Sort by total time (minimize wall clock time)
        plans.sort(key=lambda x: x['total_time'])
        
        optimal_plan = plans[0]
        
        # Add run distribution to plan
        optimal_plan['run_distribution'] = self._distribute_runs(
            n_runs, optimal_plan['n_workers'], run_complexity
        )
        
        logger.info(f"Optimal plan: {optimal_plan['n_workers']} workers, "
                   f"{optimal_plan['cores_per_worker']} cores each, "
                   f"estimated time: {optimal_plan['total_time']:.2f} units")
        
        return optimal_plan
    
    def _distribute_runs(self, n_runs: int, n_workers: int, 
                        complexity: List[float]) -> List[List[int]]:
        """Distribute runs across workers to balance load"""
        # Sort runs by complexity (descending) for better load balancing
        run_indices = sorted(range(n_runs), key=lambda i: complexity[i], reverse=True)
        
        # Initialize worker queues
        worker_queues = [[] for _ in range(n_workers)]
        worker_loads = [0.0] * n_workers
        
        # Assign runs to workers (greedy load balancing)
        for run_idx in run_indices:
            # Find worker with minimum load
            min_load_worker = worker_loads.index(min(worker_loads))
            worker_queues[min_load_worker].append(run_idx)
            worker_loads[min_load_worker] += complexity[run_idx]
        
        return worker_queues
    
    def create_worker_job(self, job_name: str, worker_id: int, 
                         cores: int, memory: int, run_indices: List[int]) -> V1Job:
        """Create Kubernetes Job for FIDASIM worker"""
        
        # Container specification
        container = V1Container(
            name=f"fidasim-worker-{worker_id}",
            image="fidasim/compute:latest",
            command=["python", "/app/worker.py"],
            env=[
                {"name": "WORKER_ID", "value": str(worker_id)},
                {"name": "RUN_INDICES", "value": json.dumps(run_indices)},
                {"name": "OMP_NUM_THREADS", "value": str(cores)},
                {"name": "REDIS_HOST", "value": "redis-service"}
            ],
            resources=V1ResourceRequirements(
                requests={
                    "cpu": str(cores),
                    "memory": f"{memory}Gi"
                },
                limits={
                    "cpu": str(cores),
                    "memory": f"{memory}Gi"
                }
            ),
            volume_mounts=[
                V1VolumeMount(name="input-data", mount_path="/inputs"),
                V1VolumeMount(name="output-data", mount_path="/outputs")
            ]
        )
        
        # Pod specification
        pod_spec = V1PodSpec(
            containers=[container],
            restart_policy="Never",
            volumes=[
                V1Volume(
                    name="input-data",
                    persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(
                        claim_name="fidasim-input-pvc"
                    )
                ),
                V1Volume(
                    name="output-data",
                    persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(
                        claim_name="fidasim-output-pvc"
                    )
                )
            ]
        )
        
        # Job specification
        job = V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=V1ObjectMeta(
                name=f"{job_name}-worker-{worker_id}",
                labels={
                    "app": "fidasim",
                    "job": job_name,
                    "worker": str(worker_id)
                }
            ),
            spec=V1JobSpec(
                template=V1PodTemplateSpec(
                    metadata=V1ObjectMeta(
                        labels={
                            "app": "fidasim",
                            "job": job_name,
                            "worker": str(worker_id)
                        }
                    ),
                    spec=pod_spec
                ),
                backoff_limit=2,
                ttl_seconds_after_finished=3600  # Clean up after 1 hour
            )
        )
        
        return job
    
    def submit_batch_job(self, job_request: Dict) -> Dict:
        """Submit batch of FIDASIM runs with optimal scheduling"""
        
        job_name = job_request.get('name', f"fidasim-batch-{os.urandom(4).hex()}")
        n_runs = job_request['n_runs']
        run_configs = job_request.get('run_configs', [])
        run_complexity = job_request.get('complexity', [1.0] * n_runs)
        
        # Store run configurations in Redis
        for i, config in enumerate(run_configs):
            self.redis_client.hset(f"job:{job_name}:run:{i}", mapping=config)
        
        # Calculate optimal distribution
        plan = self.calculate_optimal_distribution(n_runs, run_complexity)
        
        # Create and submit worker jobs
        submitted_jobs = []
        for worker_id, run_indices in enumerate(plan['run_distribution']):
            if not run_indices:
                continue
            
            job = self.create_worker_job(
                job_name=job_name,
                worker_id=worker_id,
                cores=plan['cores_per_worker'],
                memory=plan['memory_per_worker'],
                run_indices=run_indices
            )
            
            # Submit to Kubernetes
            response = self.batch_api.create_namespaced_job(
                namespace="fidasim",
                body=job
            )
            
            submitted_jobs.append({
                'worker_id': worker_id,
                'job_name': response.metadata.name,
                'run_indices': run_indices,
                'cores': plan['cores_per_worker'],
                'memory': plan['memory_per_worker']
            })
        
        # Store job metadata in Redis
        self.redis_client.hset(f"job:{job_name}", mapping={
            'status': 'running',
            'n_runs': n_runs,
            'n_workers': plan['n_workers'],
            'plan': json.dumps(plan),
            'workers': json.dumps(submitted_jobs)
        })
        
        return {
            'job_name': job_name,
            'status': 'submitted',
            'plan': plan,
            'workers': submitted_jobs
        }
    
    def get_job_status(self, job_name: str) -> Dict:
        """Get status of batch job"""
        
        # Get job metadata from Redis
        job_data = self.redis_client.hgetall(f"job:{job_name}")
        if not job_data:
            return {'error': 'Job not found'}
        
        workers = json.loads(job_data.get('workers', '[]'))
        
        # Query Kubernetes for worker status
        worker_statuses = []
        for worker in workers:
            try:
                job = self.batch_api.read_namespaced_job(
                    name=worker['job_name'],
                    namespace="fidasim"
                )
                
                status = {
                    'worker_id': worker['worker_id'],
                    'succeeded': job.status.succeeded or 0,
                    'failed': job.status.failed or 0,
                    'active': job.status.active or 0
                }
                
                # Get completed runs from Redis
                completed_runs = []
                for run_idx in worker['run_indices']:
                    if self.redis_client.exists(f"job:{job_name}:run:{run_idx}:complete"):
                        completed_runs.append(run_idx)
                
                status['completed_runs'] = completed_runs
                status['progress'] = len(completed_runs) / len(worker['run_indices'])
                
                worker_statuses.append(status)
            except:
                worker_statuses.append({
                    'worker_id': worker['worker_id'],
                    'status': 'unknown'
                })
        
        # Calculate overall progress
        total_runs = int(job_data['n_runs'])
        completed_runs = sum(len(w.get('completed_runs', [])) for w in worker_statuses)
        
        return {
            'job_name': job_name,
            'status': job_data['status'],
            'progress': completed_runs / total_runs if total_runs > 0 else 0,
            'completed_runs': completed_runs,
            'total_runs': total_runs,
            'workers': worker_statuses,
            'plan': json.loads(job_data.get('plan', '{}'))
        }


# Flask API endpoints
scheduler = None

@app.route('/api/scaling-curve', methods=['POST'])
def set_scaling_curve():
    """Set the multi-core scaling curve"""
    global scheduler
    
    curve_data = request.json
    scaling_curve = ScalingCurve(curve_data)
    
    scheduler = FIDASIMScheduler(
        scaling_curve=scaling_curve,
        max_nodes=request.json.get('max_nodes', 10),
        cores_per_node=request.json.get('cores_per_node', 64),
        memory_per_node=request.json.get('memory_per_node', 256)
    )
    
    return jsonify({'status': 'success', 'message': 'Scaling curve updated'})


@app.route('/api/submit-batch', methods=['POST'])
def submit_batch():
    """Submit batch of FIDASIM runs"""
    if scheduler is None:
        return jsonify({'error': 'Scheduler not initialized. Set scaling curve first.'}), 400
    
    job_request = request.json
    result = scheduler.submit_batch_job(job_request)
    
    return jsonify(result)


@app.route('/api/job-status/<job_name>', methods=['GET'])
def get_job_status(job_name):
    """Get status of batch job"""
    if scheduler is None:
        return jsonify({'error': 'Scheduler not initialized'}), 400
    
    status = scheduler.get_job_status(job_name)
    return jsonify(status)


@app.route('/api/available-resources', methods=['GET'])
def get_available_resources():
    """Get available cluster resources"""
    if scheduler is None:
        return jsonify({'error': 'Scheduler not initialized'}), 400
    
    cpu, memory = scheduler.get_available_resources()
    return jsonify({
        'available_cpu': cpu,
        'available_memory_gb': memory
    })


if __name__ == '__main__':
    # Default scaling curve if none provided
    default_curve = {
        "cores": [1, 2, 4, 8, 16, 32, 64],
        "speedup": [1.0, 1.9, 3.6, 6.8, 12.5, 21.0, 32.0],
    }
    
    scaling_curve = ScalingCurve(default_curve)
    scheduler = FIDASIMScheduler(scaling_curve)
    
    app.run(host='0.0.0.0', port=5000, debug=False)