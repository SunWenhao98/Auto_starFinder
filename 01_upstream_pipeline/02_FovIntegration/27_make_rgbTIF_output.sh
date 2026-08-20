#!/bin/bash
#SBATCH -J TE_rgb
#SBATCH -o logs_TE_rgb/%x_%A.out
#SBATCH -e logs_TE_rgb/%x_%A.err
#SBATCH -p C64M512G
#SBATCH --qos=normal
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --no-requeue
#SBATCH --export=ALL

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 27_make_rgbTIF_output.sh --red_image FILE --green_image FILE --output_image FILE [options]

Combine TE-nt and TE-rb stitched images into an RGB image.

Required:
  --red_image FILE           Red-channel stitched image, usually TE-nt
  --green_image FILE         Green-channel stitched image, usually TE-rb
  --output_image FILE        Output RGB OME-TIFF image

Options:
  --rescale_to_uint8 BOOL    Percentile-rescale both channels to uint8 [false]
  --percentile_min FLOAT     Lower percentile for rescaling [0]
  --percentile_max FLOAT     Upper percentile for rescaling [99.9]
  --script_dir PATH          Directory containing p27_make_rgbTIF_output.py
  --conda_env NAME           Conda environment name [ashlar]
  -h, --help                 Show this help and exit
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

### 参数默认值 ---
DEFAULT_SCRIPT_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration"
RED_IMAGE=""
GREEN_IMAGE=""
OUTPUT_IMAGE=""
RESCALE_TO_UINT8="false"
PERCENTILE_MIN="0"
PERCENTILE_MAX="99.9"
SCRIPT_DIR="$DEFAULT_SCRIPT_DIR"
CONDA_ENV="ashlar"

### 参数解析 ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --red_image) RED_IMAGE="$2"; shift 2 ;;
        --green_image) GREEN_IMAGE="$2"; shift 2 ;;
        --output_image) OUTPUT_IMAGE="$2"; shift 2 ;;
        --rescale_to_uint8) RESCALE_TO_UINT8="$2"; shift 2 ;;
        --percentile_min) PERCENTILE_MIN="$2"; shift 2 ;;
        --percentile_max) PERCENTILE_MAX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_env) CONDA_ENV="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: Unknown parameter: $1" >&2; print_usage >&2; exit 1 ;;
    esac
done

### 必填检查 ---
[[ -n "$RED_IMAGE" ]] || { echo "Error: --red_image is required" >&2; exit 1; }
[[ -n "$GREEN_IMAGE" ]] || { echo "Error: --green_image is required" >&2; exit 1; }
[[ -n "$OUTPUT_IMAGE" ]] || { echo "Error: --output_image is required" >&2; exit 1; }

### 环境准备 ---
PY_SCRIPT="${SCRIPT_DIR}/p27_make_rgbTIF_output.py"
LOG_DIR="logs_TE_rgb"

mkdir -p "$LOG_DIR"
start_time=$(date +%s)
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"
print_slurm_info

echo "Load conda environment: ${CONDA_ENV}"
source "/gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh"
set +u
conda activate "$CONDA_ENV"
set -u

### 参数打印 ---
echo "[PARAM] RED_IMAGE=${RED_IMAGE}"
echo "[PARAM] GREEN_IMAGE=${GREEN_IMAGE}"
echo "[PARAM] OUTPUT_IMAGE=${OUTPUT_IMAGE}"
echo "[PARAM] RESCALE_TO_UINT8=${RESCALE_TO_UINT8}"
echo "[PARAM] PERCENTILE_MIN=${PERCENTILE_MIN}"
echo "[PARAM] PERCENTILE_MAX=${PERCENTILE_MAX}"
echo "[PARAM] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PARAM] CONDA_ENV=${CONDA_ENV}"

### 执行 Python ---
PY_ARGS=(
    --red_image "$RED_IMAGE"
    --green_image "$GREEN_IMAGE"
    --output_image "$OUTPUT_IMAGE"
    --percentile_min "$PERCENTILE_MIN"
    --percentile_max "$PERCENTILE_MAX"
)

if is_true "$RESCALE_TO_UINT8"; then
    PY_ARGS+=(--rescale_to_uint8)
fi

echo "Running TE RGB merge"
python -u "$PY_SCRIPT" "${PY_ARGS[@]}"

end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Elapsed time: $((end_time - start_time)) seconds"
