#!/bin/bash
#SBATCH -J prepare_layout
#SBATCH -o logs011b_prepare_layout/%x_%A.out
#SBATCH -e logs011b_prepare_layout/%x_%A.err
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 4
#SBATCH --time=04:00:00

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 11b_prepare_layout.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME [options]

Options:
  --rawdata_round NAME       Single input round (default IF)
  --stitching_workdir NAME   Method root below the registration directory
  --channel_mode MODE        LeicaRef, LeicaIF, OlympusIF or LeicaSeqE
  --layout_mode MODE         symlink (default) or copy
  --output_format FORMAT     preserve (default), uint8 or uint16
  --round_manifest PATH      Optional CSV with role,rawdata_round,channel_mode,subdir
  --script_dir PATH
  --conda_sh PATH
  -h, --help

LeicaRef prepares ch03 only. Symlinks preserve the original pixels and bit depth.
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
LAYOUT_MODE="symlink"
OUTPUT_FORMAT="preserve"
ROUND_MANIFEST=""

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
        --layout_mode) LAYOUT_MODE="$2"; shift 2 ;;
        --output_format) OUTPUT_FORMAT="$2"; shift 2 ;;
        --round_manifest) ROUND_MANIFEST="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: unknown parameter: $1" >&2; print_usage >&2; exit 1 ;;
    esac
done

START_TIME=$(date +%s)
START_TIME_TEXT=$(date '+%Y-%m-%d %H:%M:%S')

finish() {
    local exit_code=$?
    local end_time
    local status
    end_time=$(date +%s)
    if (( exit_code == 0 )); then
        status="SUCCESS"
    else
        status="FAILED"
    fi
    echo "开始时间: ${START_TIME_TEXT}"
    echo "结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "运行时间: $((end_time - START_TIME)) seconds"
    echo "STATUS: ${status} | SLURM_JOB_NAME=${SLURM_JOB_NAME:-N/A}"
}
trap finish EXIT

REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REG_ROOT="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
WORK_DIR="${REG_ROOT}/${STITCHING_WORKDIR}"
# Links below the registration root can redirect layout writes into source data.
IFS='/' read -r -a LAYOUT_COMPONENTS <<< "$STITCHING_WORKDIR"
LAYOUT_PATH="$REG_ROOT"
for LAYOUT_COMPONENT in "${LAYOUT_COMPONENTS[@]}"; do
    LAYOUT_PATH="${LAYOUT_PATH}/${LAYOUT_COMPONENT}"
    if [[ -L "$LAYOUT_PATH" ]]; then
        echo "Error: method layout path is a symlink: $LAYOUT_PATH" >&2
        exit 1
    fi
done
PY_SCRIPT="${SCRIPT_DIR}/p11b_prepare_layout.py"

prepare_round_layout() {
    case "$CHANNEL_MODE" in
        LeicaIF) CHANNELS="ch00=raw-561-CA9,ch01=raw-488-CD144,ch02=raw-647-CD31,ch03=raw-DAPI" ;;
        OlympusIF) CHANNELS="ch00=raw-488-CD144,ch01=raw-561-CA9,ch02=raw-647-CD31,ch03=raw-DAPI" ;;
        LeicaSeqE) CHANNELS="ch00=raw-647-GCnt,ch01=raw-561-GTrb,ch03=raw-DAPI" ;;
        LeicaRef) CHANNELS="ch03=raw-refDAPI" ;;
        *) echo "Error: unsupported --channel_mode: $CHANNEL_MODE" >&2; exit 1 ;;
    esac
    RAW_ROUND_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/${RAWDATA_ROUND}"
    OUTPUT_DIR="$WORK_DIR"
    if [[ -n "$ROUND_SUBDIR" ]]; then
        OUTPUT_DIR="${WORK_DIR}/${ROUND_SUBDIR}"
    fi
    MANIFEST_FILE="${OUTPUT_DIR}/channel_manifest_${RAWDATA_ROUND}_${OUTPUT_FORMAT}.csv"

    echo "[PARAM] ROUND_ROLE=${ROUND_ROLE}"
    echo "[PARAM] RAWDATA_ROUND=${RAWDATA_ROUND}"
    echo "[PARAM] CHANNEL_MODE=${CHANNEL_MODE}"
    echo "[PARAM] CHANNELS=${CHANNELS}"
    echo "[PATH] RAW_ROUND_DIR=${RAW_ROUND_DIR}"
    echo "[PATH] OUTPUT_DIR=${OUTPUT_DIR}"
    echo "[PATH] MANIFEST_FILE=${MANIFEST_FILE}"
    python -u "$PY_SCRIPT" \
        --raw_round_dir "$RAW_ROUND_DIR" \
        --output_dir "$OUTPUT_DIR" \
        --channels "$CHANNELS" \
        --manifest_path "$MANIFEST_FILE" \
        --layout_mode "$LAYOUT_MODE" \
        --output_format "$OUTPUT_FORMAT"
    [[ -s "$MANIFEST_FILE" ]] || { echo "Error: layout manifest missing or empty: $MANIFEST_FILE" >&2; exit 1; }
}

print_slurm_info
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] STITCHING_WORKDIR=${STITCHING_WORKDIR}"
echo "[PARAM] LAYOUT_MODE=${LAYOUT_MODE}"
echo "[PARAM] OUTPUT_FORMAT=${OUTPUT_FORMAT}"
echo "[PATH] REG_ROOT=${REG_ROOT}"
echo "[PATH] WORK_DIR=${WORK_DIR}"
echo "[PATH] ROUND_MANIFEST=${ROUND_MANIFEST}"
echo "[PATH] PY_SCRIPT=${PY_SCRIPT}"
echo "[PATH] CONDA_SH=${CONDA_SH}"

source "$CONDA_SH"
set +u
conda activate ashlar
set -u

if [[ -n "$ROUND_MANIFEST" ]]; then
    ROUND_SPECS=$(python - "$ROUND_MANIFEST" <<'PY'
import csv
import sys

with open(sys.argv[1], newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
        print("\t".join(row[key] for key in ("role", "rawdata_round", "channel_mode", "subdir")))
PY
    )
    while IFS=$'\t' read -r ROUND_ROLE RAWDATA_ROUND CHANNEL_MODE ROUND_SUBDIR; do
        prepare_round_layout
    done <<< "$ROUND_SPECS"
else
    ROUND_ROLE="$RAWDATA_ROUND"
    ROUND_SUBDIR=""
    prepare_round_layout
fi
