#!/bin/bash
#SBATCH -J ashlar_stitch_initial
#SBATCH -o logs022_ashlar_stitch_initial/%x_%A.out
#SBATCH -e logs022_ashlar_stitch_initial/%x_%A.err
#SBATCH -p C64M512G
#SBATCH -N 1
#SBATCH -c 60
#SBATCH --time=24:00:00

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 22_ashlar_stitch_initial.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME --stitching_workdir NAME --source_channel_dir DIR --input_config NAME --output_config NAME [options]

Options:
  --stitch_result_dirname NAME
  --output_prefix PREFIX
  --make_3d BOOL
  --rotate90 BOOL
  --rotate_positions BOOL
  --pixel_size_um FLOAT
  --max_shift_px FLOAT
  --filter_sigma FLOAT
  --stitch_alpha FLOAT
  --max_error VALUE
  --slice_indices LIST
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
SOURCE_CHANNEL_DIR=""
INPUT_CONFIG=""
OUTPUT_CONFIG=""
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

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --stitching_workdir) STITCHING_WORKDIR="$2"; shift 2 ;;
        --source_channel_dir) SOURCE_CHANNEL_DIR="$2"; shift 2 ;;
        --input_config) INPUT_CONFIG="$2"; shift 2 ;;
        --output_config) OUTPUT_CONFIG="$2"; shift 2 ;;
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

for value in PROJECT_ROOT PROJECT_NAME REG_DIR_SUFFIX SCRIPT_DIR CONDA_SH STITCHING_WORKDIR SOURCE_CHANNEL_DIR INPUT_CONFIG OUTPUT_CONFIG; do
    [[ -n "${!value}" ]] || { echo "Error: ${value} is required" >&2; exit 1; }
done
REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REG_ROOT="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
WORK_DIR="${REG_ROOT}/${STITCHING_WORKDIR}"
INPUT_DIR="${WORK_DIR}/${SOURCE_CHANNEL_DIR}"
INPUT_CONFIG_FILE="${WORK_DIR}/${INPUT_CONFIG}"
OUTPUT_CONFIG_FILE="${WORK_DIR}/${OUTPUT_CONFIG}"
OUTPUT_IMAGE_PREFIX="${WORK_DIR}/${STITCH_RESULT_DIRNAME}/${OUTPUT_PREFIX}"
OUTPUT_2D_FILE="${OUTPUT_IMAGE_PREFIX}_2d.ome.tif"

print_slurm_info
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] STITCHING_WORKDIR=${STITCHING_WORKDIR}"
echo "[PARAM] SOURCE_CHANNEL_DIR=${SOURCE_CHANNEL_DIR}"
echo "[PARAM] INPUT_CONFIG=${INPUT_CONFIG}"
echo "[PARAM] OUTPUT_CONFIG=${OUTPUT_CONFIG}"
echo "[PARAM] STITCH_RESULT_DIRNAME=${STITCH_RESULT_DIRNAME}"
echo "[PARAM] OUTPUT_PREFIX=${OUTPUT_PREFIX}"
echo "[PARAM] MAKE_3D=${MAKE_3D}"
echo "[PARAM] ROTATE90=${ROTATE90}"
echo "[PARAM] ROTATE_POSITIONS=${ROTATE_POSITIONS}"
echo "[PARAM] PIXEL_SIZE_UM=${PIXEL_SIZE_UM}"
echo "[PARAM] MAX_SHIFT_PX=${MAX_SHIFT_PX}"
echo "[PARAM] FILTER_SIGMA=${FILTER_SIGMA}"
echo "[PARAM] STITCH_ALPHA=${STITCH_ALPHA}"
echo "[PARAM] MAX_ERROR=${MAX_ERROR}"
echo "[PARAM] SLICE_INDICES=${SLICE_INDICES}"

PY_SCRIPT="${SCRIPT_DIR}/p22_ashlar_stitch_initial.py"
PY_ARGS=(
    --input_dir "$INPUT_DIR"
    --config_file "$INPUT_CONFIG_FILE"
    --output_image_prefix "$OUTPUT_IMAGE_PREFIX"
    --registered_config_file "$OUTPUT_CONFIG_FILE"
    --make_3d "$MAKE_3D"
    --pixel_size_um "$PIXEL_SIZE_UM"
    --max_shift_px "$MAX_SHIFT_PX"
    --filter_sigma "$FILTER_SIGMA"
    --stitch_alpha "$STITCH_ALPHA"
    --max_error "$MAX_ERROR"
    --slice_indices "$SLICE_INDICES"
)
if [[ "$ROTATE90" == "true" ]]; then
    PY_ARGS+=(--rotate90)
fi
if [[ "$ROTATE_POSITIONS" == "true" ]]; then
    PY_ARGS+=(--rotate_positions)
fi

echo "[PATH] REG_ROOT=${REG_ROOT}"
echo "[PATH] WORK_DIR=${WORK_DIR}"
echo "[PATH] INPUT_DIR=${INPUT_DIR}"
echo "[PATH] INPUT_CONFIG_FILE=${INPUT_CONFIG_FILE}"
echo "[PATH] OUTPUT_CONFIG_FILE=${OUTPUT_CONFIG_FILE}"
echo "[PATH] OUTPUT_2D_FILE=${OUTPUT_2D_FILE}"
echo "[PATH] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PATH] CONDA_SH=${CONDA_SH}"
echo "[PATH] PY_SCRIPT=${PY_SCRIPT}"
for path in "$INPUT_DIR" "$INPUT_CONFIG_FILE" "$CONDA_SH" "$PY_SCRIPT"; do
    [[ -e "$path" ]] || { echo "Error: missing input: $path" >&2; exit 1; }
done
source "$CONDA_SH"
set +u
conda activate ashlar
set -u
python -u "$PY_SCRIPT" "${PY_ARGS[@]}"
[[ -s "$OUTPUT_CONFIG_FILE" ]] || { echo "Error: registered config missing or empty: $OUTPUT_CONFIG_FILE" >&2; exit 1; }
[[ -s "$OUTPUT_2D_FILE" ]] || { echo "Error: stitched 2D output missing or empty: $OUTPUT_2D_FILE" >&2; exit 1; }
