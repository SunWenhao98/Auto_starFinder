#!/bin/bash
#SBATCH -J prepare_if_tileconfig
#SBATCH -o logs_prepare_if_tileconfig/%x_%A.out
#SBATCH -e logs_prepare_if_tileconfig/%x_%A.err
#SBATCH -p C64M256G
#SBATCH --qos=normal
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --no-requeue
#SBATCH --export=ALL

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 23_prepare_moveImages_tileconfig.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME --stitching_workdir NAME --rawdata_round NAME --channel_mode MODE --registered_config_name NAME --shifted_config_name NAME [options]

Prepare raw channel layout and shifted TileConfiguration from registered coordinates.
For full explicit path control, call p23_prepare_moveImages_tileconfig.py directly.

Required:
  --project_root PATH              Project root directory
  --project_name NAME              Project/sample name under project_root
  --reg_dir_suffix NAME            Registration directory name, e.g. 02_registration001_GBM008
  --stitching_workdir NAME         Work directory under registration dir, e.g. IFnew_uint8
  --rawdata_round NAME             Raw round directory under 01_data, e.g. IF or round011
  --channel_mode MODE              LeicaIF, OlympusIF, or LeicaSeqE
  --registered_config_name NAME    Explicit Fiji/Ashlar registered config filename
  --shifted_config_name NAME       Explicit shifted config filename

Path/name options:
  --registration_log_name NAME     Shift log filename [log_protein_registration_<stitching_workdir>.txt]

Behavior options:
  --output_format FORMAT           preserve, uint8, or uint16 [preserve]
  --rotate_shifts BOOL             Rotate IF_registration shift coordinates [false]
  --shift_sign FLOAT               Shift direction multiplier [1.0]
  --script_dir PATH                Directory containing p23_prepare_moveImages_tileconfig.py
  --conda_env NAME                 Conda environment name [ashlar]
  -h, --help                       Show this help and exit
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

resolve_channel_names() {
    case "$1" in
        LeicaIF)
            echo "561-CA9,488-CD144,647-CD31,DAPI"
            ;;
        OlympusIF)
            echo "488-CD144,561-CA9,647-CD31,DAPI"
            ;;
        LeicaSeqE)
            echo "647-GCnt,561-GTrb,Padlayer,DAPI"
            ;;
        *)
            echo "Error: Unsupported channel_mode for step 23: $1" >&2
            echo "Supported modes: LeicaIF, OlympusIF, LeicaSeqE" >&2
            exit 1
            ;;
    esac
}

DEFAULT_SCRIPT_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration"
PROJECT_ROOT=""
PROJECT_NAME=""
REG_DIR_SUFFIX=""
STITCHING_WORKDIR=""
RAWDATA_ROUND=""
CHANNEL_MODE=""
REGISTERED_CONFIG_NAME=""
SHIFTED_CONFIG_NAME=""
REGISTRATION_LOG_NAME=""
OUTPUT_FORMAT="preserve"
ROTATE_SHIFTS="false"
SHIFT_SIGN="1.0"
SCRIPT_DIR="$DEFAULT_SCRIPT_DIR"
CONDA_ENV="ashlar"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --stitching_workdir) STITCHING_WORKDIR="$2"; shift 2 ;;
        --rawdata_round) RAWDATA_ROUND="$2"; shift 2 ;;
        --channel_mode) CHANNEL_MODE="$2"; shift 2 ;;
        --registered_config_name) REGISTERED_CONFIG_NAME="$2"; shift 2 ;;
        --shifted_config_name) SHIFTED_CONFIG_NAME="$2"; shift 2 ;;
        --registration_log_name) REGISTRATION_LOG_NAME="$2"; shift 2 ;;
        --output_format) OUTPUT_FORMAT="$2"; shift 2 ;;
        --rotate_shifts) ROTATE_SHIFTS="$2"; shift 2 ;;
        --shift_sign) SHIFT_SIGN="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_env) CONDA_ENV="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: Unknown parameter: $1" >&2; print_usage >&2; exit 1 ;;
    esac
done

[[ -n "$PROJECT_ROOT" ]] || { echo "Error: --project_root is required" >&2; exit 1; }
[[ -n "$PROJECT_NAME" ]] || { echo "Error: --project_name is required" >&2; exit 1; }
[[ -n "$REG_DIR_SUFFIX" ]] || { echo "Error: --reg_dir_suffix is required" >&2; exit 1; }
[[ -n "$STITCHING_WORKDIR" ]] || { echo "Error: --stitching_workdir is required" >&2; exit 1; }
[[ -n "$RAWDATA_ROUND" ]] || { echo "Error: --rawdata_round is required" >&2; exit 1; }
[[ -n "$CHANNEL_MODE" ]] || { echo "Error: --channel_mode is required" >&2; exit 1; }
[[ -n "$REGISTERED_CONFIG_NAME" ]] || { echo "Error: --registered_config_name is required" >&2; exit 1; }
[[ -n "$SHIFTED_CONFIG_NAME" ]] || { echo "Error: --shifted_config_name is required" >&2; exit 1; }

if [[ -z "$REGISTRATION_LOG_NAME" ]]; then
    REGISTRATION_LOG_NAME="log_protein_registration_${STITCHING_WORKDIR}.txt"
fi

CHANNEL_NAMES="$(resolve_channel_names "$CHANNEL_MODE")"
WORK_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/${REG_DIR_SUFFIX}/${STITCHING_WORKDIR}"
RAW_ROUND_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/${RAWDATA_ROUND}"
REGISTRATION_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/${REG_DIR_SUFFIX}"
REGISTERED_CONFIG="${WORK_DIR}/${REGISTERED_CONFIG_NAME}"

PY_SCRIPT="${SCRIPT_DIR}/p23_prepare_moveImages_tileconfig.py"
LOG_DIR="logs_prepare_if_tileconfig"

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
echo "[PARAM] RAWDATA_ROUND=${RAWDATA_ROUND}"
echo "[PARAM] CHANNEL_MODE=${CHANNEL_MODE}"
echo "[PARAM] CHANNEL_NAMES=${CHANNEL_NAMES}"
echo "[PARAM] REGISTERED_CONFIG_NAME=${REGISTERED_CONFIG_NAME}"
echo "[PARAM] SHIFTED_CONFIG_NAME=${SHIFTED_CONFIG_NAME}"
echo "[PARAM] REGISTRATION_LOG_NAME=${REGISTRATION_LOG_NAME}"
echo "[PARAM] WORK_DIR=${WORK_DIR}"
echo "[PARAM] RAW_ROUND_DIR=${RAW_ROUND_DIR}"
echo "[PARAM] REGISTRATION_DIR=${REGISTRATION_DIR}"
echo "[PARAM] REGISTERED_CONFIG=${REGISTERED_CONFIG}"
echo "[PARAM] OUTPUT_FORMAT=${OUTPUT_FORMAT}"
echo "[PARAM] ROTATE_SHIFTS=${ROTATE_SHIFTS}"
echo "[PARAM] SHIFT_SIGN=${SHIFT_SIGN}"
echo "[PARAM] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PARAM] CONDA_ENV=${CONDA_ENV}"

PY_ARGS=(
    --work_dir "$WORK_DIR"
    --raw_round_dir "$RAW_ROUND_DIR"
    --registration_dir "$REGISTRATION_DIR"
    --registered_config "$REGISTERED_CONFIG"
    --shifted_config_name "$SHIFTED_CONFIG_NAME"
    --registration_log_name "$REGISTRATION_LOG_NAME"
    --channel_names "$CHANNEL_NAMES"
    --output_format "$OUTPUT_FORMAT"
    --shift_sign "$SHIFT_SIGN"
)

if is_true "$ROTATE_SHIFTS"; then
    PY_ARGS+=(--rotate90)
fi

echo "Running raw TileConfiguration preparation"
python -u "$PY_SCRIPT" "${PY_ARGS[@]}"

end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Elapsed time: $((end_time - start_time)) seconds"
