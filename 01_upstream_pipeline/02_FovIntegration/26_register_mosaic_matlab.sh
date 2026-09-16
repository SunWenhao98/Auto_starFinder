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
Usage: 26_register_mosaic_matlab.sh --project_root PATH --project_name NAME --reg_dir_suffix DIR --fixed_path PATH --moving_path PATH --output_workdir DIR --output_label NAME [options]

Options:
  --overview_downsample INT
  --overview_block_px INT
  --roi_size_px INT
  --roi_count INT
  --min_valid_rois INT
  --min_overlap_ratio FLOAT
  --max_roi_spread_px FLOAT
  --tile_size_px INT
  --interpolation_order INT
  --preview_downsample INT
  --compression NAME
  --overwrite BOOL
  --dry_run BOOL
  --script_dir PATH
  --conda_sh PATH
  --core_matlab_dir PATH
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

matlab_escape() {
    local value="$1"
    printf '%s' "${value//\'/\'\'}"
}

PROJECT_ROOT=""
PROJECT_NAME=""
REG_DIR_SUFFIX=""
SCRIPT_DIR=""
CONDA_SH=""
CORE_MATLAB_DIR=""
FIXED_PATH=""
MOVING_PATH=""
OUTPUT_WORKDIR=""
OUTPUT_LABEL=""
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
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --core_matlab_dir) CORE_MATLAB_DIR="$2"; shift 2 ;;
        --fixed_path) FIXED_PATH="$2"; shift 2 ;;
        --moving_path) MOVING_PATH="$2"; shift 2 ;;
        --output_workdir) OUTPUT_WORKDIR="$2"; shift 2 ;;
        --output_label) OUTPUT_LABEL="$2"; shift 2 ;;
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

for value in PROJECT_ROOT PROJECT_NAME REG_DIR_SUFFIX SCRIPT_DIR CONDA_SH CORE_MATLAB_DIR FIXED_PATH MOVING_PATH OUTPUT_WORKDIR OUTPUT_LABEL; do
    [[ -n "${!value}" ]] || { echo "Error: ${value} is required" >&2; exit 1; }
done
[[ "$INTERPOLATION_ORDER" == "0" || "$INTERPOLATION_ORDER" == "1" ]] || { echo "Error: --interpolation_order must be 0 or 1" >&2; exit 1; }

REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REG_ROOT="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
FIXED_MOSAIC="${REG_ROOT}/${FIXED_PATH}"
MOVING_MOSAIC="${REG_ROOT}/${MOVING_PATH}"
OUTPUT_PREFIX="${REG_ROOT}/${OUTPUT_WORKDIR}/${OUTPUT_LABEL}"
TRANSFORM_JSON="${OUTPUT_PREFIX}.matlab.transform.json"
SUMMARY_CSV="${OUTPUT_PREFIX}.matlab.transform.csv"
ROI_CSV="${OUTPUT_PREFIX}.matlab.roi_diagnostics.csv"
REGISTERED_MOSAIC="${OUTPUT_PREFIX}.matlab.registered_moving.ome.tif"
APPLICATION_JSON="${OUTPUT_PREFIX}.matlab.application.json"
PREVIEW_TIF="${OUTPUT_PREFIX}.matlab.registered_moving.preview.tif"
QC_PNG="${OUTPUT_PREFIX}.matlab.registration_qc.png"
QC_PDF="${OUTPUT_PREFIX}.matlab.registration_qc.pdf"
print_slurm_info
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] FIXED_PATH=${FIXED_PATH}"
echo "[PARAM] MOVING_PATH=${MOVING_PATH}"
echo "[PARAM] OUTPUT_WORKDIR=${OUTPUT_WORKDIR}"
echo "[PARAM] OUTPUT_LABEL=${OUTPUT_LABEL}"
echo "[PARAM] OVERVIEW_DOWNSAMPLE=${OVERVIEW_DOWNSAMPLE}"
echo "[PARAM] OVERVIEW_BLOCK_PX=${OVERVIEW_BLOCK_PX}"
echo "[PARAM] ROI_SIZE_PX=${ROI_SIZE_PX}"
echo "[PARAM] ROI_COUNT=${ROI_COUNT}"
echo "[PARAM] MIN_VALID_ROIS=${MIN_VALID_ROIS}"
echo "[PARAM] MIN_OVERLAP_RATIO=${MIN_OVERLAP_RATIO}"
echo "[PARAM] MAX_ROI_SPREAD_PX=${MAX_ROI_SPREAD_PX}"
echo "[PARAM] TILE_SIZE_PX=${TILE_SIZE_PX}"
echo "[PARAM] INTERPOLATION_ORDER=${INTERPOLATION_ORDER}"
echo "[PARAM] PREVIEW_DOWNSAMPLE=${PREVIEW_DOWNSAMPLE}"
echo "[PARAM] COMPRESSION=${COMPRESSION}"
echo "[PARAM] OVERWRITE=${OVERWRITE}"
echo "[PARAM] DRY_RUN=${DRY_RUN}"

DFT_HELPER_DIR="${CORE_MATLAB_DIR}/starFinder"
MATLAB_SCRIPT="${SCRIPT_DIR}/p26_register_mosaic_matlab.m"
APPLY_SCRIPT="${SCRIPT_DIR}/p29_apply_mosaic_transform.py"
OVERWRITE_MATLAB="false"
if [[ "$OVERWRITE" == "true" ]]; then
    OVERWRITE_MATLAB="true"
fi
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

echo "[PATH] REG_ROOT=${REG_ROOT}"
echo "[PATH] FIXED_MOSAIC=${FIXED_MOSAIC}"
echo "[PATH] MOVING_MOSAIC=${MOVING_MOSAIC}"
echo "[PATH] OUTPUT_PREFIX=${OUTPUT_PREFIX}"
echo "[PATH] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PATH] CONDA_SH=${CONDA_SH}"
echo "[PATH] CORE_MATLAB_DIR=${CORE_MATLAB_DIR}"
printf '[COMMAND] matlab -batch %q\n' "$MATLAB_BATCH"
printf '[COMMAND] '; printf '%q ' "${APPLY_COMMAND[@]}"; printf '\n'
if [[ "$DRY_RUN" == "true" ]]; then
    FINAL_STATUS="DRY_RUN_DONE"
    exit 0
fi
for path in "$FIXED_MOSAIC" "$MOVING_MOSAIC" "$CONDA_SH" "$MATLAB_SCRIPT" "$APPLY_SCRIPT" "${DFT_HELPER_DIR}/DFTRegister2D.m"; do
    [[ -f "$path" ]] || { echo "Error: missing file: $path" >&2; exit 1; }
done
mkdir -p "$(dirname "$OUTPUT_PREFIX")"
module purge
module load matlab/2023a
matlab -batch "$MATLAB_BATCH"
source "${CONDA_SH}"
set +u
conda activate ashlar
set -u
"${APPLY_COMMAND[@]}"

for path in "$TRANSFORM_JSON" "$SUMMARY_CSV" "$ROI_CSV" "$REGISTERED_MOSAIC" "$APPLICATION_JSON" "$PREVIEW_TIF" "$QC_PNG" "$QC_PDF"; do
    [[ -s "$path" ]] || { echo "Error: missing or empty output: $path" >&2; exit 1; }
done
