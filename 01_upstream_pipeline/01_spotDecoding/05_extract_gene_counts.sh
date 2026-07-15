#!/bin/bash
#SBATCH -J extract_gene_counts
#SBATCH -o logs_extract_gene_counts/extract_gene_counts_%A.out
#SBATCH -e logs_extract_gene_counts/extract_gene_counts_%A.err
#SBATCH -p C64M512G
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=32G
#SBATCH --time=04:00:00

set -euo pipefail

mkdir -p logs_extract_gene_counts
start_time=$(date +%s)
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"

echo "============= SLURM Job Info =================="
echo "Job ID:          ${SLURM_JOB_ID:-NA}"
echo "Job Name:        ${SLURM_JOB_NAME:-NA}"
echo "User:            ${SLURM_JOB_USER:-${USER:-NA}}"
echo "Submit Host:     ${SLURM_SUBMIT_HOST:-NA}"
echo "Submit Directory:${SLURM_SUBMIT_DIR:-$(pwd)}"
echo "Node List:       ${SLURM_NODELIST:-NA}"
echo "Job Node:        ${SLURMD_NODENAME:-NA}"
echo "Partition:       ${SLURM_JOB_PARTITION:-NA}"
echo "CPUs per task:   ${SLURM_CPUS_PER_TASK:-NA}"
echo "==============================================="

PROJECT_ROOT=$1
PROJECT_NAME=$2
registration_folder=$3
target_file=${4:-goodPoints_max3d_0.2_tri.csv}
gene_column=${5:-Gene}
suffix_regex=${6:-'_(rbRNA|ntRNA)$'}
output_subdir=${7:-00_gene_counts}
start_pos=${8:-none}
end_pos=${9:-none}

REGISTRATION_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/${registration_folder}"
SCRIPT_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/01_spotDecoding"
PY_SCRIPT="${SCRIPT_DIR}/p05_extract_gene_counts.py"
PYTHON=/gpfs/share/home/2401111558/anaconda3/envs/data_analysis_env/bin/python

echo "[INFO] PROJECT_ROOT: ${PROJECT_ROOT}"
echo "[INFO] PROJECT_NAME: ${PROJECT_NAME}"
echo "[INFO] registration_folder: ${registration_folder}"
echo "[INFO] REGISTRATION_DIR: ${REGISTRATION_DIR}"
echo "[INFO] SCRIPT_DIR: ${SCRIPT_DIR}"
echo "[INFO] PY_SCRIPT: ${PY_SCRIPT}"
echo "[INFO] target_file: ${target_file}"
echo "[INFO] gene_column: ${gene_column}"
echo "[INFO] suffix_regex: ${suffix_regex}"
echo "[INFO] output_subdir: ${output_subdir}"
echo "[INFO] start_pos: ${start_pos}"
echo "[INFO] end_pos: ${end_pos}"

if [ ! -d "${REGISTRATION_DIR}" ]; then
    echo "STATUS: FAILED"
    echo "错误: registration directory 不存在: ${REGISTRATION_DIR}" >&2
    exit 1
fi

if [ ! -f "${PY_SCRIPT}" ]; then
    echo "STATUS: FAILED"
    echo "错误: p05_extract_gene_counts.py 不存在: ${PY_SCRIPT}" >&2
    exit 1
fi

"${PYTHON}" "${PY_SCRIPT}" \
    --registration-dir "${REGISTRATION_DIR}" \
    --target-file "${target_file}" \
    --gene-column "${gene_column}" \
    --suffix-regex "${suffix_regex}" \
    --output-subdir "${output_subdir}" \
    --sample-id "${PROJECT_NAME}" \
    --start-pos "${start_pos}" \
    --end-pos "${end_pos}"

end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "运行时间: $(($end_time - $start_time)) seconds"
echo "STATUS: SUCCESS"
