#!/bin/bash
#SBATCH -J ashlar_joint_mosaic
#SBATCH -o logs032_ashlar_joint_mosaic/%x_%A.out
#SBATCH -e logs032_ashlar_joint_mosaic/%x_%A.err
#SBATCH -p C64M512G
#SBATCH -N 1
#SBATCH -c 60
#SBATCH --time=24:00:00

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 32_ashlar_stitch_mosaic_joint.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME --stitching_workdir NAME --channel_mode MODE --input_config NAME [options]

Options:
  --channel_dir_prefix PREFIX
  --stitch_result_dirname NAME
  --output_prefix PREFIX
  --output_format FORMAT
  --rotate_images BOOL
  --make_3d BOOL
  --pixel_size_um FLOAT
  --slice_indices LIST
  --tile_transform_json NAME   joint-stitching summary json (in the workdir) whose IF tile
                               transform is applied to every channel; empty = none
  --ref_channel_dir NAME       also stitch this reference-round channel dir ...
  --ref_input_config NAME      ... with this config (no tile transform); both empty = skip
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
CHANNEL_MODE=""
INPUT_CONFIG=""
CHANNEL_DIR_PREFIX="raw-"
STITCH_RESULT_DIRNAME="stitching_results"
OUTPUT_PREFIX="stitched"
OUTPUT_FORMAT="preserve"
ROTATE_IMAGES="false"
MAKE_3D="false"
PIXEL_SIZE_UM="0.142"
SLICE_INDICES=""
TILE_TRANSFORM_JSON=""
REF_CHANNEL_DIR=""
REF_INPUT_CONFIG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --stitching_workdir) STITCHING_WORKDIR="$2"; shift 2 ;;
        --channel_mode) CHANNEL_MODE="$2"; shift 2 ;;
        --input_config) INPUT_CONFIG="$2"; shift 2 ;;
        --channel_dir_prefix) CHANNEL_DIR_PREFIX="$2"; shift 2 ;;
        --stitch_result_dirname) STITCH_RESULT_DIRNAME="$2"; shift 2 ;;
        --output_prefix) OUTPUT_PREFIX="$2"; shift 2 ;;
        --output_format) OUTPUT_FORMAT="$2"; shift 2 ;;
        --rotate_images) ROTATE_IMAGES="$2"; shift 2 ;;
        --make_3d) MAKE_3D="$2"; shift 2 ;;
        --pixel_size_um) PIXEL_SIZE_UM="$2"; shift 2 ;;
        --slice_indices) SLICE_INDICES="$2"; shift 2 ;;
        --tile_transform_json) TILE_TRANSFORM_JSON="$2"; shift 2 ;;
        --ref_channel_dir) REF_CHANNEL_DIR="$2"; shift 2 ;;
        --ref_input_config) REF_INPUT_CONFIG="$2"; shift 2 ;;
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

for value in PROJECT_ROOT PROJECT_NAME REG_DIR_SUFFIX SCRIPT_DIR CONDA_SH STITCHING_WORKDIR CHANNEL_MODE INPUT_CONFIG; do
    [[ -n "${!value}" ]] || { echo "Error: ${value} is required" >&2; exit 1; }
done
case "$CHANNEL_MODE" in
    LeicaIF) CHANNEL_NAMES="561-CA9,488-CD144,647-CD31,DAPI" ;;
    OlympusIF) CHANNEL_NAMES="488-CD144,561-CA9,647-CD31,DAPI" ;;
    LeicaSeqE) CHANNEL_NAMES="647-GCnt,561-GTrb,Padlayer,DAPI" ;;
    LeicaIFIndependent) CHANNEL_NAMES="561-CA9,488-CD144,647-CD31" ;;
    OlympusIFIndependent) CHANNEL_NAMES="488-CD144,561-CA9,647-CD31" ;;
    LeicaSeqEIndependent) CHANNEL_NAMES="647-GCnt,561-GTrb" ;;
    *) echo "Error: unsupported --channel_mode: $CHANNEL_MODE" >&2; exit 1 ;;
esac
REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REG_ROOT="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
WORK_DIR="${REG_ROOT}/${STITCHING_WORKDIR}"
INPUT_CONFIG_FILE="${WORK_DIR}/${INPUT_CONFIG}"
STITCH_RESULT_DIR="${WORK_DIR}/${STITCH_RESULT_DIRNAME}"
print_slurm_info
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] STITCHING_WORKDIR=${STITCHING_WORKDIR}"
echo "[PARAM] CHANNEL_MODE=${CHANNEL_MODE}"
echo "[PARAM] CHANNEL_NAMES=${CHANNEL_NAMES}"
echo "[PARAM] INPUT_CONFIG=${INPUT_CONFIG}"
echo "[PARAM] CHANNEL_DIR_PREFIX=${CHANNEL_DIR_PREFIX}"
echo "[PARAM] STITCH_RESULT_DIRNAME=${STITCH_RESULT_DIRNAME}"
echo "[PARAM] OUTPUT_PREFIX=${OUTPUT_PREFIX}"
echo "[PARAM] OUTPUT_FORMAT=${OUTPUT_FORMAT}"
echo "[PARAM] ROTATE_IMAGES=${ROTATE_IMAGES}"
echo "[PARAM] MAKE_3D=${MAKE_3D}"
echo "[PARAM] PIXEL_SIZE_UM=${PIXEL_SIZE_UM}"
echo "[PARAM] SLICE_INDICES=${SLICE_INDICES}"
echo "[PARAM] TILE_TRANSFORM_JSON=${TILE_TRANSFORM_JSON}"
echo "[PARAM] REF_CHANNEL_DIR=${REF_CHANNEL_DIR}"
echo "[PARAM] REF_INPUT_CONFIG=${REF_INPUT_CONFIG}"

PY_SCRIPT="${SCRIPT_DIR}/p32_ashlar_stitch_mosaic_joint.py"

echo "[PATH] REG_ROOT=${REG_ROOT}"
echo "[PATH] WORK_DIR=${WORK_DIR}"
echo "[PATH] INPUT_CONFIG_FILE=${INPUT_CONFIG_FILE}"
echo "[PATH] STITCH_RESULT_DIR=${STITCH_RESULT_DIR}"
echo "[PATH] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PATH] CONDA_SH=${CONDA_SH}"
echo "[PATH] PY_SCRIPT=${PY_SCRIPT}"
TRANSFORM_ARGS=()
if [[ -n "$TILE_TRANSFORM_JSON" ]]; then
    TRANSFORM_ARGS=(--tile_transform_json "${WORK_DIR}/${TILE_TRANSFORM_JSON}")
fi
if [[ -n "$REF_CHANNEL_DIR" || -n "$REF_INPUT_CONFIG" ]]; then
    [[ -n "$REF_CHANNEL_DIR" && -n "$REF_INPUT_CONFIG" ]] || { echo "Error: --ref_channel_dir and --ref_input_config must be given together" >&2; exit 1; }
fi
for path in "$INPUT_CONFIG_FILE" "$CONDA_SH" "$PY_SCRIPT"; do
    [[ -f "$path" ]] || { echo "Error: missing file: $path" >&2; exit 1; }
done
if [[ -n "$TILE_TRANSFORM_JSON" ]]; then
    [[ -f "${WORK_DIR}/${TILE_TRANSFORM_JSON}" ]] || { echo "Error: missing file: ${WORK_DIR}/${TILE_TRANSFORM_JSON}" >&2; exit 1; }
fi
source "$CONDA_SH"
set +u
conda activate ashlar
set -u

if [[ -n "$REF_CHANNEL_DIR" ]]; then
    REF_OUTPUT_PREFIX="${STITCH_RESULT_DIR}/${OUTPUT_PREFIX}_${REF_CHANNEL_DIR#"$CHANNEL_DIR_PREFIX"}"
    PY_ARGS=(
        --input_dir "${WORK_DIR}/${REF_CHANNEL_DIR}"
        --config_file "${WORK_DIR}/${REF_INPUT_CONFIG}"
        --output_image_prefix "$REF_OUTPUT_PREFIX"
        --output_format "$OUTPUT_FORMAT"
        --make_3d "$MAKE_3D"
        --pixel_size_um "$PIXEL_SIZE_UM"
        --slice_indices "$SLICE_INDICES"
    )
    if [[ "$ROTATE_IMAGES" == "true" ]]; then
        PY_ARGS+=(--rotate90)
    fi
    python -u "$PY_SCRIPT" "${PY_ARGS[@]}"
    [[ -s "${REF_OUTPUT_PREFIX}_2d.ome.tif" ]] || { echo "Error: stitched 2D output missing or empty: ${REF_OUTPUT_PREFIX}_2d.ome.tif" >&2; exit 1; }
fi

IFS=',' read -r -a CHANNEL_ARRAY <<< "$CHANNEL_NAMES"
for CHANNEL_NAME in "${CHANNEL_ARRAY[@]}"; do
    CHANNEL_NAME="${CHANNEL_NAME//[[:space:]]/}"
    [[ -n "$CHANNEL_NAME" ]] || continue
    INPUT_DIR="${WORK_DIR}/${CHANNEL_DIR_PREFIX}${CHANNEL_NAME}"
    OUTPUT_IMAGE_PREFIX="${STITCH_RESULT_DIR}/${OUTPUT_PREFIX}_${CHANNEL_NAME}"
    OUTPUT_2D_FILE="${OUTPUT_IMAGE_PREFIX}_2d.ome.tif"
    PY_ARGS=(
        --input_dir "$INPUT_DIR"
        --config_file "$INPUT_CONFIG_FILE"
        --output_image_prefix "$OUTPUT_IMAGE_PREFIX"
        --output_format "$OUTPUT_FORMAT"
        --make_3d "$MAKE_3D"
        --pixel_size_um "$PIXEL_SIZE_UM"
        --slice_indices "$SLICE_INDICES"
        ${TRANSFORM_ARGS[@]+"${TRANSFORM_ARGS[@]}"}
    )
    if [[ "$ROTATE_IMAGES" == "true" ]]; then
        PY_ARGS+=(--rotate90)
    fi
    python -u "$PY_SCRIPT" "${PY_ARGS[@]}"
    [[ -s "$OUTPUT_2D_FILE" ]] || { echo "Error: stitched 2D output missing or empty: $OUTPUT_2D_FILE" >&2; exit 1; }
done
