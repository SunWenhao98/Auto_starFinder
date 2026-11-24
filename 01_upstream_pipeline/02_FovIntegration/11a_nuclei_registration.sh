#!/bin/bash
#SBATCH -J Nuclei_based_Registration
#SBATCH -o logs011a_nuclei_registration/%x_%A_%a.out
#SBATCH -e logs011a_nuclei_registration/%x_%A_%a.err
#SBATCH -p C64M512G
#SBATCH -c 4
#SBATCH --time=24:00:00
#SBATCH --array=1-1

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 11a_nuclei_registration.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME [options]

Options:
  --offset INT
  --image_width INT
  --image_depth INT
  --ref_round INT
  --channel_num INT
  --round_num INT
  --ref_input_format FORMAT    Reference TIFF input type (default: uint16).
  --moving_input_format FORMAT Moving TIFF input type (default: uint16).
  --norm_out_format FORMAT     Working image type (default: uint16, preserves uint8/16 values).
  --aligned_round_outdir NAME  Image output only when --apply_and_save_images is true.
  --moving_round NAME
  --channel_panel MODE
  --apply_and_save_images BOOL  Apply shifts and save all images (default: false).
  --core_matlab_dir PATH
  -h, --help

The shift log is named by the reference and moving rounds. A successful run
replaces only that Position's canonical log for the same round pair.
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
CORE_MATLAB_DIR=""
OFFSET="0"
IMAGE_WIDTH="2304"
IMAGE_DEPTH="38"
REF_ROUND="1"
CHANNEL_NUM="3"
ROUND_NUM="6"
REF_INPUT_FORMAT="uint16"
MOVING_INPUT_FORMAT="uint16"
NORM_OUT_FORMAT="uint16"
ALIGNED_ROUND_OUTDIR="IF"
MOVING_ROUND="IF"
CHANNEL_PANEL="OlympusIF"
APPLY_AND_SAVE_IMAGES="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --core_matlab_dir) CORE_MATLAB_DIR="$2"; shift 2 ;;
        --offset) OFFSET="$2"; shift 2 ;;
        --image_width) IMAGE_WIDTH="$2"; shift 2 ;;
        --image_depth) IMAGE_DEPTH="$2"; shift 2 ;;
        --ref_round) REF_ROUND="$2"; shift 2 ;;
        --channel_num) CHANNEL_NUM="$2"; shift 2 ;;
        --round_num) ROUND_NUM="$2"; shift 2 ;;
        --ref_input_format) REF_INPUT_FORMAT="$2"; shift 2 ;;
        --moving_input_format) MOVING_INPUT_FORMAT="$2"; shift 2 ;;
        --norm_out_format) NORM_OUT_FORMAT="$2"; shift 2 ;;
        --aligned_round_outdir) ALIGNED_ROUND_OUTDIR="$2"; shift 2 ;;
        --moving_round) MOVING_ROUND="$2"; shift 2 ;;
        --channel_panel) CHANNEL_PANEL="$2"; shift 2 ;;
        --apply_and_save_images) APPLY_AND_SAVE_IMAGES="$2"; shift 2 ;;
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

for value in PROJECT_ROOT PROJECT_NAME REG_DIR_SUFFIX CORE_MATLAB_DIR; do
    [[ -n "${!value}" ]] || { echo "Error: ${value} is required" >&2; exit 1; }
done

case "$CHANNEL_PANEL" in
    LeicaIF) CHANNEL_PANEL_MATLAB="{'561-CA9', '488-CD144', '647-CD31', 'DAPI'}" ;;
    OlympusIF) CHANNEL_PANEL_MATLAB="{'488-CD144', '561-CA9', '647-CD31', 'DAPI'}" ;;
    LeicaSeqE) CHANNEL_PANEL_MATLAB="{'647-GCnt', '561-GTrb', 'Padlayer', 'DAPI'}" ;;
    *) echo "Error: unsupported --channel_panel: $CHANNEL_PANEL" >&2; exit 1 ;;
esac

TASK_ID=$((SLURM_ARRAY_TASK_ID + OFFSET))
INDEX=$((TASK_ID - 1))
DATA_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/round001"
[[ -d "$DATA_DIR" ]] || { echo "Error: data directory not found: $DATA_DIR" >&2; exit 1; }
readarray -t POSITIONS < <(find -L "$DATA_DIR" -maxdepth 1 -type d -name 'Position*' | sort -V)
(( ${#POSITIONS[@]} > 0 )) || { echo "Error: no Position directories found: $DATA_DIR" >&2; exit 1; }
[[ "$INDEX" -ge 0 && "$INDEX" -lt "${#POSITIONS[@]}" ]] || { echo "Error: array task ${TASK_ID} is outside available positions" >&2; exit 1; }

POSITION_NAME="$(basename "${POSITIONS[$INDEX]}")"
REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REG_ROOT="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
APPLY_AND_SAVE_IMAGES_MATLAB="false"
if [[ "${APPLY_AND_SAVE_IMAGES,,}" == "true" ]]; then
    APPLY_AND_SAVE_IMAGES_MATLAB="true"
fi

print_slurm_info
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] REGISTRATION_FOLDER=${REGISTRATION_FOLDER}"
echo "[PARAM] OFFSET=${OFFSET}"
echo "[PARAM] TASK_ID=${TASK_ID}"
echo "[PARAM] POSITION_NAME=${POSITION_NAME}"
echo "[PARAM] IMAGE_WIDTH=${IMAGE_WIDTH}"
echo "[PARAM] IMAGE_DEPTH=${IMAGE_DEPTH}"
echo "[PARAM] REF_ROUND=${REF_ROUND}"
echo "[PARAM] CHANNEL_NUM=${CHANNEL_NUM}"
echo "[PARAM] ROUND_NUM=${ROUND_NUM}"
echo "[PARAM] REF_INPUT_FORMAT=${REF_INPUT_FORMAT}"
echo "[PARAM] MOVING_INPUT_FORMAT=${MOVING_INPUT_FORMAT}"
echo "[PARAM] NORM_OUT_FORMAT=${NORM_OUT_FORMAT}"
echo "[PARAM] ALIGNED_ROUND_OUTDIR=${ALIGNED_ROUND_OUTDIR}"
echo "[PARAM] MOVING_ROUND=${MOVING_ROUND}"
echo "[PARAM] CHANNEL_PANEL=${CHANNEL_PANEL}"
echo "[PARAM] APPLY_AND_SAVE_IMAGES=${APPLY_AND_SAVE_IMAGES_MATLAB}"
echo "[PARAM] CORE_MATLAB_DIR=${CORE_MATLAB_DIR}"
echo "[PATH] REG_ROOT=${REG_ROOT}"

module purge
module load matlab/2023a

printf -v MATLAB_COMMAND '%s ' \
    "addpath(genpath('$CORE_MATLAB_DIR'));" \
    "core_matlab_new('$PROJECT_NAME', 'nuclei_protein_registration', '$POSITION_NAME'," \
    "$IMAGE_WIDTH, $IMAGE_DEPTH, $REF_ROUND, $CHANNEL_NUM, $ROUND_NUM," \
    "'$PROJECT_ROOT', '01_data', '$REGISTRATION_FOLDER', 'log'," \
    "'moving_round', '$MOVING_ROUND'," \
    "'ref_input_format', '$REF_INPUT_FORMAT'," \
    "'moving_input_format', '$MOVING_INPUT_FORMAT'," \
    "'norm_out_format', '$NORM_OUT_FORMAT'," \
    "'channel_panel', $CHANNEL_PANEL_MATLAB," \
    "'aligned_round_outdir', '$ALIGNED_ROUND_OUTDIR'," \
    "'apply_and_save_images', $APPLY_AND_SAVE_IMAGES_MATLAB);"
matlab -batch "$MATLAB_COMMAND"
