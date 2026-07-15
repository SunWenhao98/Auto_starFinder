#!/bin/bash
#SBATCH -J atlas_correlation
#SBATCH -o logs_atlas_correlation/atlas_correlation_%A.out
#SBATCH -e logs_atlas_correlation/atlas_correlation_%A.err
#SBATCH -p C64M512G
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=32G
#SBATCH --time=04:00:00

set -euo pipefail

mkdir -p logs_atlas_correlation
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
gene_counts_file=$4
atlas_dir=$5
output_subdir=$6
sample_filter_column=$7
sample_filter_contains=$8
category_column=$9
sample_id_column=${10}
analysis_label=${11:-auto}
no_plots=${12:-false}
if [ "$#" -eq 11 ] && { [ "${analysis_label}" = "true" ] || [ "${analysis_label}" = "false" ]; }; then
    no_plots="${analysis_label}"
    analysis_label="auto"
fi

REGISTRATION_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/${registration_folder}"
OUTPUT_DIR="${REGISTRATION_DIR}/${output_subdir}"
SCRIPT_DIR="/gpfs/share/home/2401111558/00_scripts/06_BioinfoSummary/03_reusable_correlation/scripts"
PY_SCRIPT="${SCRIPT_DIR}/run_atlas_correlation.py"
PYTHON=/gpfs/share/home/2401111558/anaconda3/envs/data_analysis_env/bin/python

echo "[INFO] PROJECT_ROOT: ${PROJECT_ROOT}"
echo "[INFO] PROJECT_NAME: ${PROJECT_NAME}"
echo "[INFO] registration_folder: ${registration_folder}"
echo "[INFO] REGISTRATION_DIR: ${REGISTRATION_DIR}"
echo "[INFO] gene_counts_file: ${gene_counts_file}"
echo "[INFO] atlas_dir: ${atlas_dir}"
echo "[INFO] OUTPUT_DIR: ${OUTPUT_DIR}"
echo "[INFO] sample_filter_column: ${sample_filter_column}"
echo "[INFO] sample_filter_contains: ${sample_filter_contains}"
echo "[INFO] category_column: ${category_column}"
echo "[INFO] sample_id_column: ${sample_id_column}"
echo "[INFO] analysis_label: ${analysis_label}"
echo "[INFO] no_plots: ${no_plots}"
echo "[INFO] PY_SCRIPT: ${PY_SCRIPT}"

if [ ! -d "${REGISTRATION_DIR}" ]; then
    echo "STATUS: FAILED"
    echo "错误: registration directory 不存在: ${REGISTRATION_DIR}" >&2
    exit 1
fi

if [ ! -d "${atlas_dir}" ]; then
    echo "STATUS: FAILED"
    echo "错误: atlas directory 不存在: ${atlas_dir}" >&2
    exit 1
fi

resolved_gene_counts_file="${gene_counts_file}"
if [[ "${resolved_gene_counts_file}" != /* ]]; then
    resolved_gene_counts_file="${REGISTRATION_DIR}/${resolved_gene_counts_file}"
fi

if [ ! -f "${resolved_gene_counts_file}" ]; then
    echo "STATUS: FAILED"
    echo "错误: gene_counts file 不存在: ${resolved_gene_counts_file}" >&2
    exit 1
fi

if [ ! -f "${PY_SCRIPT}" ]; then
    echo "STATUS: FAILED"
    echo "错误: run_atlas_correlation.py 不存在: ${PY_SCRIPT}" >&2
    exit 1
fi

cmd=(
    "${PYTHON}" "${PY_SCRIPT}"
    --sample_id "${PROJECT_NAME}"
    --registration_dir "${REGISTRATION_DIR}"
    --gene_counts_file "${gene_counts_file}"
    --atlas_dir "${atlas_dir}"
    --output_dir "${OUTPUT_DIR}"
    --sample_filter_column "${sample_filter_column}"
    --sample_filter_contains "${sample_filter_contains}"
    --category_column "${category_column}"
    --sample_id_column "${sample_id_column}"
    --analysis_label "${analysis_label}"
)

if [ "${no_plots}" = "true" ]; then
    cmd+=(--no_plots)
fi

"${cmd[@]}"

end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "运行时间: $(($end_time - $start_time)) seconds"
echo "STATUS: SUCCESS"
