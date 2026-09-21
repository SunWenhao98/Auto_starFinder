#!/bin/bash
#SBATCH -J prepare_tile_config
#SBATCH -o logs012_prepare_tile_config/%x_%A.out
#SBATCH -e logs012_prepare_tile_config/%x_%A.err
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 8
#SBATCH --time=24:00:00

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 12_prepare_tile_config.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME --stitching_workdir NAME --source_channel_dir NAME --match_string TEXT --pixel_size_um FLOAT --image_xy INT --overlap_ratio FLOAT --output_config NAME [options]

Options:
  --invert_y BOOL
  --maf_file FILE
  --position_offset INT
  --microscope MODE
  --run_fiji_fusion_preflight BOOL
  --fiji_fusion_preflight_report NAME
  --script_dir PATH
  --conda_sh PATH
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
CONDA_SH=""
STITCHING_WORKDIR=""
SOURCE_CHANNEL_DIR=""
MATCH_STRING=""
PIXEL_SIZE_UM=""
IMAGE_XY=""
OVERLAP_RATIO=""
OUTPUT_CONFIG=""
INVERT_Y="false"
MAF_FILE=""
POSITION_OFFSET="0"
MICROSCOPE="Leica"
RUN_FIJI_FUSION_PREFLIGHT="true"
FIJI_FUSION_PREFLIGHT_REPORT="fiji_fusion_preflight.json"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --stitching_workdir) STITCHING_WORKDIR="$2"; shift 2 ;;
        --source_channel_dir) SOURCE_CHANNEL_DIR="$2"; shift 2 ;;
        --match_string) MATCH_STRING="$2"; shift 2 ;;
        --pixel_size_um) PIXEL_SIZE_UM="$2"; shift 2 ;;
        --image_xy) IMAGE_XY="$2"; shift 2 ;;
        --overlap_ratio) OVERLAP_RATIO="$2"; shift 2 ;;
        --output_config) OUTPUT_CONFIG="$2"; shift 2 ;;
        --invert_y) INVERT_Y="$2"; shift 2 ;;
        --maf_file) MAF_FILE="$2"; shift 2 ;;
        --position_offset) POSITION_OFFSET="$2"; shift 2 ;;
        --microscope) MICROSCOPE="$2"; shift 2 ;;
        --run_fiji_fusion_preflight) RUN_FIJI_FUSION_PREFLIGHT="$2"; shift 2 ;;
        --fiji_fusion_preflight_report) FIJI_FUSION_PREFLIGHT_REPORT="$2"; shift 2 ;;
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

for value in PROJECT_ROOT PROJECT_NAME REG_DIR_SUFFIX SCRIPT_DIR CONDA_SH STITCHING_WORKDIR SOURCE_CHANNEL_DIR MATCH_STRING PIXEL_SIZE_UM IMAGE_XY OVERLAP_RATIO OUTPUT_CONFIG; do
    [[ -n "${!value}" ]] || { echo "Error: ${value} is required" >&2; exit 1; }
done

REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REG_ROOT="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
WORK_DIR="${REG_ROOT}/${STITCHING_WORKDIR}"
INPUT_DIR="${WORK_DIR}/${SOURCE_CHANNEL_DIR}"
OUTPUT_CONFIG_FILE="${WORK_DIR}/${OUTPUT_CONFIG}"
PREFLIGHT_REPORT_FILE="${WORK_DIR}/${FIJI_FUSION_PREFLIGHT_REPORT}"

COMMON_ARGS=(
    --input_dir "$INPUT_DIR"
    --output_dir "$WORK_DIR"
    --match_string "$MATCH_STRING"
    --pixel_size_um "$PIXEL_SIZE_UM"
    --image_xy "$IMAGE_XY"
    --overlap_ratio "$OVERLAP_RATIO"
)
if [[ "$INVERT_Y" == "true" ]]; then
    COMMON_ARGS+=(--invert_y)
fi

print_slurm_info
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] STITCHING_WORKDIR=${STITCHING_WORKDIR}"
echo "[PARAM] SOURCE_CHANNEL_DIR=${SOURCE_CHANNEL_DIR}"
echo "[PARAM] MATCH_STRING=${MATCH_STRING}"
echo "[PARAM] PIXEL_SIZE_UM=${PIXEL_SIZE_UM}"
echo "[PARAM] IMAGE_XY=${IMAGE_XY}"
echo "[PARAM] OVERLAP_RATIO=${OVERLAP_RATIO}"
echo "[PARAM] OUTPUT_CONFIG=${OUTPUT_CONFIG}"
echo "[PARAM] INVERT_Y=${INVERT_Y}"
echo "[PARAM] MAF_FILE=${MAF_FILE}"
echo "[PARAM] POSITION_OFFSET=${POSITION_OFFSET}"
echo "[PARAM] MICROSCOPE=${MICROSCOPE}"
echo "[PARAM] RUN_FIJI_FUSION_PREFLIGHT=${RUN_FIJI_FUSION_PREFLIGHT}"

case "$MICROSCOPE" in
    Leica)
        PY_SCRIPT="${SCRIPT_DIR}/p12_leica2Stitching_configuration.py"
        MICROSCOPE_ARGS=(--maf_file "$MAF_FILE" --position_offset "$POSITION_OFFSET" --project_name "$PROJECT_NAME")
        ;;
    Olympus)
        PY_SCRIPT="${SCRIPT_DIR}/p12_vsi2Stitching_configuration.py"
        MICROSCOPE_ARGS=()
        ;;
    *) echo "Error: unsupported --microscope: $MICROSCOPE" >&2; exit 1 ;;
esac

echo "[PATH] REG_ROOT=${REG_ROOT}"
echo "[PATH] WORK_DIR=${WORK_DIR}"
echo "[PATH] INPUT_DIR=${INPUT_DIR}"
echo "[PATH] OUTPUT_CONFIG_FILE=${OUTPUT_CONFIG_FILE}"
echo "[PATH] PREFLIGHT_REPORT_FILE=${PREFLIGHT_REPORT_FILE}"
echo "[PATH] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PATH] CONDA_SH=${CONDA_SH}"
echo "[PATH] PY_SCRIPT=${PY_SCRIPT}"

[[ -d "$INPUT_DIR" ]] || { echo "Error: input directory not found: $INPUT_DIR" >&2; exit 1; }
[[ -f "$PY_SCRIPT" ]] || { echo "Error: runner not found: $PY_SCRIPT" >&2; exit 1; }
[[ -f "$CONDA_SH" ]] || { echo "Error: conda initialization script not found: $CONDA_SH" >&2; exit 1; }

source "$CONDA_SH"
set +u
conda activate data_analysis_env
set -u

python -u "$PY_SCRIPT" "${COMMON_ARGS[@]}" "${MICROSCOPE_ARGS[@]}"
cp "${WORK_DIR}/TileConfiguration.txt" "$OUTPUT_CONFIG_FILE"
echo "OUTPUT_CONFIG: ${OUTPUT_CONFIG_FILE}"
[[ -s "$OUTPUT_CONFIG_FILE" ]] || { echo "Error: output config missing or empty: $OUTPUT_CONFIG_FILE" >&2; exit 1; }

if [[ "$RUN_FIJI_FUSION_PREFLIGHT" == "true" ]]; then
    python -u "${SCRIPT_DIR}/p12_check_fiji_fusion_size.py" \
        --config_file "$OUTPUT_CONFIG_FILE" \
        --image_xy "$IMAGE_XY" \
        --report_file "$PREFLIGHT_REPORT_FILE"
    [[ -s "$PREFLIGHT_REPORT_FILE" ]] || { echo "Error: preflight report missing or empty: $PREFLIGHT_REPORT_FILE" >&2; exit 1; }
fi
