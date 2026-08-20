#!/bin/bash
#SBATCH -J fiji_stitch_mosaic
#SBATCH -o logs_fiji_stitch_mosaic/%x_%A.out
#SBATCH -e logs_fiji_stitch_mosaic/%x_%A.err
#SBATCH -p C64M512G
#SBATCH --qos=normal
#SBATCH -n 1
#SBATCH -c 60

#SBATCH --time=24:00:00
#SBATCH --no-requeue
#SBATCH --export=ALL

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 16_fiji_stitch_mosaic.sh --work_dir PATH --config_file NAME --channel_mode MODE [options]

Reuse a registered or shifted TileConfiguration to fuse selected channels in Fiji.

Required:
  --work_dir PATH          Stitching work directory
  --config_file NAME       Mosaic config filename under work_dir
  --channel_mode MODE      LeicaIF, OlympusIF, LeicaSeqE, or an *Independent mode

Options:
  --channel_names LIST     Comma-separated channels overriding channel_mode []
  --channel_dir_prefix PFX Channel input directory prefix [raw-]
  --output_prefix PREFIX   Fiji output prefix [stitched_fiji]
  --stitch_pattern NAME    Fiji macro branch [Positions_from_file_mosaic]
  --layout_file NAME       Channel-local config filename [TileConfiguration.mosaic.txt]
  --fusion_method NAME     Fiji fusion method [Linear Blending]
  --subpixel_accuracy BOOL Enable floating-coordinate interpolation [true]
  --image_output NAME      Fiji image output mode [Fuse and display]
  --save_format FORMAT     tiff, ome_tiff, or ome_bigtiff [tiff]
  --script_dir PATH        Fiji helper directory
  --fiji_executable FILE   Fiji ImageJ executable
  --conda_env NAME         Fiji conda environment
  --dry_run BOOL           Print per-channel actions only [false]
  -h, --help               Show this help and exit
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
        LeicaIF) echo "561-CA9,488-CD144,647-CD31,DAPI" ;;
        OlympusIF) echo "488-CD144,561-CA9,647-CD31,DAPI" ;;
        LeicaSeqE) echo "647-GCnt,561-GTrb,Padlayer,DAPI" ;;
        LeicaIFIndependent) echo "561-CA9,488-CD144,647-CD31" ;;
        OlympusIFIndependent) echo "488-CD144,561-CA9,647-CD31" ;;
        LeicaSeqEIndependent) echo "647-GCnt,561-GTrb" ;;
        *)
            echo "Error: Unsupported --channel_mode: $1" >&2
            echo "Supported modes: LeicaIF, OlympusIF, LeicaSeqE, LeicaIFIndependent, OlympusIFIndependent, LeicaSeqEIndependent" >&2
            exit 1
            ;;
    esac
}

DEFAULT_SCRIPT_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration"
WORK_DIR=""
CONFIG_FILE=""
CHANNEL_MODE=""
CHANNEL_NAMES=""
CHANNEL_DIR_PREFIX="raw-"
OUTPUT_PREFIX="stitched_fiji"
STITCH_PATTERN="Positions_from_file_mosaic"
LAYOUT_FILE="TileConfiguration.mosaic.txt"
FUSION_METHOD="Linear Blending"
SUBPIXEL_ACCURACY="true"
IMAGE_OUTPUT="Fuse and display"
SAVE_FORMAT="tiff"
SCRIPT_DIR="$DEFAULT_SCRIPT_DIR"
FIJI_EXECUTABLE="/gpfs/share/home/2401111558/11_softwares/Fiji.app/ImageJ-linux64"
CONDA_ENV="/gpfs/share/home/2401111558/anaconda3/envs/Fiji"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --work_dir) WORK_DIR="$2"; shift 2 ;;
        --config_file) CONFIG_FILE="$2"; shift 2 ;;
        --channel_mode) CHANNEL_MODE="$2"; shift 2 ;;
        --channel_names) CHANNEL_NAMES="$2"; shift 2 ;;
        --channel_dir_prefix) CHANNEL_DIR_PREFIX="$2"; shift 2 ;;
        --output_prefix) OUTPUT_PREFIX="$2"; shift 2 ;;
        --stitch_pattern) STITCH_PATTERN="$2"; shift 2 ;;
        --layout_file) LAYOUT_FILE="$2"; shift 2 ;;
        --fusion_method) FUSION_METHOD="$2"; shift 2 ;;
        --subpixel_accuracy) SUBPIXEL_ACCURACY="$2"; shift 2 ;;
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
[[ -n "$CONFIG_FILE" ]] || { echo "Error: --config_file is required" >&2; exit 1; }
[[ -n "$CHANNEL_MODE" ]] || { echo "Error: --channel_mode is required" >&2; exit 1; }
is_true "$SUBPIXEL_ACCURACY" || true
is_true "$DRY_RUN" || true

if [[ -z "$CHANNEL_NAMES" ]]; then
    CHANNEL_NAMES="$(resolve_channel_names "$CHANNEL_MODE")"
fi
IFS=',' read -r -a CHANNEL_ARRAY <<< "$CHANNEL_NAMES"
MOSAIC_CONFIG_FILE="${WORK_DIR}/${CONFIG_FILE}"
BSH_FILE="${SCRIPT_DIR}/fiji_grid_collection_stitch.bsh"

echo "[PARAM] WORK_DIR=${WORK_DIR}"
echo "[PARAM] CONFIG_FILE=${CONFIG_FILE}"
echo "[PARAM] MOSAIC_CONFIG_FILE=${MOSAIC_CONFIG_FILE}"
echo "[PARAM] CHANNEL_MODE=${CHANNEL_MODE}"
echo "[PARAM] CHANNEL_NAMES=${CHANNEL_NAMES}"
echo "[PARAM] CHANNEL_DIR_PREFIX=${CHANNEL_DIR_PREFIX}"
echo "[PARAM] OUTPUT_PREFIX=${OUTPUT_PREFIX}"
echo "[PARAM] STITCH_PATTERN=${STITCH_PATTERN}"
echo "[PARAM] LAYOUT_FILE=${LAYOUT_FILE}"
echo "[PARAM] FUSION_METHOD=${FUSION_METHOD}"
echo "[PARAM] SUBPIXEL_ACCURACY=${SUBPIXEL_ACCURACY}"
echo "[PARAM] IMAGE_OUTPUT=${IMAGE_OUTPUT}"
echo "[PARAM] SAVE_FORMAT=${SAVE_FORMAT}"
echo "[PARAM] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PARAM] FIJI_EXECUTABLE=${FIJI_EXECUTABLE}"
echo "[PARAM] CONDA_ENV=${CONDA_ENV}"
echo "[PARAM] DRY_RUN=${DRY_RUN}"

if ! is_true "$DRY_RUN"; then
    [[ -f "$MOSAIC_CONFIG_FILE" ]] || { echo "Error: mosaic config not found: $MOSAIC_CONFIG_FILE" >&2; exit 1; }
    [[ -f "$BSH_FILE" ]] || { echo "Error: Fiji BSH helper not found: $BSH_FILE" >&2; exit 1; }
    [[ -x "$FIJI_EXECUTABLE" ]] || { echo "Error: Fiji executable not found: $FIJI_EXECUTABLE" >&2; exit 1; }
    mkdir -p logs_fiji_stitch_mosaic
    start_time=$(date +%s)
    echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"
    print_slurm_info
    source "/gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh"
    set +u
    conda activate "$CONDA_ENV"
    set -u
fi

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

    echo "[CHANNEL] ${CHANNEL_NAME}"
    echo "[COPY] ${MOSAIC_CONFIG_FILE} -> ${CHANNEL_LAYOUT_FILE}"
    echo "[CMD] ${FIJI_EXECUTABLE} --headless --console ${BSH_FILE}"
    echo "[OUTPUT] ${EXPECTED_OUTPUT_FILE}"
    if is_true "$DRY_RUN"; then
        continue
    fi

    [[ -d "$INPUT_DIR" ]] || { echo "Error: channel directory not found: $INPUT_DIR" >&2; exit 1; }
    cp "$MOSAIC_CONFIG_FILE" "$CHANNEL_LAYOUT_FILE"

    GRID_X="1"
    GRID_Y="1"
    FIRST_INDEX="1"
    OUTPUT_TEXTFILE_NAME="TileConfiguration.txt"
    REGRESSION_THRESHOLD="0.30"
    MAX_AVG_DISPLACEMENT_THRESHOLD="2.50"
    ABSOLUTE_DISPLACEMENT_THRESHOLD="3.50"
    COMPUTE_OVERLAP="false"
    COMPUTATION_PARAMETERS="Save memory (but be slower)"
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
done

# Reserved p1/p2 fallback. These calls remain disabled by default.
# STITCH_PATTERN="Positions_from_file_p1"
# for CHANNEL_NAME in "${CHANNEL_ARRAY[@]}"; do
#     INPUT_DIR="${WORK_DIR}/${CHANNEL_DIR_PREFIX}${CHANNEL_NAME}"
#     OUTPUT_NAME="${OUTPUT_PREFIX}_${CHANNEL_NAME}_p1"
#     cp "${WORK_DIR}/TileConfiguration.registered.p1.txt" "${INPUT_DIR}/TileConfiguration.registered.p1.txt"
#     "$FIJI_EXECUTABLE" --headless --console "$BSH_FILE"
# done
# STITCH_PATTERN="Positions_from_file_p2"
# for CHANNEL_NAME in "${CHANNEL_ARRAY[@]}"; do
#     INPUT_DIR="${WORK_DIR}/${CHANNEL_DIR_PREFIX}${CHANNEL_NAME}"
#     OUTPUT_NAME="${OUTPUT_PREFIX}_${CHANNEL_NAME}_p2"
#     cp "${WORK_DIR}/TileConfiguration.registered.p2.txt" "${INPUT_DIR}/TileConfiguration.registered.p2.txt"
#     "$FIJI_EXECUTABLE" --headless --console "$BSH_FILE"
# done

if is_true "$DRY_RUN"; then
    echo "STATUS: DRY_RUN_DONE"
else
    echo "STATUS: SUCCESS"
    end_time=$(date +%s)
    echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Elapsed time: $((end_time - start_time)) seconds"
fi
