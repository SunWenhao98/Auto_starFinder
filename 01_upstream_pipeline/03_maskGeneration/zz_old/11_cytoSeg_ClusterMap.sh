#!/bin/bash

#SBATCH -J cytoSeg_ClusterMap
#SBATCH -o logs_cytoSeg_ClusterMap/cytoSeg_ClusterMap_%A_%a.out
#SBATCH -e logs_cytoSeg_ClusterMap/cytoSeg_ClusterMap_%A_%a.err

#SBATCH -p C64M512G
#SBATCH -c 16

#SBATCH --time=24:00:00
#SBATCH --array=1-25%25

# 加载环境
echo "Loading Environment..."
module purge
source /gpfs/share/home/2401111558/anaconda3/etc/profile.d/conda.sh
conda activate clustermap

mkdir -p logs_cytoSeg_ClusterMap
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

echo "============= Allocated CPUs Info ============="
echo "CPUs per task:   $SLURM_CPUS_PER_TASK"
echo "Allocated CPUs:  $SLURM_JOB_CPUS_PER_NODE"  # 实际分配的每节点CPU数

echo "Tasks per node:  $SLURM_NTASKS_PER_NODE"
echo "Total Tasks:     $SLURM_NTASKS"
echo "Memory per node: $SLURM_MEM_PER_NODE MB"
echo "==============================================="

SCRIPT_ROOT="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline"
CORE_MATLAB_DIR="${SCRIPT_ROOT}/core_programs/01_starfinder_for_OT1"
SCRIPT_PATH="${SCRIPT_ROOT}/03_maskGeneration/run_cellpose.py"
export CORE_MATLAB_DIR

# ================= Processing =================
PROJECT_ROOT=$1
PROJECT_NAME=$2
registration_folder=$3
ref_round=${4:-1}
DIAMETER=${5:-100}         # 细胞核直径
OFFSET=${6:-0}             # 数组任务的偏移量


TASK_ID=$(( SLURM_ARRAY_TASK_ID + OFFSET ))
index=$(( TASK_ID - 1 ))
reference_dir="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/round00${ref_round}"

declare -a dapi_files
readarray -t dapi_files < <(find "${reference_dir}" -maxdepth 2 -name "*ch03.tif" | sort -V)
dapi_file=${dapi_files[$index]}
POSITION_NAME=$(basename "$(dirname "${dapi_file}")")
output_dir="${PROJECT_ROOT}/${PROJECT_NAME}/${registration_folder}/${POSITION_NAME}/seg/dapi_cellpose"
mkdir -p "${output_dir}"

echo "Processing file: ${dapi_file}"
echo "Position Name: ${POSITION_NAME}"
echo "Output Dir: ${output_dir}"


# ================= EXECUTION =================
npy_file="${output_dir}/${POSITION_NAME}_dapi2d_cellpose.npy"

# 运行 2D Cellpose 分割 ---
echo ">>> Running 2D Cellpose Segmentation..."

python -u "${SCRIPT_PATH}" \
    --input "${dapi_file}" \
    --output_base "${output_dir}" \
    --diameter ${DIAMETER}

# 检查是否生成了 npy 文件
if [ ! -f "$npy_file" ]; then
    echo "Error: Cellpose 运行结束，但未找到输出文件: ${npy_file}"
    exit 1
fi
echo "Cellpose 2D Output Found: ${npy_file}"
