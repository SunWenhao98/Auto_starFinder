#!/bin/bash
#SBATCH -J RNA_restore_suffix
#SBATCH -o logs021_RNA_restore_suffix/%x_%A_%a.out
#SBATCH -e logs021_RNA_restore_suffix/%x_%A_%a.err
#SBATCH -p C64M512G
#SBATCH --qos=normal
#SBATCH -N 1
#SBATCH -c 2
#SBATCH --time=12:00:00
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
RAW_CSV="goodPoints_max3d_0.2_tri.csv"
PROCESSED_CSV="remain_reads_raw.csv"
OUTPUT_CSV="remain_reads_assigned.csv"
IMG_C="2048"
IMG_R="2048"
ROTATION_DEG="0"
TOLERANCE="2"
OUTPUT_LABEL="auto"
OFFSET="0"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --raw_csv) RAW_CSV="$2"; shift 2 ;;
        --processed_csv) PROCESSED_CSV="$2"; shift 2 ;;
        --output_csv) OUTPUT_CSV="$2"; shift 2 ;;
        --img_c) IMG_C="$2"; shift 2 ;;
        --img_r) IMG_R="$2"; shift 2 ;;
        --rotation_deg) ROTATION_DEG="$2"; shift 2 ;;
        --tolerance) TOLERANCE="$2"; shift 2 ;;
        --output_label) OUTPUT_LABEL="$2"; shift 2 ;;
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
REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REGISTRATION_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
readarray -t POSITIONS < <(find -L "${REGISTRATION_DIR}" -maxdepth 1 -type d -name "Position*" | sort -V)
if (( POSITION_INDEX < 0 || POSITION_INDEX >= ${#POSITIONS[@]} )); then
    echo "Task ID ${TASK_ID} is outside the available Position range." >&2
    exit 1
fi

POSITION_DIR="${POSITIONS[POSITION_INDEX]}"
POSITION_NAME=$(basename "${POSITION_DIR}")
CLEAN_CSV_NAME="${RAW_CSV%.*}_clean_genes.csv"
if [[ "${OUTPUT_LABEL}" == "auto" ]]; then
    readarray -t CLUSTER_DIRS < <(find -L "${POSITION_DIR}/seg" -maxdepth 1 -type d -name "clustermap*" | sort -Vr)
    CLUSTER_DIR=""
    for candidate in "${CLUSTER_DIRS[@]}"; do
        if [[ -f "${candidate}/${CLEAN_CSV_NAME}" && -f "${candidate}/${PROCESSED_CSV}" ]]; then
            CLUSTER_DIR="${candidate}"
            break
        fi
    done
    if [[ -z "${CLUSTER_DIR}" ]]; then
        echo "No ClusterMap output containing ${CLEAN_CSV_NAME} and ${PROCESSED_CSV} was found for ${POSITION_NAME}." >&2
        exit 1
    fi
else
    if [[ ! "${OUTPUT_LABEL}" =~ ^[A-Za-z0-9._-]+$ || "${OUTPUT_LABEL}" == "." || "${OUTPUT_LABEL}" == ".." ]]; then
        echo "Invalid output label: ${OUTPUT_LABEL}" >&2
        exit 1
    fi
    CLUSTER_DIR="${POSITION_DIR}/seg/clustermap_${OUTPUT_LABEL}"
    if [[ ! -f "${CLUSTER_DIR}/${CLEAN_CSV_NAME}" || ! -f "${CLUSTER_DIR}/${PROCESSED_CSV}" ]]; then
        echo "Required ClusterMap inputs are missing from ${CLUSTER_DIR}." >&2
        exit 1
    fi
fi

RAW_CSV_PATH="${POSITION_DIR}/${RAW_CSV}"
PROCESSED_CSV_PATH="${CLUSTER_DIR}/${PROCESSED_CSV}"
OUTPUT_CSV_PATH="${CLUSTER_DIR}/${OUTPUT_CSV}"
RUNNER="${SCRIPT_DIR}/p21_restore_rna_suffix.py"
if [[ ! -f "${RUNNER}" || ! -f "${CONDA_SH}" ]]; then
    echo "Runner or conda initialization path validation failed." >&2
    exit 1
fi

print_slurm_info
echo "PROJECT_ROOT=${PROJECT_ROOT}"
echo "PROJECT_NAME=${PROJECT_NAME}"
echo "REGISTRATION_FOLDER=${REGISTRATION_FOLDER}"
echo "TASK_ID=${TASK_ID}"
echo "POSITION_NAME=${POSITION_NAME}"
echo "OUTPUT_LABEL=${OUTPUT_LABEL}"
echo "CLUSTER_DIR=${CLUSTER_DIR}"
echo "RAW_CSV_PATH=${RAW_CSV_PATH}"
echo "PROCESSED_CSV_PATH=${PROCESSED_CSV_PATH}"
echo "OUTPUT_CSV_PATH=${OUTPUT_CSV_PATH}"
echo "RUNNER=${RUNNER}"
echo "CONDA_SH=${CONDA_SH}"
echo "OFFSET=${OFFSET}"

source "${CONDA_SH}"
set +u
conda activate data_analysis_env
set -u

python -u "${RUNNER}" \
    --raw_csv "${RAW_CSV_PATH}" \
    --processed_csv "${PROCESSED_CSV_PATH}" \
    --output_csv "${OUTPUT_CSV_PATH}" \
    --img_c "${IMG_C}" \
    --img_r "${IMG_R}" \
    --rotation_deg "${ROTATION_DEG}" \
    --tolerance "${TOLERANCE}"

if [[ ! -f "${OUTPUT_CSV_PATH}" ]]; then
    echo "RNA suffix restore did not generate ${OUTPUT_CSV_PATH}" >&2
    exit 1
fi
