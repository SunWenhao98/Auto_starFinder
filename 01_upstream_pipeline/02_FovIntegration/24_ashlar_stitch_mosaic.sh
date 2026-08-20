#!/bin/bash
#SBATCH -J ashlar_direct_stitch
#SBATCH -o logs_ashlar_direct_stitch/%x_%A.out
#SBATCH -e logs_ashlar_direct_stitch/%x_%A.err
#SBATCH -p C64M512G
#SBATCH --qos=normal
#SBATCH -n 1
#SBATCH -c 60
#SBATCH --mem=480G
#SBATCH --time=24:00:00
#SBATCH --no-requeue
#SBATCH --export=ALL

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 24_ashlar_stitch_mosaic.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME --stitching_workdir NAME --channel_mode MODE --config_for_mosaic_stitch FILE [options]

Run direct Ashlar mosaic from semantic project paths and a mosaic stitch config.
For full explicit path control, call p24_ashlar_stitch_mosaic.py directly.

Required:
  --project_root PATH              Project root directory
  --project_name NAME              Project/sample name under project_root
  --reg_dir_suffix NAME            Registration directory name, e.g. 02_registration001_GBM008
  --stitching_workdir NAME         Work directory under registration dir
  --channel_mode MODE              LeicaIF, OlympusIF, LeicaSeqE, or *Independent mode
  --config_for_mosaic_stitch FILE  Config file name under work dir

Path/name options:
  --channel_dir_prefix PREFIX      Channel input directory prefix [raw-]
  --stitch_result_dirname NAME     Output subdirectory [stitching_results]
  --output_prefix PREFIX           Output prefix stem [stitched]

Ashlar options:
  --output_format FORMAT           preserve, uint8, or uint16 [preserve]
  --rotate_images BOOL             Rotate each FOV clockwise before stitching [false]
  --make_3d BOOL                   Write 3D stack mosaic [false]
  --pixel_size_um FLOAT            Pixel size in um/pixel [0.142]
  --slice_indices LIST             Comma-separated 1-based z slices []
  --script_dir PATH                Directory containing p24_ashlar_stitch_mosaic.py
  --conda_env NAME                 Conda environment name [ashlar]
  -h, --help                       Show this help and exit
USAGE
}

is_true() {
    case "${1,,}" in
        true|t|yes|y|1) return 0 ;;
        false|f|no|n|0|"") return 1 ;;
        *) echo "Error: expected boolean true/false, got '$1'" >&2; exit 1 ;;
    esac
}

print_slurm_info() {
    echo "============= SLURM Job Info =================="
    echo "Job ID:          ${SLURM_JOB_ID:-}"
    echo "Job Name:        ${SLURM_JOB_NAME:-}"
    echo "User:            ${SLURM_JOB_USER:-${USER:-}}"
    echo "Submit Host:     ${SLURM_SUBMIT_HOST:-}"
    echo "Submit Directory:${SLURM_SUBMIT_DIR:-}"
    echo "Node List:       ${SLURM_NODELIST:-}"
    echo "Job Node:        ${SLURMD_NODENAME:-}"
    echo "Partition:       ${SLURM_JOB_PARTITION:-}"
    echo "CPUs per task:   ${SLURM_CPUS_PER_TASK:-}"
    echo "Memory per node: ${SLURM_MEM_PER_NODE:-} MB"
    echo "==============================================="
}

resolve_channel_names() {
    case "$1" in
        LeicaIF)
            echo "561-CA9,488-CD144,647-CD31,DAPI"
            ;;
        OlympusIF)
            echo "488-CD144,561-CA9,647-CD31,DAPI"
            ;;
        LeicaSeqE)
            echo "647-GCnt,561-GTrb,Padlayer,DAPI"
            ;;
        LeicaIFIndependent)
            echo "561-CA9,488-CD144,647-CD31"
            ;;
        OlympusIFIndependent)
            echo "488-CD144,561-CA9,647-CD31"
            ;;
        LeicaSeqEIndependent)
            echo "647-GCnt,561-GTrb"
            ;;
        *)
            echo "Error: Unsupported channel_mode: $1" >&2
            echo "Supported modes: LeicaIF, OlympusIF, LeicaSeqE, LeicaIFIndependent, OlympusIFIndependent, LeicaSeqEIndependent" >&2
            exit 1
            ;;
    esac
}

DEFAULT_SCRIPT_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration"
PROJECT_ROOT=""
PROJECT_NAME=""
REG_DIR_SUFFIX=""
STITCHING_WORKDIR=""
CHANNEL_MODE=""
CONFIG_FOR_MOSAIC_STITCH=""
CHANNEL_DIR_PREFIX="raw-"
STITCH_RESULT_DIRNAME="stitching_results"
OUTPUT_PREFIX="stitched"
OUTPUT_FORMAT="preserve"
ROTATE_IMAGES="false"
MAKE_3D="false"
PIXEL_SIZE_UM="0.142"
SLICE_INDICES=""
SCRIPT_DIR="$DEFAULT_SCRIPT_DIR"
CONDA_ENV="ashlar"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --stitching_workdir) STITCHING_WORKDIR="$2"; shift 2 ;;
        --channel_mode) CHANNEL_MODE="$2"; shift 2 ;;
        --config_for_mosaic_stitch) CONFIG_FOR_MOSAIC_STITCH="$2"; shift 2 ;;
        --channel_dir_prefix) CHANNEL_DIR_PREFIX="$2"; shift 2 ;;
        --stitch_result_dirname) STITCH_RESULT_DIRNAME="$2"; shift 2 ;;
        --output_prefix) OUTPUT_PREFIX="$2"; shift 2 ;;
        --output_format) OUTPUT_FORMAT="$2"; shift 2 ;;
        --rotate_images) ROTATE_IMAGES="$2"; shift 2 ;;
        --make_3d) MAKE_3D="$2"; shift 2 ;;
        --pixel_size_um) PIXEL_SIZE_UM="$2"; shift 2 ;;
        --slice_indices) SLICE_INDICES="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_env) CONDA_ENV="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: Unknown parameter: $1" >&2; print_usage >&2; exit 1 ;;
    esac
done

[[ -n "$PROJECT_ROOT" ]] || { echo "Error: --project_root is required" >&2; exit 1; }
[[ -n "$PROJECT_NAME" ]] || { echo "Error: --project_name is required" >&2; exit 1; }
[[ -n "$REG_DIR_SUFFIX" ]] || { echo "Error: --reg_dir_suffix is required" >&2; exit 1; }
[[ -n "$STITCHING_WORKDIR" ]] || { echo "Error: --stitching_workdir is required" >&2; exit 1; }
[[ -n "$CHANNEL_MODE" ]] || { echo "Error: --channel_mode is required" >&2; exit 1; }
[[ -n "$CONFIG_FOR_MOSAIC_STITCH" ]] || { echo "Error: --config_for_mosaic_stitch is required" >&2; exit 1; }

CHANNEL_NAMES="$(resolve_channel_names "$CHANNEL_MODE")"
WORK_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/${REG_DIR_SUFFIX}/${STITCHING_WORKDIR}"
CONFIG_FILE="${WORK_DIR}/${CONFIG_FOR_MOSAIC_STITCH}"
STITCH_RESULT_DIR="${WORK_DIR}/${STITCH_RESULT_DIRNAME}"

PY_SCRIPT="${SCRIPT_DIR}/p24_ashlar_stitch_mosaic.py"
LOG_DIR="logs_ashlar_direct_stitch"

mkdir -p "$LOG_DIR"
start_time=$(date +%s)
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"
print_slurm_info

echo "Load conda environment: ${CONDA_ENV}"
source "/gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh"
set +u
conda activate "$CONDA_ENV"
set -u

echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] REG_DIR_SUFFIX=${REG_DIR_SUFFIX}"
echo "[PARAM] STITCHING_WORKDIR=${STITCHING_WORKDIR}"
echo "[PARAM] CHANNEL_MODE=${CHANNEL_MODE}"
echo "[PARAM] CHANNEL_NAMES=${CHANNEL_NAMES}"
echo "[PARAM] CONFIG_FOR_MOSAIC_STITCH=${CONFIG_FOR_MOSAIC_STITCH}"
echo "[PARAM] CHANNEL_DIR_PREFIX=${CHANNEL_DIR_PREFIX}"
echo "[PARAM] STITCH_RESULT_DIRNAME=${STITCH_RESULT_DIRNAME}"
echo "[PARAM] OUTPUT_PREFIX=${OUTPUT_PREFIX}"
echo "[PARAM] WORK_DIR=${WORK_DIR}"
echo "[PARAM] CONFIG_FILE=${CONFIG_FILE}"
echo "[PARAM] STITCH_RESULT_DIR=${STITCH_RESULT_DIR}"
echo "[PARAM] OUTPUT_FORMAT=${OUTPUT_FORMAT}"
echo "[PARAM] ROTATE_IMAGES=${ROTATE_IMAGES}"
echo "[PARAM] MAKE_3D=${MAKE_3D}"
echo "[PARAM] PIXEL_SIZE_UM=${PIXEL_SIZE_UM}"
echo "[PARAM] SLICE_INDICES=${SLICE_INDICES}"
echo "[PARAM] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PARAM] CONDA_ENV=${CONDA_ENV}"

IFS=',' read -r -a CHANNEL_ARRAY <<< "$CHANNEL_NAMES"
for CHANNEL_NAME in "${CHANNEL_ARRAY[@]}"; do
    CHANNEL_NAME="${CHANNEL_NAME//[[:space:]]/}"
    [[ -n "$CHANNEL_NAME" ]] || continue

    INPUT_DIR="${WORK_DIR}/${CHANNEL_DIR_PREFIX}${CHANNEL_NAME}"
    OUTPUT_IMAGE_PREFIX="${STITCH_RESULT_DIR}/${OUTPUT_PREFIX}_${CHANNEL_NAME}"
    echo "[CHANNEL] ${CHANNEL_NAME}"
    echo "[CHANNEL] INPUT_DIR=${INPUT_DIR}"
    echo "[CHANNEL] OUTPUT_IMAGE_PREFIX=${OUTPUT_IMAGE_PREFIX}"

    PY_ARGS=(
        --input_dir "$INPUT_DIR"
        --config_file "$CONFIG_FILE"
        --output_image_prefix "$OUTPUT_IMAGE_PREFIX"
        --output_format "$OUTPUT_FORMAT"
        --make_3d "$MAKE_3D"
        --pixel_size_um "$PIXEL_SIZE_UM"
        --slice_indices "$SLICE_INDICES"
    )

    if is_true "$ROTATE_IMAGES"; then
        PY_ARGS+=(--rotate90)
    fi

    echo "Running Ashlar direct stitch for ${CHANNEL_NAME}"
    python -u "$PY_SCRIPT" "${PY_ARGS[@]}"
done

echo "Direct stitch complete."
end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Elapsed time: $((end_time - start_time)) seconds"
