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
Usage: 31_ashlar_stitch_joint.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME --stitching_workdir NAME --ref_channel_dir DIR --if_channel_dir DIR --input_config NAME [options]

Joint ashlar stitching of the reference round and the IF round: one solve for
all FOVs of both rounds, output TileConfigurations share one coordinate frame.

Options:
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
REF_CHANNEL_DIR=""
IF_CHANNEL_DIR=""
INPUT_CONFIG=""
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
        --ref_channel_dir) REF_CHANNEL_DIR="$2"; shift 2 ;;
        --if_channel_dir) IF_CHANNEL_DIR="$2"; shift 2 ;;
        --input_config) INPUT_CONFIG="$2"; shift 2 ;;
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

for value in PROJECT_ROOT PROJECT_NAME REG_DIR_SUFFIX SCRIPT_DIR CONDA_SH STITCHING_WORKDIR REF_CHANNEL_DIR IF_CHANNEL_DIR INPUT_CONFIG; do
    [[ -n "${!value}" ]] || { echo "Error: ${value} is required" >&2; exit 1; }
done
REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REG_ROOT="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
WORK_DIR="${REG_ROOT}/${STITCHING_WORKDIR}"
REF_DIR="${WORK_DIR}/${REF_CHANNEL_DIR}"
IF_DIR="${WORK_DIR}/${IF_CHANNEL_DIR}"
INPUT_CONFIG_FILE="${WORK_DIR}/${INPUT_CONFIG}"
OUTPUT_REF_CONFIG_FILE="${WORK_DIR}/${OUTPUT_REF_CONFIG}"
OUTPUT_IF_CONFIG_FILE="${WORK_DIR}/${OUTPUT_IF_CONFIG}"
SUMMARY_FILE="${WORK_DIR}/${OUTPUT_PREFIX}_summary.json"

print_slurm_info
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] STITCHING_WORKDIR=${STITCHING_WORKDIR}"
echo "[PARAM] REF_CHANNEL_DIR=${REF_CHANNEL_DIR}"
echo "[PARAM] IF_CHANNEL_DIR=${IF_CHANNEL_DIR}"
echo "[PARAM] INPUT_CONFIG=${INPUT_CONFIG}"
echo "[PARAM] OUTPUT_REF_CONFIG=${OUTPUT_REF_CONFIG}"
echo "[PARAM] OUTPUT_IF_CONFIG=${OUTPUT_IF_CONFIG}"
echo "[PARAM] OUTPUT_PREFIX=${OUTPUT_PREFIX}"
echo "[PARAM] MAX_SHIFT_FRAC=${MAX_SHIFT_FRAC}"
echo "[PARAM] FILTER_SIGMA=${FILTER_SIGMA}"
echo "[PARAM] ROTATION_THRESHOLD_MDEG=${ROTATION_THRESHOLD_MDEG}"
echo "[PARAM] ROTATE90=${ROTATE90}"

PY_SCRIPT="${SCRIPT_DIR}/p31_ashlar_stitch_joint.py"
PY_ARGS=(
    --ref_dir "$REF_DIR"
    --if_dir "$IF_DIR"
    --config_file "$INPUT_CONFIG_FILE"
    --output_dir "$WORK_DIR"
    --prefix "$OUTPUT_PREFIX"
    --ref_config_name "$OUTPUT_REF_CONFIG"
    --if_config_name "$OUTPUT_IF_CONFIG"
    --max_shift_frac "$MAX_SHIFT_FRAC"
    --filter_sigma "$FILTER_SIGMA"
    --rotation_threshold_mdeg "$ROTATION_THRESHOLD_MDEG"
)
if [[ "$ROTATE90" == "true" ]]; then
    PY_ARGS+=(--rotate90)
fi

echo "[PATH] REG_ROOT=${REG_ROOT}"
echo "[PATH] WORK_DIR=${WORK_DIR}"
echo "[PATH] REF_DIR=${REF_DIR}"
echo "[PATH] IF_DIR=${IF_DIR}"
echo "[PATH] INPUT_CONFIG_FILE=${INPUT_CONFIG_FILE}"
echo "[PATH] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PATH] CONDA_SH=${CONDA_SH}"
echo "[PATH] PY_SCRIPT=${PY_SCRIPT}"
for path in "$REF_DIR" "$IF_DIR" "$INPUT_CONFIG_FILE" "$CONDA_SH" "$PY_SCRIPT"; do
    [[ -e "$path" ]] || { echo "Error: missing input: $path" >&2; exit 1; }
done
source "$CONDA_SH"
set +u
conda activate ashlar
set -u
python -u "$PY_SCRIPT" "${PY_ARGS[@]}"
for path in "$OUTPUT_REF_CONFIG_FILE" "$OUTPUT_IF_CONFIG_FILE" "$SUMMARY_FILE"; do
    [[ -s "$path" ]] || { echo "Error: joint output missing or empty: $path" >&2; exit 1; }
done
