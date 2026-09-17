#!/bin/bash

#SBATCH -J cellreads_integration
#SBATCH -o logs001_segResultsStitch/segResultsStitch_%A.out
#SBATCH -e logs001_segResultsStitch/segResultsStitch_%A.err

#SBATCH -p C64M512G
#SBATCH -N 1
#SBATCH -c 60

#SBATCH --time=12:00:00


set -euo pipefail

usage() {
    printf '%s\n' \
        "Usage: 01_segResultsStitch.sh --script_dir DIR --conda_sh FILE --project_root DIR --project_name NAME --reg_dir_suffix SUFFIX --image_width PX --if_dirname NAME --tile_registered_name FILE --output_dirname NAME --seg_method NAME --output_suffix SUFFIX --clean_gene_match_string TEXT --clustermap_output_label LABEL"
}

start_time=$(date +%s)

finish() {
    status=$?
    end_time=$(date +%s)
    echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "运行时间: $((end_time - start_time)) seconds"
    if [[ "$status" -eq 0 ]]; then
        echo "STATUS: SUCCESS | SLURM_JOB_NAME=${SLURM_JOB_NAME:-N/A}"
    else
        echo "STATUS: FAILED | SLURM_JOB_NAME=${SLURM_JOB_NAME:-N/A}"
    fi
}
trap finish EXIT

SCRIPT_DIR=""
CONDA_SH=""
PROJECT_ROOT=""
PROJECT_NAME=""
REG_DIR_SUFFIX=""
IMAGE_WIDTH=""
IF_DIRNAME=""
TILE_REGISTERED_NAME=""
OUTPUT_DIRNAME=""
SEG_METHOD=""
OUTPUT_SUFFIX=""
CLEAN_GENE_MATCH_STRING=""
CLUSTERMAP_OUTPUT_LABEL=""

while (( $# )); do
    case "$1" in
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --image_width) IMAGE_WIDTH="$2"; shift 2 ;;
        --if_dirname) IF_DIRNAME="$2"; shift 2 ;;
        --tile_registered_name) TILE_REGISTERED_NAME="$2"; shift 2 ;;
        --output_dirname) OUTPUT_DIRNAME="$2"; shift 2 ;;
        --seg_method) SEG_METHOD="$2"; shift 2 ;;
        --output_suffix) OUTPUT_SUFFIX="$2"; shift 2 ;;
        --clean_gene_match_string) CLEAN_GENE_MATCH_STRING="$2"; shift 2 ;;
        --clustermap_output_label) CLUSTERMAP_OUTPUT_LABEL="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

for required_value in \
    "$SCRIPT_DIR" "$CONDA_SH" "$PROJECT_ROOT" "$PROJECT_NAME" \
    "$IMAGE_WIDTH" "$IF_DIRNAME" "$TILE_REGISTERED_NAME" \
    "$OUTPUT_DIRNAME" "$SEG_METHOD" "$OUTPUT_SUFFIX" \
    "$CLEAN_GENE_MATCH_STRING" "$CLUSTERMAP_OUTPUT_LABEL"; do
    if [[ -z "$required_value" ]]; then
        echo "Missing required argument" >&2
        usage >&2
        exit 2
    fi
done

PYTHON_SCRIPT="${SCRIPT_DIR}/segResultsStitch_v1_20260112.py"
REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REG_ROOT="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
TILE_DIR="${REG_ROOT}/${IF_DIRNAME}"
TILE_INITIAL="${TILE_DIR}/TileConfiguration.initial.txt"
TILE_REGISTERED="${TILE_DIR}/${TILE_REGISTERED_NAME}"
TILE_GRID="${TILE_DIR}/tile_summary.csv"
OUTPUT_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/${OUTPUT_DIRNAME}"
COORDS_OUTPUT="${OUTPUT_DIR}/coords.csv"
TUNED_COORDS_OUTPUT="${OUTPUT_DIR}/tuned_coords.csv"
CELL_CENTERS_OUTPUT="${OUTPUT_DIR}/cell_centers_${PROJECT_NAME}_${SEG_METHOD}_${OUTPUT_SUFFIX}.csv"
REMAIN_READS_OUTPUT="${OUTPUT_DIR}/remain_reads_${PROJECT_NAME}_${SEG_METHOD}_${OUTPUT_SUFFIX}.csv"

for required_file in \
    "$CONDA_SH" "$PYTHON_SCRIPT" "$TILE_INITIAL" "$TILE_REGISTERED" "$TILE_GRID"; do
    if [[ ! -f "$required_file" ]]; then
        echo "Required file not found: $required_file" >&2
        exit 1
    fi
done

mkdir -p "$OUTPUT_DIR"

echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============= SLURM Job Info =================="
echo "Job ID:          ${SLURM_JOB_ID:-N/A}"
echo "Job Name:        ${SLURM_JOB_NAME:-N/A}"
echo "Node List:       ${SLURM_NODELIST:-N/A}"
echo "CPUs per task:   ${SLURM_CPUS_PER_TASK:-N/A}"
echo "Memory per node: ${SLURM_MEM_PER_NODE:-N/A} MB"
echo "[INFO] runner: $PYTHON_SCRIPT"
echo "[INFO] registration_root: $REG_ROOT"
echo "[INFO] tile_initial: $TILE_INITIAL"
echo "[INFO] tile_registered: $TILE_REGISTERED"
echo "[INFO] tile_grid: $TILE_GRID"
echo "[INFO] output_dir: $OUTPUT_DIR"

source "$CONDA_SH"
conda activate data_analysis_env

python -u "$PYTHON_SCRIPT" \
    --tile_initial "$TILE_INITIAL" \
    --tile_registered "$TILE_REGISTERED" \
    --tile_grid "$TILE_GRID" \
    --input_reg_dir "$REG_ROOT" \
    --output_dir "$OUTPUT_DIR" \
    --coords_output "$COORDS_OUTPUT" \
    --tuned_coords_output "$TUNED_COORDS_OUTPUT" \
    --cell_centers_output "$CELL_CENTERS_OUTPUT" \
    --remain_reads_output "$REMAIN_READS_OUTPUT" \
    --figure_output_dir "$OUTPUT_DIR" \
    --image_width "$IMAGE_WIDTH" \
    --seg_method "$SEG_METHOD" \
    --project_name "$PROJECT_NAME" \
    --output_suffix "$OUTPUT_SUFFIX" \
    --clean_gene_match_string "$CLEAN_GENE_MATCH_STRING" \
    --clustermap_output_label "$CLUSTERMAP_OUTPUT_LABEL"

for output_file in "$CELL_CENTERS_OUTPUT" "$REMAIN_READS_OUTPUT"; do
    if [[ ! -f "$output_file" ]]; then
        echo "Expected output not found: $output_file" >&2
        exit 1
    fi
done
