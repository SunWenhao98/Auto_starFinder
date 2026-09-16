#!/bin/bash
#SBATCH -J extract_gene_counts
#SBATCH -o logs005_extract_gene_counts/%x_%A.out
#SBATCH -e logs005_extract_gene_counts/%x_%A.err
#SBATCH -p C64M512G
#SBATCH -N 1
#SBATCH -c 4
#SBATCH --time=04:00:00

set -euo pipefail

print_usage() {
    echo "Usage: $0 --project_root PATH --project_name NAME --reg_dir_suffix SUFFIX [options]"
}

print_slurm_info() {
    echo "Job ID:          $SLURM_JOB_ID"
    echo "Job Name:        $SLURM_JOB_NAME"
    echo "User:            $SLURM_JOB_USER"
    echo "Submit Host:     $SLURM_SUBMIT_HOST"
    echo "Submit Directory:$SLURM_SUBMIT_DIR"
    echo "Node List:       $SLURM_NODELIST"
    echo "Job Node:        $SLURMD_NODENAME"
    echo "Number of Nodes: $SLURM_JOB_NUM_NODES"
    echo "Partition:       $SLURM_JOB_PARTITION"
    echo "CPUs per task:   $SLURM_CPUS_PER_TASK"
    echo "Allocated CPUs:  $SLURM_JOB_CPUS_PER_NODE"
}

PROJECT_ROOT=""
PROJECT_NAME=""
REG_DIR_SUFFIX=""
SCRIPT_DIR=""
CONDA_SH=""
TARGET_FILE="goodPoints_max3d_0.2_tri.csv"
GENE_COLUMN="Gene"
SUFFIX_REGEX="_(rbRNA|ntRNA)$"
OUTPUT_SUBDIR="00_gene_counts"
START_POS="none"
END_POS="none"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --target_file) TARGET_FILE="$2"; shift 2 ;;
        --gene_column) GENE_COLUMN="$2"; shift 2 ;;
        --suffix_regex) SUFFIX_REGEX="$2"; shift 2 ;;
        --output_subdir) OUTPUT_SUBDIR="$2"; shift 2 ;;
        --start_pos) START_POS="$2"; shift 2 ;;
        --end_pos) END_POS="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) print_usage >&2; exit 2 ;;
    esac
done

START_TIME=$(date +%s)
START_TIME_TEXT=$(date '+%Y-%m-%d %H:%M:%S')
FINAL_STATUS=""

finish() {
    local exit_code=$?
    local end_time
    local end_time_text
    local status
    end_time=$(date +%s)
    end_time_text=$(date '+%Y-%m-%d %H:%M:%S')
    if (( exit_code == 0 )); then
        status="${FINAL_STATUS:-SUCCESS}"
    else
        status="FAILED"
    fi
    echo "开始时间: ${START_TIME_TEXT}"
    echo "结束时间: ${end_time_text}"
    echo "运行时间: $((end_time - START_TIME)) seconds"
    echo "STATUS: ${status} | SLURM_JOB_NAME=${SLURM_JOB_NAME:-N/A}"
}
trap finish EXIT

REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REGISTRATION_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
PY_SCRIPT="${SCRIPT_DIR}/p05_extract_gene_counts.py"

print_slurm_info
echo "PROJECT_ROOT=${PROJECT_ROOT}"
echo "PROJECT_NAME=${PROJECT_NAME}"
echo "REGISTRATION_FOLDER=${REGISTRATION_FOLDER}"
echo "REGISTRATION_DIR=${REGISTRATION_DIR}"
echo "PY_SCRIPT=${PY_SCRIPT}"
echo "CONDA_SH=${CONDA_SH}"
echo "TARGET_FILE=${TARGET_FILE}"
echo "GENE_COLUMN=${GENE_COLUMN}"
echo "SUFFIX_REGEX=${SUFFIX_REGEX}"
echo "OUTPUT_SUBDIR=${OUTPUT_SUBDIR}"
echo "START_POS=${START_POS}"
echo "END_POS=${END_POS}"

if [[ ! -d "${REGISTRATION_DIR}" ]]; then
    echo "Registration directory does not exist: ${REGISTRATION_DIR}" >&2
    exit 1
fi
if [[ ! -f "${PY_SCRIPT}" ]]; then
    echo "Runner does not exist: ${PY_SCRIPT}" >&2
    exit 1
fi
if [[ ! -f "${CONDA_SH}" ]]; then
    echo "Conda initialization script does not exist: ${CONDA_SH}" >&2
    exit 1
fi

source "${CONDA_SH}"
set +u
conda activate data_analysis_env
set -u

python -u "${PY_SCRIPT}" \
    --registration-dir "${REGISTRATION_DIR}" \
    --target-file "${TARGET_FILE}" \
    --gene-column "${GENE_COLUMN}" \
    --suffix-regex "${SUFFIX_REGEX}" \
    --output-subdir "${OUTPUT_SUBDIR}" \
    --sample-id "${PROJECT_NAME}" \
    --start-pos "${START_POS}" \
    --end-pos "${END_POS}"
