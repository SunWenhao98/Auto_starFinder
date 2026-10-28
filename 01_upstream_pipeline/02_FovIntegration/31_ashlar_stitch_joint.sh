#!/bin/bash
#SBATCH -J ashlar_joint_stitch
#SBATCH -o logs031_ashlar_joint_stitch/%x_%A.out
#SBATCH -e logs031_ashlar_joint_stitch/%x_%A.err
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 16
#SBATCH --time=24:00:00

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 31_ashlar_stitch_joint.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME --stitching_workdir NAME --maf_file FILE [options]

Joint ashlar stitching of the reference round and the IF round: one solve for
all FOVs of both rounds, output TileConfigurations share one coordinate frame.
Reads the raw rounds in place (01_data/round%03d of --ref_round, 01_data/<--if_round>);
no FOV registration or layout step is needed. Positions imaged in both rounds
are used; their nominal TileConfiguration (+ tile_summary.csv) is written from
the MAF into the stitching workdir, as 12 does.

Options:
  --ref_round INT                reference round number (default 1)
  --if_round NAME                IF round directory under 01_data (default IF)
  --ref_channel_token TEXT       raw file token of the ref DAPI channel (default ch03)
  --if_channel_token TEXT        raw file token of the IF DAPI channel (default ch03)
  --output_config NAME           nominal config (default TileConfiguration.initial.txt)
  --position_offset INT          first MAF point of this sample (default 0)
  --pixel_size_um FLOAT          (default 0.142)
  --image_xy INT                 (default 2048)
  --overlap_ratio FLOAT          (default 0.1)
  --invert_y BOOL
  --microscope MODE              Leica (MAF) only
  --output_ref_config NAME       (default TileConfiguration.joint_ref.txt)
  --output_if_config NAME        (default TileConfiguration.joint_IF.txt)
  --output_prefix PREFIX         diagnostics prefix (default joint_ref-IF)
  --max_shift_frac FLOAT         (default 0.05)
  --filter_sigma FLOAT           (default 3.0)
  --rotation_threshold_mdeg FLOAT  (default 10)
  --rotate90 BOOL
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
REF_ROUND="1"
IF_ROUND="IF"
REF_CHANNEL_TOKEN="ch03"
IF_CHANNEL_TOKEN="ch03"
OUTPUT_CONFIG="TileConfiguration.initial.txt"
MAF_FILE=""
POSITION_OFFSET="0"
PIXEL_SIZE_UM="0.142"
IMAGE_XY="2048"
OVERLAP_RATIO="0.1"
INVERT_Y="false"
MICROSCOPE="Leica"
OUTPUT_REF_CONFIG="TileConfiguration.joint_ref.txt"
OUTPUT_IF_CONFIG="TileConfiguration.joint_IF.txt"
OUTPUT_PREFIX="joint_ref-IF"
MAX_SHIFT_FRAC="0.05"
FILTER_SIGMA="3.0"
ROTATION_THRESHOLD_MDEG="10"
ROTATE90="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --stitching_workdir) STITCHING_WORKDIR="$2"; shift 2 ;;
        --ref_round) REF_ROUND="$2"; shift 2 ;;
        --if_round) IF_ROUND="$2"; shift 2 ;;
        --ref_channel_token) REF_CHANNEL_TOKEN="$2"; shift 2 ;;
        --if_channel_token) IF_CHANNEL_TOKEN="$2"; shift 2 ;;
        --output_config) OUTPUT_CONFIG="$2"; shift 2 ;;
        --maf_file) MAF_FILE="$2"; shift 2 ;;
        --position_offset) POSITION_OFFSET="$2"; shift 2 ;;
        --pixel_size_um) PIXEL_SIZE_UM="$2"; shift 2 ;;
        --image_xy) IMAGE_XY="$2"; shift 2 ;;
        --overlap_ratio) OVERLAP_RATIO="$2"; shift 2 ;;
        --invert_y) INVERT_Y="$2"; shift 2 ;;
        --microscope) MICROSCOPE="$2"; shift 2 ;;
        --output_ref_config) OUTPUT_REF_CONFIG="$2"; shift 2 ;;
        --output_if_config) OUTPUT_IF_CONFIG="$2"; shift 2 ;;
        --output_prefix) OUTPUT_PREFIX="$2"; shift 2 ;;
        --max_shift_frac) MAX_SHIFT_FRAC="$2"; shift 2 ;;
        --filter_sigma) FILTER_SIGMA="$2"; shift 2 ;;
        --rotation_threshold_mdeg) ROTATION_THRESHOLD_MDEG="$2"; shift 2 ;;
        --rotate90) ROTATE90="$2"; shift 2 ;;
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

for value in PROJECT_ROOT PROJECT_NAME REG_DIR_SUFFIX SCRIPT_DIR CONDA_SH STITCHING_WORKDIR MAF_FILE OUTPUT_CONFIG; do
    [[ -n "${!value}" ]] || { echo "Error: ${value} is required" >&2; exit 1; }
done
[[ "$MICROSCOPE" == "Leica" ]] || { echo "Error: --microscope ${MICROSCOPE} is not supported (Leica MAF only)" >&2; exit 1; }
DATA_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/01_data"
REF_ROUND_DIR="${DATA_DIR}/$(printf 'round%03d' "$((10#${REF_ROUND}))")"
IF_ROUND_DIR="${DATA_DIR}/${IF_ROUND}"
REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REG_ROOT="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
WORK_DIR="${REG_ROOT}/${STITCHING_WORKDIR}"
OUTPUT_CONFIG_FILE="${WORK_DIR}/${OUTPUT_CONFIG}"
OUTPUT_REF_CONFIG_FILE="${WORK_DIR}/${OUTPUT_REF_CONFIG}"
OUTPUT_IF_CONFIG_FILE="${WORK_DIR}/${OUTPUT_IF_CONFIG}"
SUMMARY_FILE="${WORK_DIR}/${OUTPUT_PREFIX}_summary.json"

print_slurm_info
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] STITCHING_WORKDIR=${STITCHING_WORKDIR}"
echo "[PARAM] REF_ROUND=${REF_ROUND}"
echo "[PARAM] IF_ROUND=${IF_ROUND}"
echo "[PARAM] REF_CHANNEL_TOKEN=${REF_CHANNEL_TOKEN}"
echo "[PARAM] IF_CHANNEL_TOKEN=${IF_CHANNEL_TOKEN}"
echo "[PARAM] OUTPUT_CONFIG=${OUTPUT_CONFIG}"
echo "[PARAM] MAF_FILE=${MAF_FILE}"
echo "[PARAM] POSITION_OFFSET=${POSITION_OFFSET}"
echo "[PARAM] PIXEL_SIZE_UM=${PIXEL_SIZE_UM}"
echo "[PARAM] IMAGE_XY=${IMAGE_XY}"
echo "[PARAM] OVERLAP_RATIO=${OVERLAP_RATIO}"
echo "[PARAM] INVERT_Y=${INVERT_Y}"
echo "[PARAM] OUTPUT_REF_CONFIG=${OUTPUT_REF_CONFIG}"
echo "[PARAM] OUTPUT_IF_CONFIG=${OUTPUT_IF_CONFIG}"
echo "[PARAM] OUTPUT_PREFIX=${OUTPUT_PREFIX}"
echo "[PARAM] MAX_SHIFT_FRAC=${MAX_SHIFT_FRAC}"
echo "[PARAM] FILTER_SIGMA=${FILTER_SIGMA}"
echo "[PARAM] ROTATION_THRESHOLD_MDEG=${ROTATION_THRESHOLD_MDEG}"
echo "[PARAM] ROTATE90=${ROTATE90}"

PY_SCRIPT="${SCRIPT_DIR}/p31_ashlar_stitch_joint.py"
PY_ARGS=(
    --ref_round_dir "$REF_ROUND_DIR"
    --if_round_dir "$IF_ROUND_DIR"
    --ref_channel "$REF_CHANNEL_TOKEN"
    --if_channel "$IF_CHANNEL_TOKEN"
    --maf_file "$MAF_FILE"
    --position_offset "$POSITION_OFFSET"
    --project_name "$PROJECT_NAME"
    --pixel_size_um "$PIXEL_SIZE_UM"
    --image_xy "$IMAGE_XY"
    --overlap_ratio "$OVERLAP_RATIO"
    --config_name "$OUTPUT_CONFIG"
    --output_dir "$WORK_DIR"
    --prefix "$OUTPUT_PREFIX"
    --ref_config_name "$OUTPUT_REF_CONFIG"
    --if_config_name "$OUTPUT_IF_CONFIG"
    --max_shift_frac "$MAX_SHIFT_FRAC"
    --filter_sigma "$FILTER_SIGMA"
    --rotation_threshold_mdeg "$ROTATION_THRESHOLD_MDEG"
)
if [[ "$INVERT_Y" == "true" ]]; then
    PY_ARGS+=(--invert_y)
fi
if [[ "$ROTATE90" == "true" ]]; then
    PY_ARGS+=(--rotate90)
fi

echo "[PATH] REF_ROUND_DIR=${REF_ROUND_DIR}"
echo "[PATH] IF_ROUND_DIR=${IF_ROUND_DIR}"
echo "[PATH] REG_ROOT=${REG_ROOT}"
echo "[PATH] WORK_DIR=${WORK_DIR}"
echo "[PATH] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PATH] CONDA_SH=${CONDA_SH}"
echo "[PATH] PY_SCRIPT=${PY_SCRIPT}"
for path in "$REF_ROUND_DIR" "$IF_ROUND_DIR" "$MAF_FILE" "$CONDA_SH" "$PY_SCRIPT"; do
    [[ -e "$path" ]] || { echo "Error: missing input: $path" >&2; exit 1; }
done
mkdir -p "$WORK_DIR"
source "$CONDA_SH"
set +u
conda activate ashlar
set -u
python -u "$PY_SCRIPT" "${PY_ARGS[@]}"
for path in "$OUTPUT_CONFIG_FILE" "$OUTPUT_REF_CONFIG_FILE" "$OUTPUT_IF_CONFIG_FILE" "$SUMMARY_FILE"; do
    [[ -s "$path" ]] || { echo "Error: joint output missing or empty: $path" >&2; exit 1; }
done
