#!/bin/bash
#SBATCH -J fiji_estimate_coordinates
#SBATCH -o logs_fiji_estimate_coordinates/%x_%A.out
#SBATCH -e logs_fiji_estimate_coordinates/%x_%A.err
#SBATCH -p C64M512G
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH -c 60

#SBATCH --time=24:00:00
#SBATCH --no-requeue
#SBATCH --export=ALL

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 15_fiji_estimate_coordinates.sh --work_dir PATH --source_channel NAME [options]

Estimate Fiji registered coordinates from an initial TileConfiguration.

Required:
  --work_dir PATH                         Stitching work directory
  --source_channel NAME                   Source channel directory under work_dir

Options:
  --grid_x INT                            Grid columns [1]
  --grid_y INT                            Grid rows [1]
  --first_index INT                       First file index [1]
  --stitch_pattern NAME                   Fiji macro branch [Positions_from_file]
  --initial_config_name NAME              Work-dir initial config [TileConfiguration.initial.txt]
  --layout_file NAME                      Channel-local layout filename [TileConfiguration.txt]
  --registered_config_name NAME           Published Fiji config [TileConfiguration.Fiji.txt]
  --run_fiji_fusion_preflight BOOL        Enforce preflight report [true]
  --fiji_fusion_preflight_report NAME     Preflight JSON filename [fiji_fusion_preflight.json]
  --output_name NAME                      Fiji image output stem [stitched_<source_channel>]
  --output_textfile_name NAME             Grid-mode config output [TileConfiguration.txt]
  --regression_threshold FLOAT            Fiji regression threshold [0.30]
  --max_avg_displacement_threshold FLOAT  Fiji max/avg displacement threshold [2.50]
  --absolute_displacement_threshold FLOAT Fiji absolute displacement threshold [3.50]
  --fusion_method NAME                    Fiji fusion method [Linear Blending]
  --compute_overlap BOOL                  Re-estimate overlap [true]
  --subpixel_accuracy BOOL                Enable subpixel interpolation [true]
  --computation_parameters NAME           Fiji computation mode [Save memory (but be slower)]
  --image_output NAME                     Fiji image output mode [Fuse and display]
  --save_format FORMAT                    tiff, ome_tiff, or ome_bigtiff [tiff]
  --script_dir PATH                       Fiji helper directory
  --fiji_executable FILE                  Fiji ImageJ executable
  --conda_env NAME                        Fiji conda environment
  --dry_run BOOL                          Print actions without copying or running [false]
  -h, --help                              Show this help and exit
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

DEFAULT_SCRIPT_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration"
WORK_DIR=""
SOURCE_CHANNEL=""
GRID_X="1"
GRID_Y="1"
FIRST_INDEX="1"
STITCH_PATTERN="Positions_from_file"
INITIAL_CONFIG_NAME="TileConfiguration.initial.txt"
LAYOUT_FILE="TileConfiguration.txt"
REGISTERED_CONFIG_NAME="TileConfiguration.Fiji.txt"
RUN_FIJI_FUSION_PREFLIGHT="true"
FIJI_FUSION_PREFLIGHT_REPORT="fiji_fusion_preflight.json"
OUTPUT_NAME=""
OUTPUT_TEXTFILE_NAME="TileConfiguration.txt"
REGRESSION_THRESHOLD="0.30"
MAX_AVG_DISPLACEMENT_THRESHOLD="2.50"
ABSOLUTE_DISPLACEMENT_THRESHOLD="3.50"
FUSION_METHOD="Linear Blending"
COMPUTE_OVERLAP="true"
SUBPIXEL_ACCURACY="true"
COMPUTATION_PARAMETERS="Save memory (but be slower)"
IMAGE_OUTPUT="Fuse and display"
SAVE_FORMAT="tiff"
SCRIPT_DIR="$DEFAULT_SCRIPT_DIR"
FIJI_EXECUTABLE="/gpfs/share/home/${USER}/11_softwares/Fiji.app/ImageJ-linux64"
CONDA_ENV="/gpfs/share/home/${USER}/anaconda3/envs/Fiji"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --work_dir) WORK_DIR="$2"; shift 2 ;;
        --source_channel) SOURCE_CHANNEL="$2"; shift 2 ;;
        --grid_x) GRID_X="$2"; shift 2 ;;
        --grid_y) GRID_Y="$2"; shift 2 ;;
        --first_index) FIRST_INDEX="$2"; shift 2 ;;
        --stitch_pattern) STITCH_PATTERN="$2"; shift 2 ;;
        --initial_config_name) INITIAL_CONFIG_NAME="$2"; shift 2 ;;
        --layout_file) LAYOUT_FILE="$2"; shift 2 ;;
        --registered_config_name) REGISTERED_CONFIG_NAME="$2"; shift 2 ;;
        --run_fiji_fusion_preflight) RUN_FIJI_FUSION_PREFLIGHT="$2"; shift 2 ;;
        --fiji_fusion_preflight_report) FIJI_FUSION_PREFLIGHT_REPORT="$2"; shift 2 ;;
        --output_name) OUTPUT_NAME="$2"; shift 2 ;;
        --output_textfile_name) OUTPUT_TEXTFILE_NAME="$2"; shift 2 ;;
        --regression_threshold) REGRESSION_THRESHOLD="$2"; shift 2 ;;
        --max_avg_displacement_threshold) MAX_AVG_DISPLACEMENT_THRESHOLD="$2"; shift 2 ;;
        --absolute_displacement_threshold) ABSOLUTE_DISPLACEMENT_THRESHOLD="$2"; shift 2 ;;
        --fusion_method) FUSION_METHOD="$2"; shift 2 ;;
        --compute_overlap) COMPUTE_OVERLAP="$2"; shift 2 ;;
        --subpixel_accuracy) SUBPIXEL_ACCURACY="$2"; shift 2 ;;
        --computation_parameters) COMPUTATION_PARAMETERS="$2"; shift 2 ;;
        --image_output) IMAGE_OUTPUT="$2"; shift 2 ;;
        --save_format) SAVE_FORMAT="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --fiji_executable) FIJI_EXECUTABLE="$2"; shift 2 ;;
        --conda_env) CONDA_ENV="$2"; shift 2 ;;
        --dry_run) DRY_RUN="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: Unknown parameter: $1" >&2; print_usage >&2; exit 1 ;;
    esac
done

[[ -n "$WORK_DIR" ]] || { echo "Error: --work_dir is required" >&2; exit 1; }
[[ -n "$SOURCE_CHANNEL" ]] || { echo "Error: --source_channel is required" >&2; exit 1; }
is_true "$RUN_FIJI_FUSION_PREFLIGHT" || true
is_true "$COMPUTE_OVERLAP" || true
is_true "$SUBPIXEL_ACCURACY" || true
is_true "$DRY_RUN" || true

if [[ -z "$OUTPUT_NAME" ]]; then
    OUTPUT_NAME="stitched_${SOURCE_CHANNEL}"
fi

INPUT_DIR="${WORK_DIR}/${SOURCE_CHANNEL}"
INITIAL_CONFIG_FILE="${WORK_DIR}/${INITIAL_CONFIG_NAME}"
CHANNEL_LAYOUT_FILE="${INPUT_DIR}/${LAYOUT_FILE}"
CHANNEL_REGISTERED_CONFIG="${INPUT_DIR}/TileConfiguration.registered.txt"
PUBLISHED_REGISTERED_CONFIG="${WORK_DIR}/${REGISTERED_CONFIG_NAME}"
PREFLIGHT_REPORT_FILE="${WORK_DIR}/${FIJI_FUSION_PREFLIGHT_REPORT}"
OUTPUT_DIRECTORY="$INPUT_DIR"
BSH_FILE="${SCRIPT_DIR}/fiji_grid_collection_stitch.bsh"
case "$SAVE_FORMAT" in
    tiff) EXPECTED_OUTPUT_FILE="${OUTPUT_DIRECTORY}/${OUTPUT_NAME}_2d_Fiji.tif" ;;
    ome_tiff) EXPECTED_OUTPUT_FILE="${OUTPUT_DIRECTORY}/${OUTPUT_NAME}_2d_Fiji.ome.tif" ;;
    ome_bigtiff) EXPECTED_OUTPUT_FILE="${OUTPUT_DIRECTORY}/${OUTPUT_NAME}_2d_Fiji.ome.btf" ;;
    *) echo "Error: unsupported --save_format: $SAVE_FORMAT" >&2; exit 1 ;;
esac

echo "[PARAM] WORK_DIR=${WORK_DIR}"
echo "[PARAM] SOURCE_CHANNEL=${SOURCE_CHANNEL}"
echo "[PARAM] INPUT_DIR=${INPUT_DIR}"
echo "[PARAM] INITIAL_CONFIG_FILE=${INITIAL_CONFIG_FILE}"
echo "[PARAM] CHANNEL_LAYOUT_FILE=${CHANNEL_LAYOUT_FILE}"
echo "[PARAM] PUBLISHED_REGISTERED_CONFIG=${PUBLISHED_REGISTERED_CONFIG}"
echo "[PARAM] STITCH_PATTERN=${STITCH_PATTERN}"
echo "[PARAM] OUTPUT_NAME=${OUTPUT_NAME}"
echo "[PARAM] OUTPUT_TEXTFILE_NAME=${OUTPUT_TEXTFILE_NAME}"
echo "[PARAM] REGRESSION_THRESHOLD=${REGRESSION_THRESHOLD}"
echo "[PARAM] MAX_AVG_DISPLACEMENT_THRESHOLD=${MAX_AVG_DISPLACEMENT_THRESHOLD}"
echo "[PARAM] ABSOLUTE_DISPLACEMENT_THRESHOLD=${ABSOLUTE_DISPLACEMENT_THRESHOLD}"
echo "[PARAM] FUSION_METHOD=${FUSION_METHOD}"
echo "[PARAM] COMPUTE_OVERLAP=${COMPUTE_OVERLAP}"
echo "[PARAM] SUBPIXEL_ACCURACY=${SUBPIXEL_ACCURACY}"
echo "[PARAM] COMPUTATION_PARAMETERS=${COMPUTATION_PARAMETERS}"
echo "[PARAM] IMAGE_OUTPUT=${IMAGE_OUTPUT}"
echo "[PARAM] SAVE_FORMAT=${SAVE_FORMAT}"
echo "[PARAM] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PARAM] FIJI_EXECUTABLE=${FIJI_EXECUTABLE}"
echo "[PARAM] CONDA_ENV=${CONDA_ENV}"
echo "[PARAM] RUN_FIJI_FUSION_PREFLIGHT=${RUN_FIJI_FUSION_PREFLIGHT}"
echo "[PARAM] PREFLIGHT_REPORT_FILE=${PREFLIGHT_REPORT_FILE}"
echo "[PARAM] EXPECTED_OUTPUT_FILE=${EXPECTED_OUTPUT_FILE}"
echo "[PARAM] DRY_RUN=${DRY_RUN}"
echo "[COPY] ${INITIAL_CONFIG_FILE} -> ${CHANNEL_LAYOUT_FILE}"
echo "[CMD] ${FIJI_EXECUTABLE} --headless --console ${BSH_FILE}"
echo "[COPY] ${CHANNEL_REGISTERED_CONFIG} -> ${PUBLISHED_REGISTERED_CONFIG}"

if is_true "$DRY_RUN"; then
    echo "FIJI_FUSION_PREFLIGHT: DRY_RUN_NOT_EVALUATED"
    echo "STATUS: DRY_RUN_DONE"
    exit 0
fi

if is_true "$RUN_FIJI_FUSION_PREFLIGHT"; then
    [[ -f "$PREFLIGHT_REPORT_FILE" ]] || {
        echo "Error: Fiji fusion preflight report not found: $PREFLIGHT_REPORT_FILE" >&2
        exit 1
    }
    if grep -qE '"fiji_fusion_safe"[[:space:]]*:[[:space:]]*true' "$PREFLIGHT_REPORT_FILE"; then
        echo "FIJI_FUSION_PREFLIGHT: SAFE"
    else
        echo "FIJI_FUSION_PREFLIGHT: UNSAFE" >&2
        echo "Use Ashlar stitching" >&2
        exit 1
    fi
else
    echo "FIJI_FUSION_PREFLIGHT: BYPASSED"
fi

[[ -f "$INITIAL_CONFIG_FILE" ]] || { echo "Error: initial config not found: $INITIAL_CONFIG_FILE" >&2; exit 1; }
[[ -d "$INPUT_DIR" ]] || { echo "Error: source channel directory not found: $INPUT_DIR" >&2; exit 1; }
[[ -f "$BSH_FILE" ]] || { echo "Error: Fiji BSH helper not found: $BSH_FILE" >&2; exit 1; }
[[ -x "$FIJI_EXECUTABLE" ]] || { echo "Error: Fiji executable not found: $FIJI_EXECUTABLE" >&2; exit 1; }

mkdir -p logs_fiji_estimate_coordinates
start_time=$(date +%s)
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"
print_slurm_info

source "/gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh"
set +u
conda activate "$CONDA_ENV"
set -u

cp "$INITIAL_CONFIG_FILE" "$CHANNEL_LAYOUT_FILE"
export INPUT_DIR GRID_X GRID_Y FIRST_INDEX OUTPUT_NAME STITCH_PATTERN
export LAYOUT_FILE OUTPUT_TEXTFILE_NAME REGRESSION_THRESHOLD
export MAX_AVG_DISPLACEMENT_THRESHOLD ABSOLUTE_DISPLACEMENT_THRESHOLD
export FUSION_METHOD COMPUTE_OVERLAP SUBPIXEL_ACCURACY COMPUTATION_PARAMETERS
export IMAGE_OUTPUT OUTPUT_DIRECTORY SAVE_FORMAT SCRIPT_DIR

"$FIJI_EXECUTABLE" --headless --console "$BSH_FILE"
[[ -s "$EXPECTED_OUTPUT_FILE" ]] || {
    echo "Error: Fiji output not found or empty: $EXPECTED_OUTPUT_FILE" >&2
    exit 1
}
[[ -f "$CHANNEL_REGISTERED_CONFIG" ]] || {
    echo "Error: Fiji registered config not found: $CHANNEL_REGISTERED_CONFIG" >&2
    exit 1
}
cp "$CHANNEL_REGISTERED_CONFIG" "$PUBLISHED_REGISTERED_CONFIG"
echo "REGISTERED_CONFIG: ${PUBLISHED_REGISTERED_CONFIG}"
echo "STATUS: SUCCESS"

end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Elapsed time: $((end_time - start_time)) seconds"
