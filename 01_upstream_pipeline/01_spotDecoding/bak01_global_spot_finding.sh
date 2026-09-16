#!/bin/bash
#SBATCH -J gSPF
#SBATCH -o logs004_global_spot_finding/%x_%A_%a.out
#SBATCH -e logs004_global_spot_finding/%x_%A_%a.err
#SBATCH -p C64M512G
#SBATCH -c 4
#SBATCH --time=24:00:00
#SBATCH --array=1-25%25

set -euo pipefail

print_usage() {
    echo "Usage: $0 --project_root PATH --project_name NAME --reg_dir_suffix SUFFIX [options]"
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
INTENSITY_THRESHOLD="0.2"
SPOTFINDING_METHOD="max3d"
LOADING_MODE="local_registration"
IMAGE_WIDTH="2304"
IMAGE_DEPTH="38"
REF_ROUND="1"
CHANNEL_NUM="3"
ROUND_NUM="6"
OFFSET="0"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --core_matlab_dir) CORE_MATLAB_DIR="$2"; shift 2 ;;
        --intensity_threshold) INTENSITY_THRESHOLD="$2"; shift 2 ;;
        --spotfinding_method) SPOTFINDING_METHOD="$2"; shift 2 ;;
        --loading_mode) LOADING_MODE="$2"; shift 2 ;;
        --image_width) IMAGE_WIDTH="$2"; shift 2 ;;
        --image_depth) IMAGE_DEPTH="$2"; shift 2 ;;
        --ref_round) REF_ROUND="$2"; shift 2 ;;
        --channel_num) CHANNEL_NUM="$2"; shift 2 ;;
        --round_num) ROUND_NUM="$2"; shift 2 ;;
        --offset) OFFSET="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) print_usage >&2; exit 2 ;;
    esac
done

if [[ -z "${CORE_MATLAB_DIR}" || ! -d "${CORE_MATLAB_DIR}" ]]; then
    echo "--core_matlab_dir must be an existing directory." >&2
    exit 2
fi

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

# Resolve the logical task to a sorted Position directory.
TASK_ID=$((SLURM_ARRAY_TASK_ID + OFFSET))
POSITION_INDEX=$((TASK_ID - 1))
DATA_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/round001"
readarray -t POSITIONS < <(find -L "${DATA_DIR}" -maxdepth 1 -type d -name "Position*" | sort -V)
if (( POSITION_INDEX < 0 || POSITION_INDEX >= ${#POSITIONS[@]} )); then
    echo "Task ID ${TASK_ID} is outside the available Position range." >&2
    exit 1
fi
POSITION_NAME=$(basename "${POSITIONS[POSITION_INDEX]}")
REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REGISTRATION_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"

module purge
module load matlab/2023a

print_slurm_info
echo "PROJECT_ROOT=${PROJECT_ROOT}"
echo "PROJECT_NAME=${PROJECT_NAME}"
echo "REGISTRATION_FOLDER=${REGISTRATION_FOLDER}"
echo "REGISTRATION_DIR=${REGISTRATION_DIR}"
echo "TASK_ID=${TASK_ID}"
echo "POSITION_NAME=${POSITION_NAME}"
echo "INTENSITY_THRESHOLD=${INTENSITY_THRESHOLD}"
echo "SPOTFINDING_METHOD=${SPOTFINDING_METHOD}"
echo "LOADING_MODE=${LOADING_MODE}"
echo "IMAGE_WIDTH=${IMAGE_WIDTH}"
echo "IMAGE_DEPTH=${IMAGE_DEPTH}"
echo "REF_ROUND=${REF_ROUND}"
echo "CHANNEL_NUM=${CHANNEL_NUM}"
echo "ROUND_NUM=${ROUND_NUM}"
echo "OFFSET=${OFFSET}"
echo "CORE_MATLAB_DIR=${CORE_MATLAB_DIR}"

matlab -batch "addpath(genpath('$CORE_MATLAB_DIR')); core_matlab_new('$PROJECT_NAME', 'global_spot_finding', '$POSITION_NAME', $IMAGE_WIDTH, $IMAGE_DEPTH, $REF_ROUND, $CHANNEL_NUM, $ROUND_NUM, '$PROJECT_ROOT', '01_data', '$REGISTRATION_FOLDER', 'log', 'spotfinding_method', '$SPOTFINDING_METHOD', 'intensity_threshold', $INTENSITY_THRESHOLD, 'loading_mode', '$LOADING_MODE')"
