#!/bin/bash
#SBATCH -J mosaic_reg_matlab
#SBATCH -o logs026_mosaic_registration/%x_%A.out
#SBATCH -e logs026_mosaic_registration/%x_%A.err
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 8

#SBATCH --time=08:00:00

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 26_register_mosaic_matlab.sh --fixed_mosaic FILE --moving_mosaic FILE --output_prefix PATH [options]

Estimate a Matlab DFT moving-to-reference translation, then use the shared
Python application runner to write the full-resolution registered image and QC.

Required:
  --fixed_mosaic FILE
  --moving_mosaic FILE
  --output_prefix PATH

Options:
  --script_dir PATH
  --dft_helper_dir PATH
  --conda_env NAME                  Python application environment [ashlar]
  --overview_downsample INT         [16]
  --overview_block_px INT           Python QC source block [4096]
  --roi_size_px INT                 [1024]
  --roi_count INT                   [9]
  --min_valid_rois INT              [4]
  --min_overlap_ratio FLOAT         [0.2]
  --max_roi_spread_px FLOAT         [1.0]
  --tile_size_px INT                [1024]
  --interpolation_order INT         0 (nearest) or 1 (linear) [1]
  --preview_downsample INT          [16]
  --compression NAME                [zlib]
  --overwrite BOOL                  [false]
  --dry_run BOOL                    [false]
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

matlab_escape() {
    local value="$1"
    printf '%s' "${value//\'/\'\'}"
}

SCRIPT_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration"
DFT_HELPER_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/core_programs/starFinder"
FIXED_MOSAIC=""
MOVING_MOSAIC=""
OUTPUT_PREFIX=""
CONDA_ENV="ashlar"
OVERVIEW_DOWNSAMPLE="16"
OVERVIEW_BLOCK_PX="4096"
ROI_SIZE_PX="1024"
ROI_COUNT="9"
MIN_VALID_ROIS="4"
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
        --dft_helper_dir) DFT_HELPER_DIR="$2"; shift 2 ;;
        --conda_env) CONDA_ENV="$2"; shift 2 ;;
        --overview_downsample) OVERVIEW_DOWNSAMPLE="$2"; shift 2 ;;
        --overview_block_px) OVERVIEW_BLOCK_PX="$2"; shift 2 ;;
        --roi_size_px) ROI_SIZE_PX="$2"; shift 2 ;;
        --roi_count) ROI_COUNT="$2"; shift 2 ;;
        --min_valid_rois) MIN_VALID_ROIS="$2"; shift 2 ;;
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

TRANSFORM_JSON="${OUTPUT_PREFIX}.matlab.transform.json"
SUMMARY_CSV="${OUTPUT_PREFIX}.matlab.transform.csv"
ROI_CSV="${OUTPUT_PREFIX}.matlab.roi_diagnostics.csv"
REGISTERED_MOSAIC="${OUTPUT_PREFIX}.matlab.registered_moving.ome.tif"
APPLICATION_JSON="${OUTPUT_PREFIX}.matlab.application.json"
PREVIEW_TIF="${OUTPUT_PREFIX}.matlab.registered_moving.preview.tif"
QC_PNG="${OUTPUT_PREFIX}.matlab.registration_qc.png"
QC_PDF="${OUTPUT_PREFIX}.matlab.registration_qc.pdf"
MATLAB_SCRIPT="${SCRIPT_DIR}/p26_register_mosaic_matlab.m"
APPLY_SCRIPT="${SCRIPT_DIR}/p29_apply_mosaic_transform.py"

OVERWRITE_MATLAB="false"
if is_true "$OVERWRITE"; then OVERWRITE_MATLAB="true"; fi
MATLAB_BATCH="addpath('$(matlab_escape "$SCRIPT_DIR")'); p26_register_mosaic_matlab('fixed_mosaic','$(matlab_escape "$FIXED_MOSAIC")','moving_mosaic','$(matlab_escape "$MOVING_MOSAIC")','output_json','$(matlab_escape "$TRANSFORM_JSON")','output_csv','$(matlab_escape "$SUMMARY_CSV")','output_roi_csv','$(matlab_escape "$ROI_CSV")','overview_downsample',$OVERVIEW_DOWNSAMPLE,'roi_size_px',$ROI_SIZE_PX,'roi_count',$ROI_COUNT,'min_valid_rois',$MIN_VALID_ROIS,'min_overlap_ratio',$MIN_OVERLAP_RATIO,'max_roi_spread_px',$MAX_ROI_SPREAD_PX,'overwrite',$OVERWRITE_MATLAB,'dft_helper_dir','$(matlab_escape "$DFT_HELPER_DIR")');"
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

printf '[COMMAND] matlab -batch %q\n' "$MATLAB_BATCH"
printf '[COMMAND] '; printf '%q ' "${APPLY_COMMAND[@]}"; printf '\n'
if is_true "$DRY_RUN"; then
    exit 0
fi

for input_path in "$FIXED_MOSAIC" "$MOVING_MOSAIC" "$MATLAB_SCRIPT" "$APPLY_SCRIPT" "$DFT_HELPER_DIR/DFTRegister2D.m"; do
    [[ -f "$input_path" ]] || { echo "Error: missing file: $input_path" >&2; exit 1; }
done
mkdir -p "$(dirname "$OUTPUT_PREFIX")"
start_time=$(date +%s)
trap 'exit_code=$?; if [[ $exit_code -ne 0 ]]; then echo "STATUS: FAILED | SLURM_JOB_NAME=${SLURM_JOB_NAME:-N/A}"; fi' EXIT
module purge
module load matlab/2023a
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
matlab -batch "$MATLAB_BATCH"

source "/gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh"
set +u
conda activate "$CONDA_ENV"
set -u
"${APPLY_COMMAND[@]}"

for output_path in "$TRANSFORM_JSON" "$SUMMARY_CSV" "$ROI_CSV" "$REGISTERED_MOSAIC" "$APPLICATION_JSON" "$PREVIEW_TIF" "$QC_PNG" "$QC_PDF"; do
    [[ -s "$output_path" ]] || { echo "Error: missing or empty output: $output_path" >&2; exit 1; }
done
echo "Elapsed time: $(($(date +%s) - start_time)) seconds"
echo "STATUS: SUCCESS | SLURM_JOB_NAME=${SLURM_JOB_NAME:-N/A}"
trap - EXIT
