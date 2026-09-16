#!/bin/bash
#SBATCH -J prepare_moveimages
#SBATCH -o logs023_prepare_moveimages/%x_%A.out
#SBATCH -e logs023_prepare_moveimages/%x_%A.err
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 4
#SBATCH --time=04:00:00

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 23_prepare_moveImages_tileconfig.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME --stitching_workdir NAME --rawdata_round NAME --channel_mode MODE --input_config NAME --output_config NAME [options]

Options:
  --output_format FORMAT
  --rotate_shifts BOOL
  --shift_sign FLOAT
  --script_dir PATH
  --conda_sh PATH
  -h, --help
USAGE
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
STITCHING_WORKDIR=""
RAWDATA_ROUND=""
CHANNEL_MODE=""
INPUT_CONFIG=""
OUTPUT_CONFIG=""
OUTPUT_FORMAT="preserve"
ROTATE_SHIFTS="false"
SHIFT_SIGN="1.0"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --stitching_workdir) STITCHING_WORKDIR="$2"; shift 2 ;;
        --rawdata_round) RAWDATA_ROUND="$2"; shift 2 ;;
        --channel_mode) CHANNEL_MODE="$2"; shift 2 ;;
        --input_config) INPUT_CONFIG="$2"; shift 2 ;;
        --output_config) OUTPUT_CONFIG="$2"; shift 2 ;;
        --output_format) OUTPUT_FORMAT="$2"; shift 2 ;;
        --rotate_shifts) ROTATE_SHIFTS="$2"; shift 2 ;;
        --shift_sign) SHIFT_SIGN="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: unknown parameter: $1" >&2; print_usage >&2; exit 1 ;;
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

for value in PROJECT_ROOT PROJECT_NAME REG_DIR_SUFFIX SCRIPT_DIR CONDA_SH STITCHING_WORKDIR RAWDATA_ROUND CHANNEL_MODE INPUT_CONFIG OUTPUT_CONFIG; do
    [[ -n "${!value}" ]] || { echo "Error: ${value} is required" >&2; exit 1; }
done
REGISTRATION_TARGET_TAG="${STITCHING_WORKDIR//[^A-Za-z0-9_.-]/_}"
REGISTRATION_LOG_NAME="log_protein_registration_${REGISTRATION_TARGET_TAG}.txt"

case "$CHANNEL_MODE" in
    LeicaIF) CHANNEL_NAMES="561-CA9,488-CD144,647-CD31,DAPI" ;;
    OlympusIF) CHANNEL_NAMES="488-CD144,561-CA9,647-CD31,DAPI" ;;
    LeicaSeqE) CHANNEL_NAMES="647-GCnt,561-GTrb,Padlayer,DAPI" ;;
    *) echo "Error: unsupported --channel_mode: $CHANNEL_MODE" >&2; exit 1 ;;
esac
REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REG_ROOT="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
WORK_DIR="${REG_ROOT}/${STITCHING_WORKDIR}"
RAW_ROUND_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/${RAWDATA_ROUND}"
REGISTRATION_DIR="$REG_ROOT"
INPUT_CONFIG_FILE="${WORK_DIR}/${INPUT_CONFIG}"
OUTPUT_CONFIG_FILE="${WORK_DIR}/${OUTPUT_CONFIG}"
SHIFT_CSV_FILE="${WORK_DIR}/if_registration_shifts.csv"

print_slurm_info
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] STITCHING_WORKDIR=${STITCHING_WORKDIR}"
echo "[PARAM] RAWDATA_ROUND=${RAWDATA_ROUND}"
echo "[PARAM] CHANNEL_MODE=${CHANNEL_MODE}"
echo "[PARAM] CHANNEL_NAMES=${CHANNEL_NAMES}"
echo "[PARAM] INPUT_CONFIG=${INPUT_CONFIG}"
echo "[PARAM] OUTPUT_CONFIG=${OUTPUT_CONFIG}"
echo "[PARAM] REGISTRATION_LOG_NAME=${REGISTRATION_LOG_NAME}"
echo "[PARAM] OUTPUT_FORMAT=${OUTPUT_FORMAT}"
echo "[PARAM] ROTATE_SHIFTS=${ROTATE_SHIFTS}"
echo "[PARAM] SHIFT_SIGN=${SHIFT_SIGN}"

PY_SCRIPT="${SCRIPT_DIR}/p23_prepare_moveImages_tileconfig.py"
PY_ARGS=(
    --work_dir "$WORK_DIR"
    --raw_round_dir "$RAW_ROUND_DIR"
    --registration_dir "$REGISTRATION_DIR"
    --registered_config "$INPUT_CONFIG_FILE"
    --shifted_config_name "$OUTPUT_CONFIG"
    --registration_log_name "$REGISTRATION_LOG_NAME"
    --channel_names "$CHANNEL_NAMES"
    --output_format "$OUTPUT_FORMAT"
    --shift_sign "$SHIFT_SIGN"
)
if [[ "$ROTATE_SHIFTS" == "true" ]]; then
    PY_ARGS+=(--rotate90)
fi

echo "[PATH] REG_ROOT=${REG_ROOT}"
echo "[PATH] WORK_DIR=${WORK_DIR}"
echo "[PATH] RAW_ROUND_DIR=${RAW_ROUND_DIR}"
echo "[PATH] INPUT_CONFIG_FILE=${INPUT_CONFIG_FILE}"
echo "[PATH] OUTPUT_CONFIG_FILE=${OUTPUT_CONFIG_FILE}"
echo "[PATH] SHIFT_CSV_FILE=${SHIFT_CSV_FILE}"
echo "[PATH] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PATH] CONDA_SH=${CONDA_SH}"
echo "[PATH] PY_SCRIPT=${PY_SCRIPT}"
for path in "$RAW_ROUND_DIR" "$INPUT_CONFIG_FILE" "$CONDA_SH" "$PY_SCRIPT"; do
    [[ -e "$path" ]] || { echo "Error: missing input: $path" >&2; exit 1; }
done

source "$CONDA_SH"
set +u
conda activate ashlar
set -u
python -u "$PY_SCRIPT" "${PY_ARGS[@]}"
[[ -s "$OUTPUT_CONFIG_FILE" ]] || { echo "Error: shifted config missing or empty: $OUTPUT_CONFIG_FILE" >&2; exit 1; }
[[ -s "$SHIFT_CSV_FILE" ]] || { echo "Error: registration shift table missing or empty: $SHIFT_CSV_FILE" >&2; exit 1; }
