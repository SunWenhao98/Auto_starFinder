#!/bin/bash
#SBATCH -J fiji_stitch_mosaic
#SBATCH -o logs016_fiji_stitch_mosaic/%x_%A.out
#SBATCH -e logs016_fiji_stitch_mosaic/%x_%A.err
#SBATCH -p C64M512G
#SBATCH -N 1
#SBATCH -c 60
#SBATCH --time=24:00:00

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 16_fiji_stitch_mosaic.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME --stitching_workdir NAME --input_config NAME --channel_mode MODE [options]

Options:
  --channel_names LIST
  --channel_dir_prefix PREFIX
  --output_prefix PREFIX
  --fusion_method NAME
  --image_output NAME
  --save_format FORMAT
  --script_dir PATH
  --fiji_dir PATH
  --dry_run BOOL
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
FIJI_DIR=""
STITCHING_WORKDIR=""
INPUT_CONFIG=""
CHANNEL_MODE=""
CHANNEL_NAMES=""    # Optional direct-shell override
CHANNEL_DIR_PREFIX="raw-"
OUTPUT_PREFIX="stitched_fiji"

FUSION_METHOD="Linear Blending"
IMAGE_OUTPUT="Fuse and display"
SAVE_FORMAT="tiff"
DRY_RUN="false"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --fiji_dir) FIJI_DIR="$2"; shift 2 ;;
        --stitching_workdir) STITCHING_WORKDIR="$2"; shift 2 ;;
        --input_config) INPUT_CONFIG="$2"; shift 2 ;;
        --channel_mode) CHANNEL_MODE="$2"; shift 2 ;;
        --channel_names) CHANNEL_NAMES="$2"; shift 2 ;;
        --channel_dir_prefix) CHANNEL_DIR_PREFIX="$2"; shift 2 ;;
        --output_prefix) OUTPUT_PREFIX="$2"; shift 2 ;;
        --fusion_method) FUSION_METHOD="$2"; shift 2 ;;
        --image_output) IMAGE_OUTPUT="$2"; shift 2 ;;
        --save_format) SAVE_FORMAT="$2"; shift 2 ;;
        --dry_run) DRY_RUN="$2"; shift 2 ;;
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

for value in PROJECT_ROOT PROJECT_NAME REG_DIR_SUFFIX SCRIPT_DIR FIJI_DIR STITCHING_WORKDIR INPUT_CONFIG CHANNEL_MODE; do
    [[ -n "${!value}" ]] || { echo "Error: ${value} is required" >&2; exit 1; }
done
FIJI_EXECUTABLE="${FIJI_DIR}/ImageJ-linux64"
if [[ -z "$CHANNEL_NAMES" ]]; then
    case "$CHANNEL_MODE" in
        LeicaIF) CHANNEL_NAMES="561-CA9,488-CD144,647-CD31,DAPI" ;;
        OlympusIF) CHANNEL_NAMES="488-CD144,561-CA9,647-CD31,DAPI" ;;
        LeicaSeqE) CHANNEL_NAMES="647-GCnt,561-GTrb,Padlayer,DAPI" ;;
        LeicaIFIndependent) CHANNEL_NAMES="561-CA9,488-CD144,647-CD31" ;;
        OlympusIFIndependent) CHANNEL_NAMES="488-CD144,561-CA9,647-CD31" ;;
        LeicaSeqEIndependent) CHANNEL_NAMES="647-GCnt,561-GTrb" ;;
        *) echo "Error: unsupported --channel_mode: $CHANNEL_MODE" >&2; exit 1 ;;
    esac
fi

REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REG_ROOT="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
WORK_DIR="${REG_ROOT}/${STITCHING_WORKDIR}"
INPUT_CONFIG_FILE="${WORK_DIR}/${INPUT_CONFIG}"
STITCHED_DIR="${WORK_DIR}/stitched${REG_DIR_SUFFIX}"
print_slurm_info
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] REG_DIR_SUFFIX=${REG_DIR_SUFFIX}"
echo "[PARAM] STITCHING_WORKDIR=${STITCHING_WORKDIR}"
echo "[PARAM] WORK_DIR=${WORK_DIR}"
echo "[PARAM] INPUT_CONFIG=${INPUT_CONFIG}"
echo "[PARAM] CHANNEL_MODE=${CHANNEL_MODE}"
echo "[PARAM] CHANNEL_NAMES=${CHANNEL_NAMES}"
echo "[PARAM] CHANNEL_DIR_PREFIX=${CHANNEL_DIR_PREFIX}"
echo "[PARAM] OUTPUT_PREFIX=${OUTPUT_PREFIX}"
echo "[PARAM] FUSION_METHOD=${FUSION_METHOD}"
echo "[PARAM] IMAGE_OUTPUT=${IMAGE_OUTPUT}"
echo "[PARAM] SAVE_FORMAT=${SAVE_FORMAT}"
echo "[PARAM] DRY_RUN=${DRY_RUN}"

STITCH_PATTERN="Positions_from_file_mosaic"
LAYOUT_FILE="TileConfiguration.mosaic.txt"
SUBPIXEL_ACCURACY="false"
BSH_FILE="${SCRIPT_DIR}/fiji_grid_collection_stitch.bsh"

echo "[MODE] STITCH_PATTERN=${STITCH_PATTERN}"
echo "[MODE] LAYOUT_FILE=${LAYOUT_FILE}"
echo "[MODE] SUBPIXEL_ACCURACY=${SUBPIXEL_ACCURACY}"
echo "[PATH] INPUT_CONFIG_FILE=${INPUT_CONFIG_FILE}"
echo "[PATH] BSH_FILE=${BSH_FILE}"
echo "[PATH] FIJI_DIR=${FIJI_DIR}"
echo "[PATH] FIJI_EXECUTABLE=${FIJI_EXECUTABLE}"
if [[ "$DRY_RUN" != "true" ]]; then
    [[ -f "$BSH_FILE" ]] || { echo "Error: missing file: $BSH_FILE" >&2; exit 1; }
    [[ -d "$FIJI_DIR" ]] || { echo "Error: Fiji directory not found: $FIJI_DIR" >&2; exit 1; }
    [[ -x "$FIJI_EXECUTABLE" ]] || { echo "Error: Fiji executable not found or not executable: $FIJI_EXECUTABLE" >&2; exit 1; }
fi
export FUSION_METHOD SUBPIXEL_ACCURACY IMAGE_OUTPUT SAVE_FORMAT SCRIPT_DIR

IFS=',' read -r -a CHANNEL_ARRAY <<< "$CHANNEL_NAMES"
for CHANNEL_NAME in "${CHANNEL_ARRAY[@]}"; do
    CHANNEL_NAME="${CHANNEL_NAME//[[:space:]]/}"
    [[ -n "$CHANNEL_NAME" ]] || continue
    INPUT_DIR="${WORK_DIR}/${CHANNEL_DIR_PREFIX}${CHANNEL_NAME}"
    CHANNEL_LAYOUT_FILE="${INPUT_DIR}/${LAYOUT_FILE}"
    OUTPUT_NAME="${OUTPUT_PREFIX}_${CHANNEL_NAME}"
    OUTPUT_DIRECTORY="$INPUT_DIR"
    case "$SAVE_FORMAT" in
        tiff) EXPECTED_OUTPUT_FILE="${OUTPUT_DIRECTORY}/${OUTPUT_NAME}_2d_Fiji.tif" ;;
        ome_tiff) EXPECTED_OUTPUT_FILE="${OUTPUT_DIRECTORY}/${OUTPUT_NAME}_2d_Fiji.ome.tif" ;;
        ome_bigtiff) EXPECTED_OUTPUT_FILE="${OUTPUT_DIRECTORY}/${OUTPUT_NAME}_2d_Fiji.ome.btf" ;;
        *) echo "Error: unsupported --save_format: $SAVE_FORMAT" >&2; exit 1 ;;
    esac
    STITCHED_OUTPUT_FILE="${STITCHED_DIR}/${PROJECT_NAME}_$(basename "$EXPECTED_OUTPUT_FILE")"
    echo "[COPY] ${INPUT_CONFIG_FILE} -> ${CHANNEL_LAYOUT_FILE}"
    echo "[COMMAND] ${FIJI_EXECUTABLE} --headless --console ${BSH_FILE}"
    echo "[OUTPUT] ${EXPECTED_OUTPUT_FILE}"
    echo "[OUTPUT] ${STITCHED_OUTPUT_FILE}"
    if [[ "$DRY_RUN" == "true" ]]; then
        continue
    fi
    cp "$INPUT_CONFIG_FILE" "$CHANNEL_LAYOUT_FILE"
    export INPUT_DIR OUTPUT_NAME STITCH_PATTERN LAYOUT_FILE OUTPUT_DIRECTORY
    "$FIJI_EXECUTABLE" --headless --console "$BSH_FILE"
    [[ -s "$EXPECTED_OUTPUT_FILE" ]] || { echo "Error: Fiji output missing: $EXPECTED_OUTPUT_FILE" >&2; exit 1; }
    mkdir -p "$STITCHED_DIR"
    cp -f -- "$EXPECTED_OUTPUT_FILE" "$STITCHED_OUTPUT_FILE"
    [[ -s "$STITCHED_OUTPUT_FILE" ]] || { echo "Error: copied stitched output missing or empty: $STITCHED_OUTPUT_FILE" >&2; exit 1; }
    echo "[COPY] ${EXPECTED_OUTPUT_FILE} -> ${STITCHED_OUTPUT_FILE}"
done
if [[ "$DRY_RUN" == "true" ]]; then
    FINAL_STATUS="DRY_RUN_DONE"
fi
