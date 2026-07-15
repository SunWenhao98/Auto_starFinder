#!/bin/bash
#SBATCH -J ashlar_initial
#SBATCH -o logs_ashlar_initial/%x_%A.out
#SBATCH -e logs_ashlar_initial/%x_%A.err
#SBATCH -p C64M512G
#SBATCH --qos=normal
#SBATCH -n 1
#SBATCH -c 60
#SBATCH --mem=128G
#SBATCH --time=24:00:00
#SBATCH --no-requeue
#SBATCH --export=ALL

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 22_ashlar_stitch_initial.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME --source_channel_dir DIR --stitching_round ROUND_DIR [options]

Run Ashlar alignment and stitching from a project-level source channel directory.
For full explicit path control, call p22_ashlar_stitch_initial.py directly.

Required:
  --project_root PATH              Project root directory
  --project_name NAME              Project/sample name under project_root
  --reg_dir_suffix NAME            Registration directory name
  --source_channel_dir DIR         Source channel directory under stitching_round, e.g. ref-DAPI or DAPI
  --stitching_round ROUND_DIR      Registration round directory, e.g. IFraw_uint8

Path name options:
  --config_name NAME               Config file name [TileConfiguration.txt]
  --registered_config_name NAME    Registered config file name [TileConfiguration.registered.txt]
  --stitch_result_dirname NAME     Output subdirectory name [stitching_results]
  --output_prefix PREFIX           Output image prefix inside output subdirectory [stitched_ref_ashlar]

Ashlar options:
  --make_3d BOOL                   Write 3D stack mosaic [false]
  --rotate90 BOOL                  Rotate each FOV clockwise before stitching [false]
  --rotate_positions BOOL          Diagnostic metadata rotation [false]
  --pixel_size_um FLOAT            Pixel size in um/pixel [0.142]
  --max_shift_px FLOAT             Maximum corrective shift in pixels [150]
  --filter_sigma FLOAT             Gaussian sigma for alignment filtering [1.0]
  --stitch_alpha FLOAT             Ashlar alpha for automatic max_error [0.01]
  --max_error VALUE                Explicit Ashlar max_error or auto [auto]
  --slice_indices LIST             Comma-separated 1-based z slices []
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

### 参数默认值 ---
PROJECT_ROOT=""
PROJECT_NAME=""
REG_DIR_SUFFIX=""
SOURCE_CHANNEL_DIR=""
STITCHING_ROUND=""
CONFIG_NAME="TileConfiguration.txt"
REGISTERED_CONFIG_NAME="TileConfiguration.registered.txt"
STITCH_RESULT_DIRNAME="stitching_results"
OUTPUT_PREFIX="stitched_ref_ashlar"
MAKE_3D="false"
ROTATE90="false"
ROTATE_POSITIONS="false"
PIXEL_SIZE_UM="0.142"
MAX_SHIFT_PX="150"
FILTER_SIGMA="1.0"
STITCH_ALPHA="0.01"
MAX_ERROR="auto"
SLICE_INDICES=""
CONDA_ENV="ashlar"

### 参数解析 ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --source_channel_dir) SOURCE_CHANNEL_DIR="$2"; shift 2 ;;
        --stitching_round) STITCHING_ROUND="$2"; shift 2 ;;
        --config_name) CONFIG_NAME="$2"; shift 2 ;;
        --registered_config_name) REGISTERED_CONFIG_NAME="$2"; shift 2 ;;
        --stitch_result_dirname) STITCH_RESULT_DIRNAME="$2"; shift 2 ;;
        --output_prefix) OUTPUT_PREFIX="$2"; shift 2 ;;
        --make_3d) MAKE_3D="$2"; shift 2 ;;
        --rotate90) ROTATE90="$2"; shift 2 ;;
        --rotate_positions) ROTATE_POSITIONS="$2"; shift 2 ;;
        --pixel_size_um) PIXEL_SIZE_UM="$2"; shift 2 ;;
        --max_shift_px) MAX_SHIFT_PX="$2"; shift 2 ;;
        --filter_sigma) FILTER_SIGMA="$2"; shift 2 ;;
        --stitch_alpha) STITCH_ALPHA="$2"; shift 2 ;;
        --max_error) MAX_ERROR="$2"; shift 2 ;;
        --slice_indices) SLICE_INDICES="$2"; shift 2 ;;
        --conda_env) CONDA_ENV="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: Unknown parameter: $1" >&2; print_usage >&2; exit 1 ;;
    esac
done

### 必填检查与路径推导 ---
[[ -n "$PROJECT_ROOT" ]] || { echo "Error: --project_root is required" >&2; exit 1; }
[[ -n "$PROJECT_NAME" ]] || { echo "Error: --project_name is required" >&2; exit 1; }
[[ -n "$REG_DIR_SUFFIX" ]] || { echo "Error: --reg_dir_suffix is required" >&2; exit 1; }
[[ -n "$SOURCE_CHANNEL_DIR" ]] || { echo "Error: --source_channel_dir is required" >&2; exit 1; }
[[ -n "$STITCHING_ROUND" ]] || { echo "Error: --stitching_round is required" >&2; exit 1; }

INPUT_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/${REG_DIR_SUFFIX}/${STITCHING_ROUND}/${SOURCE_CHANNEL_DIR}"
WORK_DIR="$(dirname "$INPUT_DIR")"
CONFIG_FILE="${WORK_DIR}/${CONFIG_NAME}"
REGISTERED_CONFIG_FILE="${WORK_DIR}/${REGISTERED_CONFIG_NAME}"
OUTPUT_IMAGE_PREFIX="${WORK_DIR}/${STITCH_RESULT_DIRNAME}/${OUTPUT_PREFIX}"

### 环境准备 ---
PY_SCRIPT="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration/p22_ashlar_stitch_initial.py"
LOG_DIR="logs_ashlar_initial"

mkdir -p "$LOG_DIR"
start_time=$(date +%s)
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"
print_slurm_info

### 参数打印 ---
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] REG_DIR_SUFFIX=${REG_DIR_SUFFIX}"
echo "[PARAM] SOURCE_CHANNEL_DIR=${SOURCE_CHANNEL_DIR}"
echo "[PARAM] STITCHING_ROUND=${STITCHING_ROUND}"
echo "[PARAM] CONFIG_NAME=${CONFIG_NAME}"
echo "[PARAM] REGISTERED_CONFIG_NAME=${REGISTERED_CONFIG_NAME}"
echo "[PARAM] STITCH_RESULT_DIRNAME=${STITCH_RESULT_DIRNAME}"
echo "[PARAM] OUTPUT_PREFIX=${OUTPUT_PREFIX}"
echo "[PARAM] INPUT_DIR=${INPUT_DIR}"
echo "[PARAM] CONFIG_FILE=${CONFIG_FILE}"
echo "[PARAM] OUTPUT_IMAGE_PREFIX=${OUTPUT_IMAGE_PREFIX}"
echo "[PARAM] REGISTERED_CONFIG_FILE=${REGISTERED_CONFIG_FILE}"
echo "[PARAM] MAKE_3D=${MAKE_3D}"
echo "[PARAM] ROTATE90=${ROTATE90}"
echo "[PARAM] ROTATE_POSITIONS=${ROTATE_POSITIONS}"
echo "[PARAM] PIXEL_SIZE_UM=${PIXEL_SIZE_UM}"
echo "[PARAM] MAX_SHIFT_PX=${MAX_SHIFT_PX}"
echo "[PARAM] FILTER_SIGMA=${FILTER_SIGMA}"
echo "[PARAM] STITCH_ALPHA=${STITCH_ALPHA}"
echo "[PARAM] MAX_ERROR=${MAX_ERROR}"
echo "[PARAM] SLICE_INDICES=${SLICE_INDICES}"
echo "[PARAM] CONDA_ENV=${CONDA_ENV}"

echo "Load conda environment: ${CONDA_ENV}"
source "/gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh"
set +u
conda activate "$CONDA_ENV"
set -u

### 执行 Python ---
PY_ARGS=(
    --input_dir "$INPUT_DIR"
    --config_file "$CONFIG_FILE"
    --output_image_prefix "$OUTPUT_IMAGE_PREFIX"
    --registered_config_file "$REGISTERED_CONFIG_FILE"
    --make_3d "$MAKE_3D"
    --pixel_size_um "$PIXEL_SIZE_UM"
    --max_shift_px "$MAX_SHIFT_PX"
    --filter_sigma "$FILTER_SIGMA"
    --stitch_alpha "$STITCH_ALPHA"
    --max_error "$MAX_ERROR"
    --slice_indices "$SLICE_INDICES"
)

if is_true "$ROTATE90"; then
    PY_ARGS+=(--rotate90)
fi
if is_true "$ROTATE_POSITIONS"; then
    PY_ARGS+=(--rotate_positions)
fi

echo "Running Ashlar stitching"
python -u "$PY_SCRIPT" "${PY_ARGS[@]}"

echo "Ashlar processing complete."
end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Elapsed time: $((end_time - start_time)) seconds"
