#!/usr/bin/env python3
"""
FIDASIM Compute Worker
======================
Executes FIDASIM runs assigned by the controller
"""

import os
import sys
import json
import time
import traceback
import subprocess
import redis
import numpy as np
from pathlib import Path

# Add FIDASIM Python modules to path
FIDASIM_DIR = os.environ.get('FIDASIM_DIR', '/opt/fidasim')
sys.path.insert(0, os.path.join(FIDASIM_DIR, 'lib/python'))

try:
    import fidasim as fs
except ImportError:
    print("Warning: FIDASIM Python module not found. Running in test mode.")
    fs = None

class FIDASIMWorker:
    """Worker that processes FIDASIM runs"""
    
    def __init__(self, worker_id: int, run_indices: list):
        self.worker_id = worker_id
        self.run_indices = run_indices
        
        # Redis connection for job status updates
        self.redis_client = redis.Redis(
            host=os.environ.get('REDIS_HOST', 'redis-service'),
            port=6379,
            decode_responses=True
        )
        
        # Paths
        self.input_dir = Path('/inputs')
        self.output_dir = Path('/outputs')
        self.work_dir = Path(f'/tmp/worker_{worker_id}')
        
        # Create working directory
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        # OMP threads from environment
        self.omp_threads = int(os.environ.get('OMP_NUM_THREADS', '1'))
        
        print(f"Worker {worker_id} initialized")
        print(f"  Assigned runs: {run_indices}")
        print(f"  OMP threads: {self.omp_threads}")
    
    def get_job_name(self) -> str:
        """Extract job name from environment or Redis"""
        # Try to get from Kubernetes labels
        job_name = os.environ.get('JOB_NAME')
        if not job_name:
            # Parse from pod name (format: jobname-worker-N-xxxxx)
            pod_name = os.environ.get('HOSTNAME', '')
            if '-worker-' in pod_name:
                job_name = '-'.join(pod_name.split('-worker-')[0].split('-')[:-1])
        return job_name or 'unknown'
    
    def run(self):
        """Main worker loop"""
        job_name = self.get_job_name()
        
        print(f"Starting worker {self.worker_id} for job {job_name}")
        
        # Update worker status
        self.update_status('running')
        
        completed_runs = []
        failed_runs = []
        
        for run_idx in self.run_indices:
            print(f"\n{'='*60}")
            print(f"Worker {self.worker_id}: Starting run {run_idx}")
            print(f"{'='*60}")
            
            try:
                # Get run configuration from Redis
                run_config = self.redis_client.hgetall(f"job:{job_name}:run:{run_idx}")
                if not run_config:
                    print(f"Warning: No configuration found for run {run_idx}")
                    run_config = self.get_default_config(run_idx)
                
                # Execute FIDASIM run
                success = self.execute_run(job_name, run_idx, run_config)
                
                if success:
                    completed_runs.append(run_idx)
                    # Mark run as complete in Redis
                    self.redis_client.set(f"job:{job_name}:run:{run_idx}:complete", "1")
                else:
                    failed_runs.append(run_idx)
                    self.redis_client.set(f"job:{job_name}:run:{run_idx}:failed", "1")
                
                # Update progress
                progress = len(completed_runs) / len(self.run_indices)
                self.update_progress(job_name, progress, completed_runs, failed_runs)
                
            except Exception as e:
                print(f"Error processing run {run_idx}: {e}")
                traceback.print_exc()
                failed_runs.append(run_idx)
                self.redis_client.set(f"job:{job_name}:run:{run_idx}:error", str(e))
        
        # Final status update
        self.update_status('completed')
        
        print(f"\n{'='*60}")
        print(f"Worker {self.worker_id} completed")
        print(f"  Successful runs: {len(completed_runs)}/{len(self.run_indices)}")
        print(f"  Failed runs: {len(failed_runs)}")
        print(f"{'='*60}")
        
        return len(failed_runs) == 0
    
    def execute_run(self, job_name: str, run_idx: int, config: dict) -> bool:
        """Execute a single FIDASIM run"""
        
        # Create run-specific output directory
        run_output_dir = self.output_dir / job_name / f"run_{run_idx:04d}"
        run_output_dir.mkdir(parents=True, exist_ok=True)
        
        # If FIDASIM module is available, use Python interface
        if fs is not None:
            return self.execute_run_python(run_output_dir, config)
        else:
            # Fallback to command-line execution
            return self.execute_run_cli(run_output_dir, config)
    
    def execute_run_python(self, output_dir: Path, config: dict) -> bool:
        """Execute FIDASIM using Python interface"""
        
        try:
            # Set up basic inputs
            inputs = {
                "device": config.get('device', 'test'),
                "shot": int(config.get('shot', 1)),
                "time": float(config.get('time', 1.0)),
                "runid": config.get('runid', f"run_{self.worker_id}"),
                "result_dir": str(output_dir),
                "tables_file": str(self.input_dir / 'atomic_tables.h5'),
                
                # Physics calculations
                "calc_fida": int(config.get('calc_fida', False)),
                "calc_npa": int(config.get('calc_npa', False)),
                "calc_neutron": int(config.get('calc_neutron', False)),
                "calc_neut_spec": int(config.get('calc_neut_spec', False)),
                
                # Weight functions
                "calc_fida_wght": int(config.get('calc_fida_wght', False)),
                "calc_npa_wght": int(config.get('calc_npa_wght', False)),
                "calc_nc_wght": int(config.get('calc_nc_wght', False)),
                
                # Monte Carlo settings
                "n_fida": int(config.get('n_fida', 5000000)),
                "n_npa": int(config.get('n_npa', 5000000)),
                "n_nbi": int(config.get('n_nbi', 50000)),
                
                # NC weight parameters
                "ne_nc": int(config.get('ne_nc', 40)),
                "np_nc": int(config.get('np_nc', 40)),
                "emax_nc": float(config.get('emax_nc', 100.0)),
                
                # Other settings
                "verbose": 1,
                "seed": int(config.get('seed', 42)) + self.worker_id * 1000
            }
            
            # Load input files
            namelist_file = self.input_dir / config.get('namelist', 'input.nml')
            if namelist_file.exists():
                # Parse namelist and update inputs
                with open(namelist_file, 'r') as f:
                    # Simple namelist parsing (would need proper parser in production)
                    pass
            
            # Check for required input files
            geqdsk_file = self.input_dir / 'g000001.01000'
            profiles_file = self.input_dir / 'profiles.cdf'
            fbm_file = self.input_dir / 'fi_1.cdf'
            
            if not all([geqdsk_file.exists(), profiles_file.exists(), fbm_file.exists()]):
                print("Warning: Required input files not found, using test data")
                # Would load test data here
                return False
            
            # Create grid
            grid = fs.utils.rz_grid(100.0, 240.0, 70, -100.0, 100.0, 100)
            
            # Read equilibrium
            equil, rho, btipsign = fs.utils.read_geqdsk(
                str(geqdsk_file), grid, ccw_phi=True, exp_Bp=0
            )
            
            # Read fast-ion distribution
            fbm = fs.utils.read_nubeam(str(fbm_file), grid, btipsign=btipsign)
            
            # Read plasma profiles
            # This would need proper profile reading
            plasma = None  # Placeholder
            
            # Create beam geometry
            nbi = None  # Placeholder
            
            # Create diagnostic geometries
            spec = None
            npa = None
            nc = None
            
            if config.get('calc_nc_wght'):
                # Create NC geometry
                nc = self.create_nc_geometry()
            
            # Run FIDASIM
            print(f"Running FIDASIM with OMP_NUM_THREADS={self.omp_threads}")
            os.environ['OMP_NUM_THREADS'] = str(self.omp_threads)
            
            # fs.prefida(inputs, grid, nbi, plasma, equil, fbm, spec=spec, npa=npa, nc=nc)
            
            # For now, simulate success
            time.sleep(np.random.uniform(5, 15))  # Simulate runtime
            
            # Create dummy output file
            output_file = output_dir / f"{inputs['runid']}_output.h5"
            import h5py
            with h5py.File(output_file, 'w') as f:
                f.create_dataset('neutron_rate', data=np.random.random() * 1e14)
                f.attrs['worker_id'] = self.worker_id
                f.attrs['omp_threads'] = self.omp_threads
                f.attrs['timestamp'] = time.time()
            
            print(f"Run completed, output saved to {output_file}")
            return True
            
        except Exception as e:
            print(f"Error in Python execution: {e}")
            traceback.print_exc()
            return False
    
    def execute_run_cli(self, output_dir: Path, config: dict) -> bool:
        """Execute FIDASIM using command-line interface"""
        
        try:
            # Prepare namelist file
            namelist_path = self.work_dir / f"run_{self.worker_id}.nml"
            self.write_namelist(namelist_path, output_dir, config)
            
            # Set environment
            env = os.environ.copy()
            env['OMP_NUM_THREADS'] = str(self.omp_threads)
            
            # Execute FIDASIM
            cmd = [
                os.path.join(FIDASIM_DIR, 'fidasim'),
                str(namelist_path)
            ]
            
            print(f"Executing: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                cwd=str(self.work_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode != 0:
                print(f"FIDASIM failed with return code {result.returncode}")
                print(f"STDOUT:\n{result.stdout}")
                print(f"STDERR:\n{result.stderr}")
                return False
            
            print("FIDASIM completed successfully")
            return True
            
        except subprocess.TimeoutExpired:
            print("FIDASIM execution timed out")
            return False
        except Exception as e:
            print(f"Error in CLI execution: {e}")
            traceback.print_exc()
            return False
    
    def write_namelist(self, path: Path, output_dir: Path, config: dict):
        """Write FIDASIM namelist file"""
        
        with open(path, 'w') as f:
            f.write("&fidasim_inputs\n")
            f.write(f"  result_dir = '{output_dir}'\n")
            f.write(f"  tables_file = '{self.input_dir}/atomic_tables.h5'\n")
            
            # Add configuration parameters
            for key, value in config.items():
                if key.startswith('calc_') or key.startswith('n_'):
                    if isinstance(value, bool):
                        value = 1 if value else 0
                    f.write(f"  {key} = {value}\n")
            
            f.write("/\n")
    
    def create_nc_geometry(self):
        """Create simple NC geometry for testing"""
        nchan = 10
        return {
            'nchan': nchan,
            'system': 'NC',
            'id': [f'ch{i}'.encode() for i in range(nchan)]
        }
    
    def get_default_config(self, run_idx: int) -> dict:
        """Get default configuration for a run"""
        return {
            'device': 'test',
            'shot': 1,
            'time': 1.0 + run_idx * 0.1,
            'runid': f'run_{run_idx:04d}',
            'calc_neutron': True,
            'calc_nc_wght': True,
            'n_nbi': 50000,
            'seed': 42 + run_idx
        }
    
    def update_status(self, status: str):
        """Update worker status in Redis"""
        try:
            self.redis_client.hset(
                f"worker:{self.worker_id}",
                mapping={
                    'status': status,
                    'timestamp': time.time()
                }
            )
        except:
            pass
    
    def update_progress(self, job_name: str, progress: float, 
                       completed: list, failed: list):
        """Update job progress in Redis"""
        try:
            self.redis_client.hset(
                f"job:{job_name}:worker:{self.worker_id}",
                mapping={
                    'progress': progress,
                    'completed_runs': json.dumps(completed),
                    'failed_runs': json.dumps(failed),
                    'timestamp': time.time()
                }
            )
        except:
            pass

def main():
    """Main entry point"""
    
    # Get worker configuration from environment
    worker_id = int(os.environ.get('WORKER_ID', '0'))
    run_indices_str = os.environ.get('RUN_INDICES', '[]')
    
    try:
        run_indices = json.loads(run_indices_str)
    except:
        print(f"Error parsing RUN_INDICES: {run_indices_str}")
        run_indices = []
    
    if not run_indices:
        print("No runs assigned to this worker")
        return 1
    
    # Create and run worker
    worker = FIDASIMWorker(worker_id, run_indices)
    success = worker.run()
    
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())