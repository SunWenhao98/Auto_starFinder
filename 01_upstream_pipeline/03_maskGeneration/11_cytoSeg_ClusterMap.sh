#!/bin/bash
#SBATCH -J clustermap_seg
#SBATCH -o logs011_clustermap/%x_%A_%a.out
#SBATCH -e logs011_clustermap/%x_%A_%a.err
#SBATCH -p C64M512G
#SBATCH -N 1
#SBATCH -c 60
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
CELL_NUM_THRESHOLD="0.1"
DAPI_GRID_INTERVAL="4"
CELL_RADIUS="40,15"
PCT_FILTER="0.01"
ROTATION="90"
EXTRA_PREPROCESS="F"
SUB_SPAN="400"
EXPECTED_WORKERS="1"
READS_FILTER="5"
OVERLAP_PERCENT="0.2"
DAPI_SUFFIX="ch03.tif"
SPOT_CSV_NAME="goodPoints_max3d_0.2_tri.csv"
OUTPUT_LABEL="auto"
OFFSET="0"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --ref_round) REF_ROUND="$2"; shift 2 ;;
        --cell_num_threshold) CELL_NUM_THRESHOLD="$2"; shift 2 ;;
        --dapi_grid_interval) DAPI_GRID_INTERVAL="$2"; shift 2 ;;
        --cell_radius) CELL_RADIUS="$2"; shift 2 ;;
        --pct_filter) PCT_FILTER="$2"; shift 2 ;;
        --rotation) ROTATION="$2"; shift 2 ;;
        --extra_preprocess) EXTRA_PREPROCESS="$2"; shift 2 ;;
        --sub_span) SUB_SPAN="$2"; shift 2 ;;
        --expected_workers) EXPECTED_WORKERS="$2"; shift 2 ;;
        --reads_filter) READS_FILTER="$2"; shift 2 ;;
        --overlap_percent) OVERLAP_PERCENT="$2"; shift 2 ;;
        --dapi_suffix) DAPI_SUFFIX="$2"; shift 2 ;;
        --spot_csv_name) SPOT_CSV_NAME="$2"; shift 2 ;;
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
printf -v ROUND_DIR "round%03d" "$((10#${REF_ROUND}))"
REFERENCE_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/${ROUND_DIR}"
readarray -t DAPI_FILES < <(find -L "${REFERENCE_DIR}" -maxdepth 2 -type f -name "*${DAPI_SUFFIX}" | sort -V)
if (( POSITION_INDEX < 0 || POSITION_INDEX >= ${#DAPI_FILES[@]} )); then
    echo "Task ID ${TASK_ID} is outside the available DAPI file range." >&2
    exit 1
fi

DAPI_FILE="${DAPI_FILES[POSITION_INDEX]}"
POSITION_NAME=$(basename "$(dirname "${DAPI_FILE}")")
REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
POSITION_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}/${POSITION_NAME}"
TRANSCRIPTS_RAW="${POSITION_DIR}/${SPOT_CSV_NAME}"
if [[ "${OUTPUT_LABEL}" == "auto" ]]; then
    OUTPUT_DIR="${POSITION_DIR}/seg/clustermap_$(date +%Y%m%d_%H%M%S)_${SLURM_JOB_ID}"
else
    if [[ ! "${OUTPUT_LABEL}" =~ ^[A-Za-z0-9._-]+$ || "${OUTPUT_LABEL}" == "." || "${OUTPUT_LABEL}" == ".." ]]; then
        echo "Invalid output label: ${OUTPUT_LABEL}" >&2
        exit 1
    fi
    OUTPUT_DIR="${POSITION_DIR}/seg/clustermap_${OUTPUT_LABEL}"
    if [[ -e "${OUTPUT_DIR}" || -L "${OUTPUT_DIR}" ]]; then
        echo "ClusterMap output target already exists: ${OUTPUT_DIR}" >&2
        exit 1
    fi
fi
TRANSCRIPTS_CLEAN="${OUTPUT_DIR}/${SPOT_CSV_NAME%.*}_clean_genes.csv"
RUNNER="${SCRIPT_DIR}/run_clustermap_v2.py"
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
echo "DAPI_FILE=${DAPI_FILE}"
echo "TRANSCRIPTS_RAW=${TRANSCRIPTS_RAW}"
echo "TRANSCRIPTS_CLEAN=${TRANSCRIPTS_CLEAN}"
echo "OUTPUT_LABEL=${OUTPUT_LABEL}"
echo "OUTPUT_DIR=${OUTPUT_DIR}"
echo "RUNNER=${RUNNER}"
echo "CONDA_SH=${CONDA_SH}"
echo "OFFSET=${OFFSET}"

source "${CONDA_SH}"
set +u
conda activate ClusterMap
set -u

mkdir -p "${OUTPUT_DIR}"
sed -e 's/_rbRNA//g' -e 's/_ntRNA//g' "${TRANSCRIPTS_RAW}" > "${TRANSCRIPTS_CLEAN}"

python -u "${RUNNER}" \
    --dapi_path "${DAPI_FILE}" \
    --transcripts_file "${TRANSCRIPTS_CLEAN}" \
    --output_path "${OUTPUT_DIR}" \
    --cell_num_threshold "${CELL_NUM_THRESHOLD}" \
    --dapi_grid_interval "${DAPI_GRID_INTERVAL}" \
    --cell_radius "${CELL_RADIUS}" \
    --pct_filter "${PCT_FILTER}" \
    --ref_round "${REF_ROUND}" \
    --extra_preprocess "${EXTRA_PREPROCESS}" \
    --rotation "${ROTATION}" \
    --sub_span "${SUB_SPAN}" \
    --expected_workers "${EXPECTED_WORKERS}" \
    --reads_filter "${READS_FILTER}" \
    --overlap_percent "${OVERLAP_PERCENT}"

if [[ ! -f "${OUTPUT_DIR}/cell_center.csv" ]]; then
    echo "ClusterMap did not generate ${OUTPUT_DIR}/cell_center.csv" >&2
    exit 1
fi
