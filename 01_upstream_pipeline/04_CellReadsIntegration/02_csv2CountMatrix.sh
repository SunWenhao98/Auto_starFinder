#!/bin/bash

#SBATCH -J segResultsStitch
#SBATCH -o logs_csv2CountMatrix/csv2CountMatrix_%A_%a.out
#SBATCH -e logs_csv2CountMatrix/csv2CountMatrix_%A_%a.err

#SBATCH -p C64M256G
#SBATCH -n 1
#SBATCH -c 8
#SBATCH --mem=32G

#SBATCH --time=12:00:00


echo "Loading Environment..."
source /gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh
conda activate data_analysis_env


mkdir -p logs_csv2CountMatrix
start_time=$(date +%s)
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"


echo "============= SLURM Job Info =================="
echo "Job ID:          $SLURM_JOB_ID"
echo "Job Name:        $SLURM_JOB_NAME"
echo "User:            $SLURM_JOB_USER"
echo "Submit Host:     $SLURM_SUBMIT_HOST"
echo "Submit Directory:$SLURM_SUBMIT_DIR"
echo "Node List:       $SLURM_NODELIST"
echo "Job Node:        $SLURMD_NODENAME"
echo "Number of Nodes: $SLURM_JOB_NUM_NODES"
echo "Partition:       $SLURM_JOB_PARTITION"

echo "============= CPU/Memory Allocation ============="
echo "CPUs per task:   $SLURM_CPUS_PER_TASK"
echo "Allocated CPUs:  $SLURM_JOB_CPUS_PER_NODE"

echo "Tasks per node:  $SLURM_NTASKS_PER_NODE"
echo "Total Tasks:     $SLURM_NTASKS"
echo "Memory per node: $SLURM_MEM_PER_NODE MB"


echo "Running csv2CountMatrix.py..."
python_script=$1
input_dir=$2

python -u $python_script \
    --input_dir $input_dir

end_time=$(date +%s)
elapsed=$(( end_time - start_time ))
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Elapsed time: $elapsed seconds"