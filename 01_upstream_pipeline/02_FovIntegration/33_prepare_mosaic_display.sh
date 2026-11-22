#!/bin/bash
#SBATCH -J mosaic_display
#SBATCH -o logs033_mosaic_display/%x_%A.out
#SBATCH -e logs033_mosaic_display/%x_%A.err
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 8
#SBATCH --time=08:00:00

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 33_prepare_mosaic_display.sh --project_root PATH --project_name NAME
    --reg_dir_suffix SUFFIX --stitching_workdir NAME --input_manifest NAME
    --display_profile NAME --output_dirname NAME --script_dir PATH --conda_sh PATH
    [--subtract_background BOOL] [--apply_display_mapping BOOL]

Manifest, profile and new output directory are relative to the stitching workdir.
The input images must already be in the same coordinate frame for each plane.
USAGE
}

finish() {
    local exit_code=$?
    local end_time
    local status="SUCCESS"
    end_time=$(date +%s)
    if (( exit_code != 0 )); then
        status="FAILED"
    fi
    echo "结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "运行时间: $((end_time - START_TIME)) seconds"
    echo "STATUS: ${status} | SLURM_JOB_NAME=${SLURM_JOB_NAME:-N/A}"
}

PROJECT_ROOT=""
PROJECT_NAME=""
REG_DIR_SUFFIX=""
STITCHING_WORKDIR=""
INPUT_MANIFEST=""
DISPLAY_PROFILE=""
OUTPUT_DIRNAME="display_review"
SUBTRACT_BACKGROUND="false"
APPLY_DISPLAY_MAPPING="false"
SCRIPT_DIR=""
CONDA_SH=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --stitching_workdir) STITCHING_WORKDIR="$2"; shift 2 ;;
        --input_manifest) INPUT_MANIFEST="$2"; shift 2 ;;
        --display_profile) DISPLAY_PROFILE="$2"; shift 2 ;;
        --output_dirname) OUTPUT_DIRNAME="$2"; shift 2 ;;
        --subtract_background) SUBTRACT_BACKGROUND="$2"; shift 2 ;;
        --apply_display_mapping) APPLY_DISPLAY_MAPPING="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: unknown parameter: $1" >&2; print_usage >&2; exit 1 ;;
    esac
done

START_TIME=$(date +%s)
trap finish EXIT
WORK_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/02_registration${REG_DIR_SUFFIX}/${STITCHING_WORKDIR}"
MANIFEST_FILE="${WORK_DIR}/${INPUT_MANIFEST}"
PROFILE_FILE="${WORK_DIR}/${DISPLAY_PROFILE}"
OUTPUT_DIR="${WORK_DIR}/${OUTPUT_DIRNAME}"
RUNNER="${SCRIPT_DIR}/p33_prepare_mosaic_display.py"

OPTIONS=()
if [[ "${SUBTRACT_BACKGROUND,,}" == "true" ]]; then
    OPTIONS+=(--subtract_background)
fi
if [[ "${APPLY_DISPLAY_MAPPING,,}" == "true" ]]; then
    OPTIONS+=(--apply_display_mapping)
fi

echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Job ID:                ${SLURM_JOB_ID:-N/A}"
echo "Node:                  ${SLURMD_NODENAME:-N/A}"
echo "CPUs per task:         ${SLURM_CPUS_PER_TASK:-N/A}"
echo "Memory per CPU (MB):   ${SLURM_MEM_PER_CPU:-N/A}"
echo "Stitching workdir:     ${WORK_DIR}"
echo "Input manifest:        ${MANIFEST_FILE}"
echo "Display profile:       ${PROFILE_FILE}"
echo "Output directory:      ${OUTPUT_DIR}"
echo "Subtract background:   ${SUBTRACT_BACKGROUND}"
echo "Apply display mapping: ${APPLY_DISPLAY_MAPPING}"
echo "Runner:                ${RUNNER}"
echo "Environment:           ashlar (${CONDA_SH})"

source "$CONDA_SH"
set +u
conda activate ashlar
set -u

python -u "$RUNNER" \
    --input_manifest "$MANIFEST_FILE" \
    --display_profile "$PROFILE_FILE" \
    --output_dir "$OUTPUT_DIR" \
    "${OPTIONS[@]}"

if [[ ! -s "${OUTPUT_DIR}/display_presets.json" ]]; then
    echo "Error: missing display presets: ${OUTPUT_DIR}/display_presets.json" >&2
    exit 1
fi
