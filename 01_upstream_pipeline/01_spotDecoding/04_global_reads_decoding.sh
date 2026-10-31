#!/bin/bash
#SBATCH -J gRD
#SBATCH -o logs004_global_reads_decoding/%x_%A_%a.out
#SBATCH -e logs004_global_reads_decoding/%x_%A_%a.err
#SBATCH -p C64M512G
#SBATCH -N 1
#SBATCH -c 8
#SBATCH --time=24:00:00
#SBATCH --array=1-25%25

set -euo pipefail

print_usage() {
    echo "Usage: $0 --project_root PATH --project_name NAME --reg_dir_suffix SUFFIX [options]"
    echo "  --intensityThresh_PR VALUE  Minimum max-channel neighborhood sum in every decoded round (default: 0)."
    echo "  --save_decode_evidence true  Export tri candidate evidence for threshold studies (default: false)."
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
IMAGE_WIDTH="2304"
IMAGE_DEPTH="38"
REF_ROUND="1"
CHANNEL_NUM="3"
ROUND_NUM="6"
INTENSITY_THRESHOLD="0.2"
SPOTFINDING_METHOD="max3d"
DECODING_MODE="normal"
CODEMAP_MODE="Olympus"
LOADING_MODE="local_registration"
INTENSITY_THRESH_PR="0"
SAVE_DECODE_EVIDENCE="false"
VOXELSIZE="1,1,1"
DECODING_ROUNDS="11"
OFFSET="0"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --core_matlab_dir) CORE_MATLAB_DIR="$2"; shift 2 ;;
        --image_width) IMAGE_WIDTH="$2"; shift 2 ;;
        --image_depth) IMAGE_DEPTH="$2"; shift 2 ;;
        --ref_round) REF_ROUND="$2"; shift 2 ;;
        --channel_num) CHANNEL_NUM="$2"; shift 2 ;;
        --round_num) ROUND_NUM="$2"; shift 2 ;;
        --intensity_threshold) INTENSITY_THRESHOLD="$2"; shift 2 ;;
        --spotfinding_method) SPOTFINDING_METHOD="$2"; shift 2 ;;
        --decoding_mode) DECODING_MODE="$2"; shift 2 ;;
        --codeMap_mode) CODEMAP_MODE="$2"; shift 2 ;;
        --loading_mode) LOADING_MODE="$2"; shift 2 ;;
        --intensityThresh_PR) INTENSITY_THRESH_PR="$2"; shift 2 ;;
        --save_decode_evidence) SAVE_DECODE_EVIDENCE="$2"; shift 2 ;;
        --voxelsize) VOXELSIZE="$2"; shift 2 ;;
        --decoding_rounds) DECODING_ROUNDS="$2"; shift 2 ;;
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

# Keep the six existing decoding modes distinct and data-driven.
case "${DECODING_MODE}" in
    seqD)
        END_BASES="['G','A']"
        BARCODE_MODE="regular"
        SPLIT_LOC="[]"
        ;;
    seqF)
        END_BASES="['A','A']"
        BARCODE_MODE="regular"
        SPLIT_LOC="[]"
        ;;
    seqF_real)
        END_BASES="['A','A']"
        BARCODE_MODE="regular"
        SPLIT_LOC="[]"
        ;;
    seqDF)
        END_BASES="['G','A','A','A']"
        BARCODE_MODE="double"
        SPLIT_LOC="6"
        ;;
    normal)
        END_BASES="['G','G','A','A','A']"
        BARCODE_MODE="tri"
        SPLIT_LOC="[6,12]"
        ;;
    seqD_nc)
        END_BASES="['G','A']"
        BARCODE_MODE="single_nc"
        SPLIT_LOC="2"
        ;;
    *)
        echo "Unknown decoding mode: ${DECODING_MODE}" >&2
        exit 1
        ;;
esac

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
VOXEL_SIZE="[${VOXELSIZE}]"

print_slurm_info
echo "PROJECT_ROOT=${PROJECT_ROOT}"
echo "PROJECT_NAME=${PROJECT_NAME}"
echo "REGISTRATION_FOLDER=${REGISTRATION_FOLDER}"
echo "REGISTRATION_DIR=${REGISTRATION_DIR}"
echo "TASK_ID=${TASK_ID}"
echo "POSITION_NAME=${POSITION_NAME}"
echo "IMAGE_WIDTH=${IMAGE_WIDTH}"
echo "IMAGE_DEPTH=${IMAGE_DEPTH}"
echo "REF_ROUND=${REF_ROUND}"
echo "CHANNEL_NUM=${CHANNEL_NUM}"
echo "ROUND_NUM=${ROUND_NUM}"
echo "INTENSITY_THRESHOLD=${INTENSITY_THRESHOLD}"
echo "SPOTFINDING_METHOD=${SPOTFINDING_METHOD}"
echo "DECODING_MODE=${DECODING_MODE}"
echo "CODEMAP_MODE=${CODEMAP_MODE}"
echo "LOADING_MODE=${LOADING_MODE}"
echo "INTENSITY_THRESH_PR=${INTENSITY_THRESH_PR}"
echo "INTENSITY_FILTER=all_decoded_rounds_max_channel_neighborhood_sum"
echo "SAVE_DECODE_EVIDENCE=${SAVE_DECODE_EVIDENCE}"
echo "VOXELSIZE=${VOXELSIZE}"
echo "DECODING_ROUNDS=${DECODING_ROUNDS}"
echo "OFFSET=${OFFSET}"
echo "END_BASES=${END_BASES}"
echo "BARCODE_MODE=${BARCODE_MODE}"
echo "SPLIT_LOC=${SPLIT_LOC}"
echo "CORE_MATLAB_DIR=${CORE_MATLAB_DIR}"

MATLAB_SAVE_DECODE_EVIDENCE=false
if [[ "${SAVE_DECODE_EVIDENCE,,}" == "true" ]]; then
    MATLAB_SAVE_DECODE_EVIDENCE=true
fi

module purge
module load matlab/2023a

matlab -batch "addpath(genpath('$CORE_MATLAB_DIR')); core_matlab_new('$PROJECT_NAME', 'global_reads_decoding', '$POSITION_NAME', $IMAGE_WIDTH, $IMAGE_DEPTH, $REF_ROUND, $CHANNEL_NUM, $ROUND_NUM, '$PROJECT_ROOT', '01_data', '$REGISTRATION_FOLDER', 'log', 'spotfinding_method', '$SPOTFINDING_METHOD', 'voxel_size', $VOXEL_SIZE, 'end_bases', $END_BASES, 'barcode_mode', '$BARCODE_MODE', 'split_loc', $SPLIT_LOC, 'intensity_threshold', $INTENSITY_THRESHOLD, 'IntensityThresh_perRound', $INTENSITY_THRESH_PR, 'loading_mode', '$LOADING_MODE', 'codeMap_mode', '$CODEMAP_MODE', 'decoding_rounds', $DECODING_ROUNDS, 'save_decode_evidence', $MATLAB_SAVE_DECODE_EVIDENCE)"
