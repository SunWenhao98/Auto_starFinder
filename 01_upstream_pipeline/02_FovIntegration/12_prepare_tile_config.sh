#!/bin/bash
#SBATCH -J prepare_tile_config
#SBATCH -o logs_prepare_tile_config/%x_%A.out
#SBATCH -e logs_prepare_tile_config/%x_%A.err
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8

#SBATCH --time=24:00:00
#SBATCH --no-requeue
#SBATCH --export=ALL

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 12_prepare_tile_config.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME --stitching_workdir NAME --source_channel_dir NAME --match_string TEXT --pixel_size_um FLOAT --image_xy INT --overlap_ratio FLOAT [options]

Generate the initial Fiji/Ashlar TileConfiguration from microscope metadata.

Required:
  --project_root PATH                   Project root directory
  --project_name NAME                   Project/sample name under project_root
  --reg_dir_suffix NAME                 Registration directory name
  --stitching_workdir NAME              Work directory under the registration directory
  --source_channel_dir NAME             Source channel directory under the work directory
  --match_string TEXT                   Image filename match token
  --pixel_size_um FLOAT                 Pixel size in um/pixel
  --image_xy INT                        Tile XY size in pixels
  --overlap_ratio FLOAT                 Expected tile overlap ratio

Options:
  --invert_y BOOL                       Invert Y coordinates [false]
  --maf_file FILE                       Leica metadata file []
  --position_offset INT                 Position ID offset [0]
  --microscope MODE                     Leica or Olympus [Leica]
  --initial_config_name NAME            Published initial config [TileConfiguration.initial.txt]
  --script_dir PATH                     Directory containing p12 scripts
  --conda_env NAME                      Conda environment [bioformats_env]
  --run_fiji_fusion_preflight BOOL      Compute ImageJ fusion-size report [true]
  --fiji_fusion_preflight_report NAME   JSON report filename [fiji_fusion_preflight.json]
  -h, --help                            Show this help and exit
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
PROJECT_ROOT=""
PROJECT_NAME=""
REG_DIR_SUFFIX=""
STITCHING_WORKDIR=""
SOURCE_CHANNEL_DIR=""
MATCH_STRING=""
PIXEL_SIZE_UM=""
IMAGE_XY=""
OVERLAP_RATIO=""
INVERT_Y="false"
MAF_FILE=""
POSITION_OFFSET="0"
MICROSCOPE="Leica"
INITIAL_CONFIG_NAME="TileConfiguration.initial.txt"
SCRIPT_DIR="$DEFAULT_SCRIPT_DIR"
CONDA_ENV="bioformats_env"
RUN_FIJI_FUSION_PREFLIGHT="true"
FIJI_FUSION_PREFLIGHT_REPORT="fiji_fusion_preflight.json"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --stitching_workdir) STITCHING_WORKDIR="$2"; shift 2 ;;
        --source_channel_dir) SOURCE_CHANNEL_DIR="$2"; shift 2 ;;
        --match_string) MATCH_STRING="$2"; shift 2 ;;
        --pixel_size_um) PIXEL_SIZE_UM="$2"; shift 2 ;;
        --image_xy) IMAGE_XY="$2"; shift 2 ;;
        --overlap_ratio) OVERLAP_RATIO="$2"; shift 2 ;;
        --invert_y) INVERT_Y="$2"; shift 2 ;;
        --maf_file) MAF_FILE="$2"; shift 2 ;;
        --position_offset) POSITION_OFFSET="$2"; shift 2 ;;
        --microscope) MICROSCOPE="$2"; shift 2 ;;
        --initial_config_name) INITIAL_CONFIG_NAME="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_env) CONDA_ENV="$2"; shift 2 ;;
        --run_fiji_fusion_preflight) RUN_FIJI_FUSION_PREFLIGHT="$2"; shift 2 ;;
        --fiji_fusion_preflight_report) FIJI_FUSION_PREFLIGHT_REPORT="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: Unknown parameter: $1" >&2; print_usage >&2; exit 1 ;;
    esac
done

for required_name in PROJECT_ROOT PROJECT_NAME REG_DIR_SUFFIX STITCHING_WORKDIR SOURCE_CHANNEL_DIR MATCH_STRING PIXEL_SIZE_UM IMAGE_XY OVERLAP_RATIO; do
    [[ -n "${!required_name}" ]] || { echo "Error: --${required_name,,} is required" >&2; exit 1; }
done
is_true "$INVERT_Y" || true
is_true "$RUN_FIJI_FUSION_PREFLIGHT" || true

WORK_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/${REG_DIR_SUFFIX}/${STITCHING_WORKDIR}"
INPUT_DIR="${WORK_DIR}/${SOURCE_CHANNEL_DIR}"
OUTPUT_DIR="$WORK_DIR"
INITIAL_CONFIG_FILE="${WORK_DIR}/${INITIAL_CONFIG_NAME}"
PREFLIGHT_REPORT_FILE="${WORK_DIR}/${FIJI_FUSION_PREFLIGHT_REPORT}"
LOG_DIR="logs_prepare_tile_config"

mkdir -p "$LOG_DIR"
start_time=$(date +%s)
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"
print_slurm_info

echo "Load conda environment: ${CONDA_ENV}"
source "/gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh"
set +u
conda activate "$CONDA_ENV"
set -u

echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] REG_DIR_SUFFIX=${REG_DIR_SUFFIX}"
echo "[PARAM] STITCHING_WORKDIR=${STITCHING_WORKDIR}"
echo "[PARAM] SOURCE_CHANNEL_DIR=${SOURCE_CHANNEL_DIR}"
echo "[PARAM] INPUT_DIR=${INPUT_DIR}"
echo "[PARAM] OUTPUT_DIR=${OUTPUT_DIR}"
echo "[PARAM] MATCH_STRING=${MATCH_STRING}"
echo "[PARAM] PIXEL_SIZE_UM=${PIXEL_SIZE_UM}"
echo "[PARAM] IMAGE_XY=${IMAGE_XY}"
echo "[PARAM] OVERLAP_RATIO=${OVERLAP_RATIO}"
echo "[PARAM] INVERT_Y=${INVERT_Y}"
echo "[PARAM] MAF_FILE=${MAF_FILE}"
echo "[PARAM] POSITION_OFFSET=${POSITION_OFFSET}"
echo "[PARAM] MICROSCOPE=${MICROSCOPE}"
echo "[PARAM] INITIAL_CONFIG_FILE=${INITIAL_CONFIG_FILE}"
echo "[PARAM] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PARAM] RUN_FIJI_FUSION_PREFLIGHT=${RUN_FIJI_FUSION_PREFLIGHT}"
echo "[PARAM] PREFLIGHT_REPORT_FILE=${PREFLIGHT_REPORT_FILE}"

COMMON_ARGS=(
    --input_dir "$INPUT_DIR"
    --output_dir "$OUTPUT_DIR"
    --match_string "$MATCH_STRING"
    --pixel_size_um "$PIXEL_SIZE_UM"
    --image_xy "$IMAGE_XY"
    --overlap_ratio "$OVERLAP_RATIO"
)
if is_true "$INVERT_Y"; then
    COMMON_ARGS+=(--invert_y)
fi

case "$MICROSCOPE" in
    Leica)
        PY_SCRIPT="${SCRIPT_DIR}/p12_leica2Stitching_configuration.py"
        python -u "$PY_SCRIPT" "${COMMON_ARGS[@]}" \
            --maf_file "$MAF_FILE" \
            --position_offset "$POSITION_OFFSET"
        ;;
    Olympus)
        PY_SCRIPT="${SCRIPT_DIR}/p12_vsi2Stitching_configuration.py"
        python -u "$PY_SCRIPT" "${COMMON_ARGS[@]}"
        ;;
    *)
        echo "Error: Unsupported --microscope: $MICROSCOPE" >&2
        echo "Supported modes: Leica, Olympus" >&2
        exit 1
        ;;
esac

cp "${WORK_DIR}/TileConfiguration.txt" "$INITIAL_CONFIG_FILE"
echo "INITIAL_CONFIG: ${INITIAL_CONFIG_FILE}"

if is_true "$RUN_FIJI_FUSION_PREFLIGHT"; then
    python -u "${SCRIPT_DIR}/p12_check_fiji_fusion_size.py" \
        --config_file "$INITIAL_CONFIG_FILE" \
        --image_xy "$IMAGE_XY" \
        --report_file "$PREFLIGHT_REPORT_FILE"
else
    echo "FIJI_FUSION_PREFLIGHT: SKIPPED"
fi

end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Elapsed time: $((end_time - start_time)) seconds"
