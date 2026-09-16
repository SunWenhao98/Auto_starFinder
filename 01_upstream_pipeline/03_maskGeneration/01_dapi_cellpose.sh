#!/bin/bash
#SBATCH -J dapi_segmentation
#SBATCH -o logs008_dapi_segmentation/%x_%A_%a.out
#SBATCH -e logs008_dapi_segmentation/%x_%A_%a.err
#SBATCH -p GPUA800
#SBATCH -N 1
#SBATCH -c 1
#SBATCH --gres=gpu:1
#SBATCH --time=24:00:00
#SBATCH --array=1-8%8

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
REF_ROUND="1"
DIAMETER="100"
AREA_THRESHOLD="1600"
OFFSET="0"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --ref_round) REF_ROUND="$2"; shift 2 ;;
        --diameter) DIAMETER="$2"; shift 2 ;;
        --area_threshold) AREA_THRESHOLD="$2"; shift 2 ;;
        --offset) OFFSET="$2"; shift 2 ;;
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

TASK_ID=$((SLURM_ARRAY_TASK_ID + OFFSET))
POSITION_INDEX=$((TASK_ID - 1))
printf -v ROUND_DIR "round%03d" "$((10#${REF_ROUND}))"
REFERENCE_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/${ROUND_DIR}"
readarray -t DAPI_FILES < <(find -L "${REFERENCE_DIR}" -maxdepth 2 -type f -name "*ch03.tif" | sort -V)
if (( POSITION_INDEX < 0 || POSITION_INDEX >= ${#DAPI_FILES[@]} )); then
    echo "Task ID ${TASK_ID} is outside the available DAPI file range." >&2
    exit 1
fi

DAPI_FILE="${DAPI_FILES[POSITION_INDEX]}"
POSITION_NAME=$(basename "$(dirname "${DAPI_FILE}")")
REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
OUTPUT_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}/${POSITION_NAME}/seg/dapi_cellpose"
RUNNER="${SCRIPT_DIR}/run_cellpose.py"
if [[ ! -f "${RUNNER}" || ! -f "${CONDA_SH}" ]]; then
    echo "Runner or conda initialization path validation failed." >&2
    exit 1
fi
mkdir -p "${OUTPUT_DIR}"

print_slurm_info
echo "PROJECT_ROOT=${PROJECT_ROOT}"
echo "PROJECT_NAME=${PROJECT_NAME}"
echo "REGISTRATION_FOLDER=${REGISTRATION_FOLDER}"
echo "TASK_ID=${TASK_ID}"
echo "POSITION_NAME=${POSITION_NAME}"
echo "DAPI_FILE=${DAPI_FILE}"
echo "OUTPUT_DIR=${OUTPUT_DIR}"
echo "RUNNER=${RUNNER}"
echo "CONDA_SH=${CONDA_SH}"
echo "DIAMETER=${DIAMETER}"
echo "AREA_THRESHOLD=${AREA_THRESHOLD}"
echo "OFFSET=${OFFSET}"

source "${CONDA_SH}"
set +u
conda activate cellpose
set -u

python -u "${RUNNER}" \
    --input "${DAPI_FILE}" \
    --output_base "${OUTPUT_DIR}/${POSITION_NAME}_dapi2d_cellpose" \
    --diameter "${DIAMETER}" \
    --threshold "${AREA_THRESHOLD}"
