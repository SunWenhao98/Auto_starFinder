#!/bin/bash

#SBATCH -J RNA_restore_suffix
#SBATCH -o logs_RNA_rs/RNA_rs_%A_%a.out
#SBATCH -e logs_RNA_rs/RNA_rs_%A_%a.err
#SBATCH -p C64M512G
#SBATCH --qos=normal
#SBATCH -n 1
#SBATCH -c 2
#SBATCH --mem=16G

#SBATCH --time=12:00:00
#SBATCH --array=1-8%8


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


# 创建日志目录
mkdir -p logs_RNA_rs
echo "Load conda environment"
source /gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh
conda activate data_analysis_env


# /gpfs/share/home/2401111558/labShare/2401111558/01_project/08_projGBM/01_Data/03_rawTifDir/GBM001/02_registration001_GBM001_NormalDecode/Position001/goodPoints_max3d_0.2_tri.csv
# /gpfs/share/home/2401111558/labShare/2401111558/01_project/08_projGBM/01_Data/03_rawTifDir/GBM001/02_registration001_GBM001_NormalDecode/Position001/seg/clustermap_20260504_213804_1550443/remain_reads_raw.csv
# /gpfs/share/home/2401111558/labShare/2401111558/01_project/08_projGBM/01_Data/03_rawTifDir/GBM001/02_registration001_GBM001_NormalDecode/Position001/seg/clustermap_20260504_213804_1550443/remain_reads_assigned.csv


input_dir=$1
segout_dir=$2

raw_csv=$3
remained_csv=$4
output_csv=$5

img_c=$6
img_r=$7
rotation_deg=$8
tolerance=$9
OFFSET=${10:-0}

echo "input_dir: $input_dir"
echo "segout_dir: $segout_dir"
echo "raw_csv: $raw_csv"
echo "remained_csv: $remained_csv"
echo "output_csv: $output_csv"

echo "img_c: $img_c"
echo "img_r: $img_r"
echo "rotation_deg: $rotation_deg"
echo "tolerance: $tolerance"
echo "OFFSET: $OFFSET"

echo "Start to restore RNA suffix"
echo "Running job on $(hostname)"
echo "Start time: $(date +%Y-%m-%d_%H:%M:%S)"
Start_time=$(date +%s)

TASK_ID=$(( SLURM_ARRAY_TASK_ID + OFFSET ))
index=$((TASK_ID - 1))

DATA_DIR="${input_dir}"
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

REAL_SEGOUT_DIR=$(ls -d ${DATA_DIR}/${POSITION_NAME}/seg/clustermap* | head -n 1)
raw_csv="${DATA_DIR}/${POSITION_NAME}/${raw_csv}"
remained_csv="${REAL_SEGOUT_DIR}/${remained_csv}"
output_csv="${REAL_SEGOUT_DIR}/${output_csv}"

# 检查文件是否存在
if [ -f "$remained_csv" ]; then
    echo "成功匹配到文件: $remained_csv"
else
    echo "错误: 无法找到文件，请检查路径"
fi


echo "Task ID: ${TASK_ID}"
echo "Selected Position folder: ${POSITION_NAME}"
echo "------------------- start processing ..."





python -u /gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/03_maskGeneration/restore_rna_suffix.py \
    --raw_csv "${raw_csv}" \
    --processed_csv "${remained_csv}" \
    --output_csv "${output_csv}" \
    --img_c "${img_c}" \
    --img_r "${img_r}" \
    --rotation_deg "${rotation_deg}" \
    --tolerance "${tolerance}"

echo "Done!"
echo "End time: $(date +%Y-%m-%d_%H:%M:%S)"
End_time=$(date +%s)
echo "Total time: $(expr $End_time - $Start_time) seconds"