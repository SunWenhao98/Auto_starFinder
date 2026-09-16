#!/bin/bash
#SBATCH -J decode_pairwise_correlation
#SBATCH -o logs007_decode_pairwise_correlation/%x_%A.out
#SBATCH -e logs007_decode_pairwise_correlation/%x_%A.err
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
GENE_COUNTS_DIR="00_gene_counts"
GENE_COUNTS_FILES="auto"
OUTPUT_SUBDIR="02_decode_pairwise_correlation"
ANALYSIS_LABEL="auto"
NO_PLOTS="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --gene_counts_dir) GENE_COUNTS_DIR="$2"; shift 2 ;;
        --gene_counts_files) GENE_COUNTS_FILES="$2"; shift 2 ;;
        --output_subdir) OUTPUT_SUBDIR="$2"; shift 2 ;;
        --analysis_label) ANALYSIS_LABEL="$2"; shift 2 ;;
        --no_plots) NO_PLOTS="$2"; shift 2 ;;
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
OUTPUT_DIR="${REGISTRATION_DIR}/${OUTPUT_SUBDIR}"
PY_SCRIPT="${SCRIPT_DIR}/run_decode_pairwise_correlation.py"

RESOLVED_GENE_COUNTS_DIR="${GENE_COUNTS_DIR}"
if [[ "${RESOLVED_GENE_COUNTS_DIR}" != /* ]]; then
    RESOLVED_GENE_COUNTS_DIR="${REGISTRATION_DIR}/${RESOLVED_GENE_COUNTS_DIR}"
fi

print_slurm_info
echo "PROJECT_ROOT=${PROJECT_ROOT}"
echo "PROJECT_NAME=${PROJECT_NAME}"
echo "REGISTRATION_FOLDER=${REGISTRATION_FOLDER}"
echo "REGISTRATION_DIR=${REGISTRATION_DIR}"
echo "GENE_COUNTS_DIR=${GENE_COUNTS_DIR}"
echo "GENE_COUNTS_FILES=${GENE_COUNTS_FILES}"
echo "OUTPUT_DIR=${OUTPUT_DIR}"
echo "ANALYSIS_LABEL=${ANALYSIS_LABEL}"
echo "NO_PLOTS=${NO_PLOTS}"
echo "PY_SCRIPT=${PY_SCRIPT}"
echo "CONDA_SH=${CONDA_SH}"

if [[ ! -d "${REGISTRATION_DIR}" || ! -d "${RESOLVED_GENE_COUNTS_DIR}" ]]; then
    echo "Pairwise correlation input path validation failed." >&2
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

COMMAND=(
    python -u "${PY_SCRIPT}"
    --sample_id "${PROJECT_NAME}"
    --registration_dir "${REGISTRATION_DIR}"
    --gene_counts_dir "${GENE_COUNTS_DIR}"
    --output_dir "${OUTPUT_DIR}"
    --analysis_label "${ANALYSIS_LABEL}"
)
if [[ "${GENE_COUNTS_FILES}" != "auto" ]]; then
    COMMAND+=(--gene_counts_files)
    IFS=',' read -ra FILE_LIST <<< "${GENE_COUNTS_FILES}"
    for file_name in "${FILE_LIST[@]}"; do
        file_name="${file_name#"${file_name%%[![:space:]]*}"}"
        file_name="${file_name%"${file_name##*[![:space:]]}"}"
        if [[ -n "${file_name}" ]]; then
            COMMAND+=("${file_name}")
        fi
    done
fi
if [[ "${NO_PLOTS}" == "true" ]]; then
    COMMAND+=(--no_plots)
fi
"${COMMAND[@]}"
