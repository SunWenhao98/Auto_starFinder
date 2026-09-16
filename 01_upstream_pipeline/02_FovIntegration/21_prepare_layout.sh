#!/bin/bash
#SBATCH -J prepare_noRef_layout
#SBATCH -o logs021_prepare_layout/%x_%A.out
#SBATCH -e logs021_prepare_layout/%x_%A.err
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 4
#SBATCH --time=04:00:00

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 21_prepare_layout.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME [options]

Options:
  --rawdata_round NAME
  --stitching_workdir NAME
  --channel_mode MODE
  --output_format FORMAT
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
RAWDATA_ROUND="IF"
STITCHING_WORKDIR="IFindep"
CHANNEL_MODE="LeicaIF"
OUTPUT_FORMAT="preserve"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --rawdata_round) RAWDATA_ROUND="$2"; shift 2 ;;
        --stitching_workdir) STITCHING_WORKDIR="$2"; shift 2 ;;
        --channel_mode) CHANNEL_MODE="$2"; shift 2 ;;
        --output_format) OUTPUT_FORMAT="$2"; shift 2 ;;
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

for value in PROJECT_ROOT PROJECT_NAME REG_DIR_SUFFIX SCRIPT_DIR CONDA_SH; do
    [[ -n "${!value}" ]] || { echo "Error: ${value} is required" >&2; exit 1; }
done

RAW_ROUND_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/${RAWDATA_ROUND}"
REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REG_ROOT="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
OUTPUT_DIR="${REG_ROOT}/${STITCHING_WORKDIR}"
MANIFEST_FILE="${OUTPUT_DIR}/channel_manifest_${RAWDATA_ROUND}_${OUTPUT_FORMAT}.csv"
case "$CHANNEL_MODE" in
    LeicaIF) CHANNELS="ch00=raw-561-CA9,ch01=raw-488-CD144,ch02=raw-647-CD31,ch03=raw-DAPI" ;;
    OlympusIF) CHANNELS="ch00=raw-488-CD144,ch01=raw-561-CA9,ch02=raw-647-CD31,ch03=raw-DAPI" ;;
    LeicaSeqE) CHANNELS="ch00=raw-647-GCnt,ch01=raw-561-GTrb,ch02=raw-Padlayer,ch03=raw-DAPI" ;;
    LeicaRef) CHANNELS="ch00=raw-561,ch01=raw-488,ch02=raw-647,ch03=raw-refDAPI" ;;
    *) echo "Error: unsupported --channel_mode: $CHANNEL_MODE" >&2; exit 1 ;;
esac

print_slurm_info
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] RAWDATA_ROUND=${RAWDATA_ROUND}"
echo "[PARAM] STITCHING_WORKDIR=${STITCHING_WORKDIR}"
echo "[PARAM] CHANNEL_MODE=${CHANNEL_MODE}"
echo "[PARAM] CHANNELS=${CHANNELS}"
echo "[PARAM] OUTPUT_FORMAT=${OUTPUT_FORMAT}"

PY_SCRIPT="${SCRIPT_DIR}/p21_prepare_noRef_layout.py"

echo "[PATH] REG_ROOT=${REG_ROOT}"
echo "[PATH] RAW_ROUND_DIR=${RAW_ROUND_DIR}"
echo "[PATH] OUTPUT_DIR=${OUTPUT_DIR}"
echo "[PATH] MANIFEST_FILE=${MANIFEST_FILE}"
echo "[PATH] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PATH] CONDA_SH=${CONDA_SH}"
echo "[PATH] PY_SCRIPT=${PY_SCRIPT}"

[[ -d "$RAW_ROUND_DIR" ]] || { echo "Error: raw round directory not found: $RAW_ROUND_DIR" >&2; exit 1; }
[[ -f "$PY_SCRIPT" ]] || { echo "Error: runner not found: $PY_SCRIPT" >&2; exit 1; }
[[ -f "$CONDA_SH" ]] || { echo "Error: conda initialization script not found: $CONDA_SH" >&2; exit 1; }

source "$CONDA_SH"
set +u
conda activate ashlar
set -u
python -u "$PY_SCRIPT" \
    --raw_round_dir "$RAW_ROUND_DIR" \
    --output_dir "$OUTPUT_DIR" \
    --channels "$CHANNELS" \
    --manifest_path "$MANIFEST_FILE" \
    --output_format "$OUTPUT_FORMAT"

[[ -s "$MANIFEST_FILE" ]] || { echo "Error: layout manifest missing or empty: $MANIFEST_FILE" >&2; exit 1; }
