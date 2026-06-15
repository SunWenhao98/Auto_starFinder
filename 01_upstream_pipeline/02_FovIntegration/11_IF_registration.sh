#!/bin/bash
#SBATCH -J IF_Registration
#SBATCH -o logs_IF_registration/IF_registration_%A_%a.out  
#SBATCH -e logs_IF_registration/IF_registration_%A_%a.err

#SBATCH -p C64M512G
#SBATCH -c 4

#SBATCH --time=24:00:00
#SBATCH --array=1-49%25

module purge
module load matlab/2023a

mkdir -p logs_IF_registration
start_time=$(date +%s)
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"


CORE_MATLAB_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/core_programs"
export CORE_MATLAB_DIR

# SCRIPT_DIR=${SLURM_SUBMIT_DIR:-$(pwd)}
# PROJECT_NAME=$(basename "$(dirname "$SCRIPT_DIR")")
# echo "脚本所在目录 (SCRIPT_DIR): ${SCRIPT_DIR}"
# echo "自动获取的项目名称 (PROJECT_NAME): ${PROJECT_NAME}"


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

echo "============= Allocated CPUs Info ============="
echo "CPUs per task:   $SLURM_CPUS_PER_TASK"
echo "Allocated CPUs:  $SLURM_JOB_CPUS_PER_NODE"  # 实际分配的每节点CPU数

echo "Tasks per node:  $SLURM_NTASKS_PER_NODE"
echo "Total Tasks:     $SLURM_NTASKS"
echo "Memory per node: $SLURM_MEM_PER_NODE MB"
echo "==============================================="




PROJECT_ROOT=$1
PROJECT_NAME=$2
registration_folder=$3
OFFSET=${4:-0}

image_width=${5:-2304}
image_depth=${6:-38}
ref_round=${7:-1}
channel_num=${8:-3}
round_num=${9:-6}

input_format=${10:-"uint16"}
norm_out_format=${11:-"uint8"}
protein_outdir=${12:-"IF"}


echo "[INFO] PROJECT_ROOT: $PROJECT_ROOT"
echo "[INFO] PROJECT_NAME: $PROJECT_NAME"
echo "[INFO] registration_folder: $registration_folder"
echo "[INFO] reference round: $ref_round"


TASK_ID=$(( SLURM_ARRAY_TASK_ID + OFFSET ))
# 这个逻辑适合访问 Position ID 连续的情形；
# POSITION_NAME=$(printf "Position%03d" $TASK_ID)

# Position ID 不从001开始，且不连续
index=$((TASK_ID - 1))

DATA_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/round001"
declare -a positions
readarray -t positions < <(find "${DATA_DIR}" -maxdepth 1 -type d -name "Position*" | sort -V)

if [ ${#positions[@]} -eq 0 ]; then
    echo "Error: No 'Position*' folders found in directory ${DATA_DIR}." >&2
    exit 1
fi

if [[ "$index" -lt 0 || "$index" -ge ${#positions[@]} ]]; then
    echo "Error: SLURM_ARRAY_TASK_ID (${TASK_ID}) is out of valid range [1-${#positions[@]}]." >&2
    exit 1
fi

POSITION_NAME=$(basename "${positions[$index]}")


echo "Task ID: ${TASK_ID}"
echo "Selected Position folder: ${POSITION_NAME}"
echo "------------------- start processing ..."

matlab -batch "addpath(genpath('$CORE_MATLAB_DIR')); core_matlab_new('$PROJECT_NAME', 'nuclei_protein_registration', '$POSITION_NAME', \
    $image_width, $image_depth, $ref_round, $channel_num, $round_num, \
    '$PROJECT_ROOT', '01_data', '$registration_folder', 'log', \
    'protein_round', 'IF', 'protein_outdir', '$protein_outdir', \
    'input_format', '$input_format', 'norm_out_format', '$norm_out_format', \
    'protein_stains', {'488-CD144', '561-CA9', '647-CD31', 'DAPI'})"
# 根据实际情况修改数据采集时所使用的染料


end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Elapsed time: $(($end_time - $start_time)) seconds"