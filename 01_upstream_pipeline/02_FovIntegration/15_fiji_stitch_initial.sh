#!/bin/bash
#SBATCH -J fiji_stitch_initial
#SBATCH -o logs015_fiji_stitch_initial/%x_%A.out
#SBATCH -e logs015_fiji_stitch_initial/%x_%A.err
#SBATCH -p C64M512G
#SBATCH -N 1
#SBATCH -c 60
#SBATCH --time=24:00:00

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 15_fiji_stitch_initial.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME --stitching_workdir NAME --source_channel NAME --input_config NAME --output_config NAME [options]

Options:
  --output_name NAME
  --regression_threshold FLOAT
  --max_avg_displacement_threshold FLOAT
  --absolute_displacement_threshold FLOAT
  --fusion_method NAME
  --compute_overlap BOOL
  --subpixel_accuracy BOOL
  --computation_parameters NAME
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
SOURCE_CHANNEL=""
INPUT_CONFIG=""
OUTPUT_CONFIG=""
OUTPUT_NAME=""
REGRESSION_THRESHOLD="0.30"
MAX_AVG_DISPLACEMENT_THRESHOLD="2.50"
ABSOLUTE_DISPLACEMENT_THRESHOLD="3.50"
FUSION_METHOD="Linear Blending"
COMPUTE_OVERLAP="true"
SUBPIXEL_ACCURACY="true"
COMPUTATION_PARAMETERS="Save memory (but be slower)"
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
        --source_channel) SOURCE_CHANNEL="$2"; shift 2 ;;
        --input_config) INPUT_CONFIG="$2"; shift 2 ;;
        --output_config) OUTPUT_CONFIG="$2"; shift 2 ;;
        --output_name) OUTPUT_NAME="$2"; shift 2 ;;
        --regression_threshold) REGRESSION_THRESHOLD="$2"; shift 2 ;;
        --max_avg_displacement_threshold) MAX_AVG_DISPLACEMENT_THRESHOLD="$2"; shift 2 ;;
        --absolute_displacement_threshold) ABSOLUTE_DISPLACEMENT_THRESHOLD="$2"; shift 2 ;;
        --fusion_method) FUSION_METHOD="$2"; shift 2 ;;
        --compute_overlap) COMPUTE_OVERLAP="$2"; shift 2 ;;
        --subpixel_accuracy) SUBPIXEL_ACCURACY="$2"; shift 2 ;;
        --computation_parameters) COMPUTATION_PARAMETERS="$2"; shift 2 ;;
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

for value in PROJECT_ROOT PROJECT_NAME REG_DIR_SUFFIX SCRIPT_DIR FIJI_DIR STITCHING_WORKDIR SOURCE_CHANNEL INPUT_CONFIG OUTPUT_CONFIG; do
    [[ -n "${!value}" ]] || { echo "Error: ${value} is required" >&2; exit 1; }
done
[[ -n "$OUTPUT_NAME" ]] || OUTPUT_NAME="stitched_${SOURCE_CHANNEL}"
FIJI_EXECUTABLE="${FIJI_DIR}/ImageJ-linux64"

# Fixed stage contract
STITCH_PATTERN="Positions_from_file"
LAYOUT_FILE="TileConfiguration.txt"
REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REG_ROOT="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
WORK_DIR="${REG_ROOT}/${STITCHING_WORKDIR}"
INPUT_DIR="${WORK_DIR}/${SOURCE_CHANNEL}"
INPUT_CONFIG_FILE="${WORK_DIR}/${INPUT_CONFIG}"
CHANNEL_LAYOUT_FILE="${INPUT_DIR}/${LAYOUT_FILE}"
CHANNEL_REGISTERED_CONFIG="${INPUT_DIR}/${LAYOUT_FILE%.txt}.registered.txt"
OUTPUT_CONFIG_FILE="${WORK_DIR}/${OUTPUT_CONFIG}"
OUTPUT_DIRECTORY="$INPUT_DIR"
case "$SAVE_FORMAT" in
    tiff) EXPECTED_OUTPUT_FILE="${OUTPUT_DIRECTORY}/${OUTPUT_NAME}_2d_Fiji.tif" ;;
    ome_tiff) EXPECTED_OUTPUT_FILE="${OUTPUT_DIRECTORY}/${OUTPUT_NAME}_2d_Fiji.ome.tif" ;;
    ome_bigtiff) EXPECTED_OUTPUT_FILE="${OUTPUT_DIRECTORY}/${OUTPUT_NAME}_2d_Fiji.ome.btf" ;;
    *) echo "Error: unsupported --save_format: $SAVE_FORMAT" >&2; exit 1 ;;
esac

print_slurm_info
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] REG_DIR_SUFFIX=${REG_DIR_SUFFIX}"
echo "[PARAM] STITCHING_WORKDIR=${STITCHING_WORKDIR}"
echo "[PARAM] WORK_DIR=${WORK_DIR}"
echo "[PARAM] SOURCE_CHANNEL=${SOURCE_CHANNEL}"
echo "[PARAM] INPUT_CONFIG=${INPUT_CONFIG}"
echo "[PARAM] OUTPUT_CONFIG=${OUTPUT_CONFIG}"
echo "[MODE] STITCH_PATTERN=${STITCH_PATTERN}"
echo "[MODE] LAYOUT_FILE=${LAYOUT_FILE}"
echo "[PARAM] OUTPUT_NAME=${OUTPUT_NAME}"
echo "[PARAM] REGRESSION_THRESHOLD=${REGRESSION_THRESHOLD}"
echo "[PARAM] MAX_AVG_DISPLACEMENT_THRESHOLD=${MAX_AVG_DISPLACEMENT_THRESHOLD}"
echo "[PARAM] ABSOLUTE_DISPLACEMENT_THRESHOLD=${ABSOLUTE_DISPLACEMENT_THRESHOLD}"
echo "[PARAM] FUSION_METHOD=${FUSION_METHOD}"
echo "[PARAM] COMPUTE_OVERLAP=${COMPUTE_OVERLAP}"
echo "[PARAM] SUBPIXEL_ACCURACY=${SUBPIXEL_ACCURACY}"
echo "[PARAM] COMPUTATION_PARAMETERS=${COMPUTATION_PARAMETERS}"
echo "[PARAM] IMAGE_OUTPUT=${IMAGE_OUTPUT}"
echo "[PARAM] SAVE_FORMAT=${SAVE_FORMAT}"
echo "[PARAM] DRY_RUN=${DRY_RUN}"

BSH_FILE="${SCRIPT_DIR}/fiji_grid_collection_stitch.bsh"

echo "[PATH] INPUT_DIR=${INPUT_DIR}"
echo "[PATH] INPUT_CONFIG_FILE=${INPUT_CONFIG_FILE}"
echo "[PATH] OUTPUT_CONFIG_FILE=${OUTPUT_CONFIG_FILE}"
echo "[PATH] EXPECTED_OUTPUT_FILE=${EXPECTED_OUTPUT_FILE}"
echo "[PATH] BSH_FILE=${BSH_FILE}"
echo "[PATH] FIJI_DIR=${FIJI_DIR}"
echo "[PATH] FIJI_EXECUTABLE=${FIJI_EXECUTABLE}"
echo "[COPY] ${INPUT_CONFIG_FILE} -> ${CHANNEL_LAYOUT_FILE}"
echo "[COMMAND] ${FIJI_EXECUTABLE} --headless --console ${BSH_FILE}"
echo "[COPY] ${CHANNEL_REGISTERED_CONFIG} -> ${OUTPUT_CONFIG_FILE}"

if [[ "$DRY_RUN" == "true" ]]; then
    FINAL_STATUS="DRY_RUN_DONE"
    exit 0
fi
[[ -f "$BSH_FILE" ]] || { echo "Error: missing file: $BSH_FILE" >&2; exit 1; }
[[ -d "$FIJI_DIR" ]] || { echo "Error: Fiji directory not found: $FIJI_DIR" >&2; exit 1; }
[[ -x "$FIJI_EXECUTABLE" ]] || { echo "Error: Fiji executable not found or not executable: $FIJI_EXECUTABLE" >&2; exit 1; }

cp "$INPUT_CONFIG_FILE" "$CHANNEL_LAYOUT_FILE"
export INPUT_DIR OUTPUT_NAME STITCH_PATTERN
export LAYOUT_FILE
export REGRESSION_THRESHOLD MAX_AVG_DISPLACEMENT_THRESHOLD
export ABSOLUTE_DISPLACEMENT_THRESHOLD FUSION_METHOD COMPUTE_OVERLAP
export SUBPIXEL_ACCURACY COMPUTATION_PARAMETERS IMAGE_OUTPUT OUTPUT_DIRECTORY SAVE_FORMAT SCRIPT_DIR
"$FIJI_EXECUTABLE" --headless --console "$BSH_FILE"

[[ -s "$EXPECTED_OUTPUT_FILE" ]] || { echo "Error: Fiji output missing: $EXPECTED_OUTPUT_FILE" >&2; exit 1; }
[[ -s "$CHANNEL_REGISTERED_CONFIG" ]] || { echo "Error: registered config missing or empty: $CHANNEL_REGISTERED_CONFIG" >&2; exit 1; }
cp "$CHANNEL_REGISTERED_CONFIG" "$OUTPUT_CONFIG_FILE"
[[ -s "$OUTPUT_CONFIG_FILE" ]] || { echo "Error: copied config missing or empty: $OUTPUT_CONFIG_FILE" >&2; exit 1; }
