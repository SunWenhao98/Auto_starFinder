#!/bin/bash

#SBATCH -J clustermap_seg
#SBATCH -o logs_clustermap/clustermap_%A_%a.out
#SBATCH -e logs_clustermap/clustermap_%A_%a.err

#SBATCH -p C64M512G
#SBATCH -n 1
#SBATCH -c 60
##SBATCH --mem=480G

#SBATCH --time=12:00:00
#SBATCH --array=1-8%8

echo "Loading Environment..."
# module purge
source /gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh
conda activate ClusterMap

mkdir -p logs_clustermap
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

# ================= Configuration =================
SCRIPT_ROOT="/gpfs/share/home/${USER}/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline"
PYTHON_SCRIPT="${SCRIPT_ROOT}/03_maskGeneration/run_clustermap_v2.py"
# /gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/03_maskGeneration/run_clustermap_v2.py
# CORE_MATLAB_DIR="${SCRIPT_ROOT}/core_programs/01_starfinder_for_OT1"
# export CORE_MATLAB_DIR

# ================= Input Parameters =================
PROJECT_ROOT=$1
PROJECT_NAME=$2
registration_folder=$3
ref_round=${4:-5}
OFFSET=${5:-0}             # array offset

# ClusterMap configuration parameters
CELL_NUM_THRESH=${6:-0.1}       # IC: cell number threshold(smaller value -> more cells)
DAPI_GRID=${7:-4}               # ID: DAPI grid interval(smaller value -> finer grid)
CELL_RADIUS=${8:-"50,10"}       # ICR: connected radius (xy,z)
PCT_FILTER=${9:-0.01}           # IPF: percentile filter threshold; DAPI 原图像的过滤
ROTATION=${10:-0}               # rotation angle for DAPI image
EXTRA_PREPROCESS=${11:-"F"}     # extra preprocessing for DAPI ("T" or "F")
SUB_SPAN=${12:-400}             # tiling window size
expected_workers=${13:-1}          # number of expected processes
READS_FILTERS=${14:-5}         
OVERLAP_PERCENT=${15:-0.2}
DAPI_SUFFIX=${16:-"ch03.tif"}
SPOT_CSV_NAME=${17:-"goodPoints_SpotFlow_0.1.csv"}


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
# 增加时间戳+随机数，确保每次运行脚本时生成的输出目录唯一，避免不同运行之间的结果互相覆盖。
output_dir="${PROJECT_ROOT}/${PROJECT_NAME}/${registration_folder}/${POSITION_NAME}/seg/clustermap_$(date +%Y%m%d_%H%M%S)_$SLURM_JOB_ID"
mkdir -p "${output_dir}"


transcripts_file_raw="${PROJECT_ROOT}/${PROJECT_NAME}/${registration_folder}/${POSITION_NAME}/${SPOT_CSV_NAME}"
if [ ! -f "$transcripts_file_raw" ]; then
    echo "Error: Transcripts CSV not found at: ${transcripts_file_raw}"
    exit 1
fi

transcripts_file_clean="${output_dir}/${SPOT_CSV_NAME%.*}_clean_genes.csv"
echo ">>> Cleaning gene names (removing _rbRNA/_ntRNA)..."
sed -e 's/_rbRNA//g' -e 's/_ntRNA//g' "${transcripts_file_raw}" > "${transcripts_file_clean}"
if [ ! -f "$transcripts_file_clean" ]; then
    echo "Error: Failed to create cleaned transcripts file."
    exit 1
fi

echo "------------------------------------------------"
echo "[INFO] Processing Position: ${POSITION_NAME}"
echo "[INFO] DAPI File:           ${dapi_file}"
echo "[INFO] Raw CSV:             ${transcripts_file_raw}"
echo "[INFO] Cleaned CSV:         ${transcripts_file_clean}"
echo "[INFO] Output Directory:    ${output_dir}"
echo "[INFO] Parameters:          Thresh=${CELL_NUM_THRESH}, Radius=${CELL_RADIUS}, Rot=${ROTATION}"
echo "------------------------------------------------"

# ================= EXECUTION =================

if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Critical Error: Python script not found at ${PYTHON_SCRIPT}"
    exit 1
fi

echo ">>> Running ClusterMap Segmentation..."
time python -u "${PYTHON_SCRIPT}" \
    --dapi_path "${dapi_file}" \
    --transcripts_file "${transcripts_file_clean}" \
    --output_path "${output_dir}" \
    --cell_num_threshold "${CELL_NUM_THRESH}" \
    --dapi_grid_interval "${DAPI_GRID}" \
    --cell_radius "${CELL_RADIUS}" \
    --pct_filter "${PCT_FILTER}" \
    --ref_round "${ref_round}" \
    --extra_preprocess "${EXTRA_PREPROCESS}" \
    --rotation "${ROTATION}" \
    --sub_span ${SUB_SPAN} \
    --expected_workers "${expected_workers}" \
    --reads_filter ${READS_FILTERS} \
    --overlap_percent ${OVERLAP_PERCENT}

if [ -f "${output_dir}/cell_center.csv" ]; then
    echo ">>> ClusterMap Finished Successfully!"
    echo "Results generated in: ${output_dir}"
else
    echo "Error: ClusterMap failed to generate 'cell_center.csv'. Check logs above."
    exit 1
fi

end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "运行时间: $(($end_time - $start_time)) seconds"