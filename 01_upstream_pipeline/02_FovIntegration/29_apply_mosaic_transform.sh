#!/bin/bash
#SBATCH -J mosaic_apply_transform
#SBATCH -o logs029_mosaic_registration/%x_%A.out
#SBATCH -e logs029_mosaic_registration/%x_%A.err
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 8

#SBATCH --time=08:00:00

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 29_apply_mosaic_transform.sh --transform_json FILE --fixed_mosaic FILE --moving_mosaic FILE --output_prefix PATH [options]

Options:
  --script_dir PATH
  --conda_env NAME            [ashlar]
  --tile_size_px INT          [1024]
  --interpolation_order INT   0 (nearest) or 1 (linear) [1]
  --preview_downsample INT    [16]
  --overview_block_px INT     [4096]
  --compression NAME          [zlib]
  --overwrite BOOL            [false]
  --dry_run BOOL              [false]
  -h, --help
USAGE
}

is_true() {
    case "${1,,}" in true|1|yes) return 0 ;; false|0|no|"") return 1 ;; *) exit 1 ;; esac
}

SCRIPT_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration"
TRANSFORM_JSON=""
FIXED_MOSAIC=""
MOVING_MOSAIC=""
OUTPUT_PREFIX=""
CONDA_ENV="ashlar"
TILE_SIZE_PX="1024"
INTERPOLATION_ORDER="1"
PREVIEW_DOWNSAMPLE="16"
OVERVIEW_BLOCK_PX="4096"
COMPRESSION="zlib"
OVERWRITE="false"
DRY_RUN="false"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --transform_json) TRANSFORM_JSON="$2"; shift 2 ;;
        --fixed_mosaic) FIXED_MOSAIC="$2"; shift 2 ;;
        --moving_mosaic) MOVING_MOSAIC="$2"; shift 2 ;;
        --output_prefix) OUTPUT_PREFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_env) CONDA_ENV="$2"; shift 2 ;;
        --tile_size_px) TILE_SIZE_PX="$2"; shift 2 ;;
        --interpolation_order) INTERPOLATION_ORDER="$2"; shift 2 ;;
        --preview_downsample) PREVIEW_DOWNSAMPLE="$2"; shift 2 ;;
        --overview_block_px) OVERVIEW_BLOCK_PX="$2"; shift 2 ;;
        --compression) COMPRESSION="$2"; shift 2 ;;
        --overwrite) OVERWRITE="$2"; shift 2 ;;
        --dry_run) DRY_RUN="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: Unknown parameter: $1" >&2; exit 1 ;;
    esac
done
[[ -n "$TRANSFORM_JSON" && -n "$FIXED_MOSAIC" && -n "$MOVING_MOSAIC" && -n "$OUTPUT_PREFIX" ]] || { echo "Error: transform, fixed, moving, and output prefix are required" >&2; exit 1; }
[[ "$INTERPOLATION_ORDER" == "0" || "$INTERPOLATION_ORDER" == "1" ]] || { echo "Error: --interpolation_order must be 0 or 1" >&2; exit 1; }
SCRIPT="${SCRIPT_DIR}/p29_apply_mosaic_transform.py"
REGISTERED_MOSAIC="${OUTPUT_PREFIX}.registered_moving.ome.tif"
APPLICATION_JSON="${OUTPUT_PREFIX}.application.json"
PREVIEW_TIF="${OUTPUT_PREFIX}.registered_moving.preview.tif"
QC_PNG="${OUTPUT_PREFIX}.registration_qc.png"
QC_PDF="${OUTPUT_PREFIX}.registration_qc.pdf"
COMMAND=(python -u "$SCRIPT" --transform_json "$TRANSFORM_JSON" --fixed_mosaic "$FIXED_MOSAIC" --moving_mosaic "$MOVING_MOSAIC" --output_registered_mosaic "$REGISTERED_MOSAIC" --output_application_json "$APPLICATION_JSON" --output_preview_tif "$PREVIEW_TIF" --output_qc_png "$QC_PNG" --output_qc_pdf "$QC_PDF" --tile_size_px "$TILE_SIZE_PX" --interpolation_order "$INTERPOLATION_ORDER" --preview_downsample "$PREVIEW_DOWNSAMPLE" --overview_block_px "$OVERVIEW_BLOCK_PX" --compression "$COMPRESSION" --overwrite "$OVERWRITE")
printf '[COMMAND] '; printf '%q ' "${COMMAND[@]}"; printf '\n'
if is_true "$DRY_RUN"; then exit 0; fi
for path in "$TRANSFORM_JSON" "$FIXED_MOSAIC" "$MOVING_MOSAIC" "$SCRIPT"; do [[ -f "$path" ]] || { echo "Error: missing file: $path" >&2; exit 1; }; done
mkdir -p "$(dirname "$OUTPUT_PREFIX")"
trap 'exit_code=$?; if [[ $exit_code -ne 0 ]]; then echo "STATUS: FAILED | SLURM_JOB_NAME=${SLURM_JOB_NAME:-N/A}"; fi' EXIT
source "/gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh"
set +u
conda activate "$CONDA_ENV"
set -u
"${COMMAND[@]}"
for path in "$REGISTERED_MOSAIC" "$APPLICATION_JSON" "$PREVIEW_TIF" "$QC_PNG" "$QC_PDF"; do [[ -s "$path" ]] || { echo "Error: missing output: $path" >&2; exit 1; }; done
echo "STATUS: SUCCESS | SLURM_JOB_NAME=${SLURM_JOB_NAME:-N/A}"
trap - EXIT
