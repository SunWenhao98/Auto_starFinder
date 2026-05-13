#!/bin/bash

#SBATCH -J clustermap_vis
#SBATCH -o logs_vis/clustermap_%A_%a.out
#SBATCH -e logs_vis/clustermap_%A_%a.err

#SBATCH -p C64M512G
#SBATCH -n 1
#SBATCH -c 8

#SBATCH --time=24:00:00
#SBATCH --array=1-8%8

echo "Loading Environment..."
# module purge
source /gpfs/share/home/2300012257/anaconda3/etc/profile.d/conda.sh
conda activate ClusterMap

mkdir -p logs_clustermap
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

# ================= Configuration =================
SCRIPT_ROOT="/gpfs/share/home/2300012257/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline"
CORE_MATLAB_DIR="${SCRIPT_ROOT}/core_programs/01_starfinder_for_OT1"
PYTHON_SCRIPT="${SCRIPT_ROOT}/03_maskGeneration/generate_qc_plot.py"
export CORE_MATLAB_DIR

# ================= Input Parameters =================
PROJECT_ROOT=$1
PROJECT_NAME=$2
registration_folder=$3
ref_round=${4:-1}
OFFSET=${5:-0}             # array offset

# ClusterMap configuration parameters
RADIUS=${6:-5}
ALPHA=${7:-0.5}

DAPI_SUFFIX="ch03.tif" 
CLUSTERMAP_CSV_NAME="remain_reads_raw.csv"

# ================= Task Setup =================
TASK_ID=$(( SLURM_ARRAY_TASK_ID + OFFSET ))
index=$(( TASK_ID - 1 ))

reference_dir="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/round00${ref_round}"

declare -a dapi_files
readarray -t dapi_files < <(find "${reference_dir}" -maxdepth 2 -name "*${DAPI_SUFFIX}" | sort -V)

if [ "$index" -ge "${#dapi_files[@]}" ]; then
    echo "Error: Task ID $index exceeds number of files (${#dapi_files[@]}). Exiting."
    exit 1
fi

dapi_file="${dapi_files[$index]}"
POSITION_NAME=$(basename "$(dirname "${dapi_file}")")

output_dir="${PROJECT_ROOT}/${PROJECT_NAME}/${registration_folder}/${POSITION_NAME}/seg/clustermap"

clustermap_file="${output_dir}/${CLUSTERMAP_CSV_NAME}"

if [ ! -f "$clustermap_file" ]; then
    echo "Error: clustermap CSV not found at: ${clustermap_file}"
    exit 1
fi

echo "------------------------------------------------"
echo "Processing Position: ${POSITION_NAME}"
echo "DAPI File:           ${dapi_file}"
echo "clustermap File:     ${clustermap_file}"
echo "Output Directory:    ${output_dir}"
echo "Parameters:          RADIUS=${RADIUS}, ALPHA=${ALPHA}"
echo "------------------------------------------------"

# ================= EXECUTION =================

if [ ! -d "$output_dir" ]; then
  mkdir -p "$output_dir"
fi

time python "$PYTHON_SCRIPT" \
    --input_dapi ${dapi_file} \
    --input_csv ${clustermap_file} \
    --output_dir ${output_dir} \
    --qc_radius ${RADIUS} \
    --qc_alpha ${ALPHA}

echo ">>> Visualization Finished Successfully!"
echo "Results generated in: $output_dir"