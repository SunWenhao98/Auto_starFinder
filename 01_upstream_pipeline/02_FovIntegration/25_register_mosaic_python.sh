#!/bin/bash
#SBATCH -J mosaic_reg_python
#SBATCH -o logs025_mosaic_registration/%x_%A.out
#SBATCH -e logs025_mosaic_registration/%x_%A.err
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 8

#SBATCH --time=08:00:00

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 25_register_mosaic_python.sh --fixed_mosaic FILE --moving_mosaic FILE --output_prefix PATH [options]

Estimate a Python moving-to-reference translation, then write the full-resolution
registered moving OME-BigTIFF and QC outputs on the fixed/reference canvas.

Required:
  --fixed_mosaic FILE
  --moving_mosaic FILE
  --output_prefix PATH

Options:
  --script_dir PATH                 Directory containing p25/p29 runners
  --conda_env NAME                  Conda environment [ashlar]
  --overview_downsample INT         Coarse downsample [16]
  --overview_block_px INT           Source overview block [4096]
  --roi_size_px INT                 Full-resolution ROI size [1024]
  --roi_count INT                   Requested ROI pairs [9]
  --min_valid_rois INT              Minimum inlier ROI count [4]
  --upsample_factor INT             Python subpixel factor [20]
  --min_overlap_ratio FLOAT         Minimum overlap [0.2]
  --max_roi_spread_px FLOAT         Maximum accepted ROI spread [1.0]
  --tile_size_px INT                Registered output tile size [1024]
  --interpolation_order INT         0 (nearest) or 1 (linear) [1]
  --preview_downsample INT          QC preview downsample [16]
  --compression NAME                TIFF compression [zlib]
  --overwrite BOOL                  Permit replacing outputs [false]
  --dry_run BOOL                    Print commands only [false]
  -h, --help
USAGE
}

is_true() {
    case "${1,,}" in
        true|1|yes) return 0 ;;
        false|0|no|"") return 1 ;;
        *) echo "Error: expected boolean true/false, got '$1'" >&2; exit 1 ;;
    esac
}

print_slurm_info() {
    echo "Job ID: ${SLURM_JOB_ID:-N/A}"
    echo "Job Name: ${SLURM_JOB_NAME:-N/A}"
    echo "Node: ${SLURMD_NODENAME:-N/A}"
    echo "CPUs: ${SLURM_CPUS_PER_TASK:-N/A}"
    echo "Memory: ${SLURM_MEM_PER_NODE:-N/A} MB"
}

SCRIPT_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration"
FIXED_MOSAIC=""
MOVING_MOSAIC=""
OUTPUT_PREFIX=""
CONDA_ENV="ashlar"
OVERVIEW_DOWNSAMPLE="16"
OVERVIEW_BLOCK_PX="4096"
ROI_SIZE_PX="1024"
ROI_COUNT="9"
MIN_VALID_ROIS="4"
UPSAMPLE_FACTOR="20"
MIN_OVERLAP_RATIO="0.2"
MAX_ROI_SPREAD_PX="1.0"
TILE_SIZE_PX="1024"
INTERPOLATION_ORDER="1"
PREVIEW_DOWNSAMPLE="16"
COMPRESSION="zlib"
OVERWRITE="false"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fixed_mosaic) FIXED_MOSAIC="$2"; shift 2 ;;
        --moving_mosaic) MOVING_MOSAIC="$2"; shift 2 ;;
        --output_prefix) OUTPUT_PREFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_env) CONDA_ENV="$2"; shift 2 ;;
        --overview_downsample) OVERVIEW_DOWNSAMPLE="$2"; shift 2 ;;
        --overview_block_px) OVERVIEW_BLOCK_PX="$2"; shift 2 ;;
        --roi_size_px) ROI_SIZE_PX="$2"; shift 2 ;;
        --roi_count) ROI_COUNT="$2"; shift 2 ;;
        --min_valid_rois) MIN_VALID_ROIS="$2"; shift 2 ;;
        --upsample_factor) UPSAMPLE_FACTOR="$2"; shift 2 ;;
        --min_overlap_ratio) MIN_OVERLAP_RATIO="$2"; shift 2 ;;
        --max_roi_spread_px) MAX_ROI_SPREAD_PX="$2"; shift 2 ;;
        --tile_size_px) TILE_SIZE_PX="$2"; shift 2 ;;
        --interpolation_order) INTERPOLATION_ORDER="$2"; shift 2 ;;
        --preview_downsample) PREVIEW_DOWNSAMPLE="$2"; shift 2 ;;
        --compression) COMPRESSION="$2"; shift 2 ;;
        --overwrite) OVERWRITE="$2"; shift 2 ;;
        --dry_run) DRY_RUN="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: Unknown parameter: $1" >&2; print_usage >&2; exit 1 ;;
    esac
done

[[ -n "$FIXED_MOSAIC" ]] || { echo "Error: --fixed_mosaic is required" >&2; exit 1; }
[[ -n "$MOVING_MOSAIC" ]] || { echo "Error: --moving_mosaic is required" >&2; exit 1; }
[[ -n "$OUTPUT_PREFIX" ]] || { echo "Error: --output_prefix is required" >&2; exit 1; }
[[ "$INTERPOLATION_ORDER" == "0" || "$INTERPOLATION_ORDER" == "1" ]] || { echo "Error: --interpolation_order must be 0 or 1" >&2; exit 1; }

TRANSFORM_JSON="${OUTPUT_PREFIX}.python.transform.json"
SUMMARY_CSV="${OUTPUT_PREFIX}.python.transform.csv"
ROI_CSV="${OUTPUT_PREFIX}.python.roi_diagnostics.csv"
REGISTERED_MOSAIC="${OUTPUT_PREFIX}.python.registered_moving.ome.tif"
APPLICATION_JSON="${OUTPUT_PREFIX}.python.application.json"
PREVIEW_TIF="${OUTPUT_PREFIX}.python.registered_moving.preview.tif"
QC_PNG="${OUTPUT_PREFIX}.python.registration_qc.png"
QC_PDF="${OUTPUT_PREFIX}.python.registration_qc.pdf"
REGISTER_SCRIPT="${SCRIPT_DIR}/p25_register_mosaic_python.py"
APPLY_SCRIPT="${SCRIPT_DIR}/p29_apply_mosaic_transform.py"

REGISTER_COMMAND=(
    python -u "$REGISTER_SCRIPT"
    --fixed_mosaic "$FIXED_MOSAIC"
    --moving_mosaic "$MOVING_MOSAIC"
    --output_json "$TRANSFORM_JSON"
    --output_csv "$SUMMARY_CSV"
    --output_roi_csv "$ROI_CSV"
    --overview_downsample "$OVERVIEW_DOWNSAMPLE"
    --overview_block_px "$OVERVIEW_BLOCK_PX"
    --roi_size_px "$ROI_SIZE_PX"
    --roi_count "$ROI_COUNT"
    --min_valid_rois "$MIN_VALID_ROIS"
    --upsample_factor "$UPSAMPLE_FACTOR"
    --min_overlap_ratio "$MIN_OVERLAP_RATIO"
    --max_roi_spread_px "$MAX_ROI_SPREAD_PX"
    --overwrite "$OVERWRITE"
)
APPLY_COMMAND=(
    python -u "$APPLY_SCRIPT"
    --transform_json "$TRANSFORM_JSON"
    --fixed_mosaic "$FIXED_MOSAIC"
    --moving_mosaic "$MOVING_MOSAIC"
    --output_registered_mosaic "$REGISTERED_MOSAIC"
    --output_application_json "$APPLICATION_JSON"
    --output_preview_tif "$PREVIEW_TIF"
    --output_qc_png "$QC_PNG"
    --output_qc_pdf "$QC_PDF"
    --tile_size_px "$TILE_SIZE_PX"
    --interpolation_order "$INTERPOLATION_ORDER"
    --preview_downsample "$PREVIEW_DOWNSAMPLE"
    --overview_block_px "$OVERVIEW_BLOCK_PX"
    --compression "$COMPRESSION"
    --overwrite "$OVERWRITE"
)

printf '[COMMAND] '; printf '%q ' "${REGISTER_COMMAND[@]}"; printf '\n'
printf '[COMMAND] '; printf '%q ' "${APPLY_COMMAND[@]}"; printf '\n'
if is_true "$DRY_RUN"; then
    exit 0
fi

for input_path in "$FIXED_MOSAIC" "$MOVING_MOSAIC" "$REGISTER_SCRIPT" "$APPLY_SCRIPT"; do
    [[ -f "$input_path" ]] || { echo "Error: missing file: $input_path" >&2; exit 1; }
done
mkdir -p "$(dirname "$OUTPUT_PREFIX")"
start_time=$(date +%s)
trap 'exit_code=$?; if [[ $exit_code -ne 0 ]]; then echo "STATUS: FAILED | SLURM_JOB_NAME=${SLURM_JOB_NAME:-N/A}"; fi' EXIT
print_slurm_info
source "/gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh"
set +u
conda activate "$CONDA_ENV"
set -u
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
"${REGISTER_COMMAND[@]}"
"${APPLY_COMMAND[@]}"

for output_path in "$TRANSFORM_JSON" "$SUMMARY_CSV" "$ROI_CSV" "$REGISTERED_MOSAIC" "$APPLICATION_JSON" "$PREVIEW_TIF" "$QC_PNG" "$QC_PDF"; do
    [[ -s "$output_path" ]] || { echo "Error: missing or empty output: $output_path" >&2; exit 1; }
done
echo "Elapsed time: $(($(date +%s) - start_time)) seconds"
echo "STATUS: SUCCESS | SLURM_JOB_NAME=${SLURM_JOB_NAME:-N/A}"
trap - EXIT
