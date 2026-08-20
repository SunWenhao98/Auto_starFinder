#!/bin/bash
#SBATCH -J Nuclei_based_Registration
#SBATCH -o logs_Nuclei_based_Registration/Nuclei_based_Registration_%A_%a.out
#SBATCH -e logs_Nuclei_based_Registration/Nuclei_based_Registration_%A_%a.err
#SBATCH -p C64M512G
#SBATCH -c 4
#SBATCH --time=24:00:00
#SBATCH --array=1-49%25

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 11_nuclei_registration.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME [options]

Run one SLURM array task of nuclei-based round registration.

Required:
  --project_root PATH          Project root directory
  --project_name NAME          Project/sample name under project_root
  --reg_dir_suffix NAME        Registration directory name

Options:
  --offset INT                 Array task offset [0]
  --image_width INT            Image width in pixels [2304]
  --image_depth INT            Number of z slices [38]
  --ref_round INT              Reference round [1]
  --channel_num INT            Number of channels [3]
  --round_num INT              Number of rounds [6]
  --input_format FORMAT        Registration input format [uint16]
  --norm_out_format FORMAT     Normalized output format [uint8]
  --aligned_round_outdir NAME  Aligned round output directory [IF]
  --moving_round NAME          Moving round name [IF]
  --channel_panel MODE         LeicaIF, OlympusIF, or LeicaSeqE [OlympusIF]
  --core_matlab_dir PATH       Directory containing core_matlab_new.m
  -h, --help                   Show this help and exit
USAGE
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
    echo "Number of Nodes: ${SLURM_JOB_NUM_NODES:-}"
    echo "Partition:       ${SLURM_JOB_PARTITION:-}"
    echo "CPUs per task:   ${SLURM_CPUS_PER_TASK:-}"
    echo "Allocated CPUs:  ${SLURM_JOB_CPUS_PER_NODE:-}"
    echo "Memory per node: ${SLURM_MEM_PER_NODE:-} MB"
    echo "==============================================="
}

PROJECT_ROOT=""
PROJECT_NAME=""
REG_DIR_SUFFIX=""
OFFSET="0"
IMAGE_WIDTH="2304"
IMAGE_DEPTH="38"
REF_ROUND="1"
CHANNEL_NUM="3"
ROUND_NUM="6"
INPUT_FORMAT="uint16"
NORM_OUT_FORMAT="uint8"
ALIGNED_ROUND_OUTDIR="IF"
MOVING_ROUND="IF"
CHANNEL_PANEL="OlympusIF"
CORE_MATLAB_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/core_programs"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --offset) OFFSET="$2"; shift 2 ;;
        --image_width) IMAGE_WIDTH="$2"; shift 2 ;;
        --image_depth) IMAGE_DEPTH="$2"; shift 2 ;;
        --ref_round) REF_ROUND="$2"; shift 2 ;;
        --channel_num) CHANNEL_NUM="$2"; shift 2 ;;
        --round_num) ROUND_NUM="$2"; shift 2 ;;
        --input_format) INPUT_FORMAT="$2"; shift 2 ;;
        --norm_out_format) NORM_OUT_FORMAT="$2"; shift 2 ;;
        --aligned_round_outdir) ALIGNED_ROUND_OUTDIR="$2"; shift 2 ;;
        --moving_round) MOVING_ROUND="$2"; shift 2 ;;
        --channel_panel) CHANNEL_PANEL="$2"; shift 2 ;;
        --core_matlab_dir) CORE_MATLAB_DIR="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: Unknown parameter: $1" >&2; print_usage >&2; exit 1 ;;
    esac
done

[[ -n "$PROJECT_ROOT" ]] || { echo "Error: --project_root is required" >&2; exit 1; }
[[ -n "$PROJECT_NAME" ]] || { echo "Error: --project_name is required" >&2; exit 1; }
[[ -n "$REG_DIR_SUFFIX" ]] || { echo "Error: --reg_dir_suffix is required" >&2; exit 1; }

case "$CHANNEL_PANEL" in
    LeicaIF)
        CHANNEL_PANEL_MATLAB="{'561-CA9', '488-CD144', '647-CD31', 'DAPI'}"
        ;;
    OlympusIF)
        CHANNEL_PANEL_MATLAB="{'488-CD144', '561-CA9', '647-CD31', 'DAPI'}"
        ;;
    LeicaSeqE)
        CHANNEL_PANEL_MATLAB="{'647-GCnt', '561-GTrb', 'Padlayer', 'DAPI'}"
        ;;
    *)
        echo "Error: Unsupported --channel_panel: $CHANNEL_PANEL" >&2
        echo "Supported modes: LeicaIF, OlympusIF, LeicaSeqE" >&2
        exit 1
        ;;
esac

module purge
module load matlab/2023a
mkdir -p logs_Nuclei_based_Registration
start_time=$(date +%s)
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"
print_slurm_info

export CORE_MATLAB_DIR
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] REG_DIR_SUFFIX=${REG_DIR_SUFFIX}"
echo "[PARAM] OFFSET=${OFFSET}"
echo "[PARAM] IMAGE_WIDTH=${IMAGE_WIDTH}"
echo "[PARAM] IMAGE_DEPTH=${IMAGE_DEPTH}"
echo "[PARAM] REF_ROUND=${REF_ROUND}"
echo "[PARAM] CHANNEL_NUM=${CHANNEL_NUM}"
echo "[PARAM] ROUND_NUM=${ROUND_NUM}"
echo "[PARAM] INPUT_FORMAT=${INPUT_FORMAT}"
echo "[PARAM] NORM_OUT_FORMAT=${NORM_OUT_FORMAT}"
echo "[PARAM] ALIGNED_ROUND_OUTDIR=${ALIGNED_ROUND_OUTDIR}"
echo "[PARAM] MOVING_ROUND=${MOVING_ROUND}"
echo "[PARAM] CHANNEL_PANEL=${CHANNEL_PANEL}"
echo "[PARAM] CORE_MATLAB_DIR=${CORE_MATLAB_DIR}"

TASK_ID=$((SLURM_ARRAY_TASK_ID + OFFSET))
index=$((TASK_ID - 1))
DATA_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/round001"
declare -a positions
readarray -t positions < <(find "$DATA_DIR" -maxdepth 1 -type d -name "Position*" | sort -V)

if [[ ${#positions[@]} -eq 0 ]]; then
    echo "Error: No 'Position*' folders found in directory ${DATA_DIR}." >&2
    exit 1
fi
if [[ "$index" -lt 0 || "$index" -ge ${#positions[@]} ]]; then
    echo "Error: SLURM_ARRAY_TASK_ID (${TASK_ID}) is out of valid range [1-${#positions[@]}]." >&2
    exit 1
fi

POSITION_NAME=$(basename "${positions[$index]}")
echo "Task ID: ${TASK_ID}"
echo "Selected Position folder: ${POSITION_NAME}"

matlab -batch "addpath(genpath('$CORE_MATLAB_DIR')); core_matlab_new('$PROJECT_NAME', 'nuclei_protein_registration', '$POSITION_NAME', \
    $IMAGE_WIDTH, $IMAGE_DEPTH, $REF_ROUND, $CHANNEL_NUM, $ROUND_NUM, \
    '$PROJECT_ROOT', '01_data', '$REG_DIR_SUFFIX', 'log', \
    'moving_round', '$MOVING_ROUND', 'aligned_round_outdir', '$ALIGNED_ROUND_OUTDIR', \
    'input_format', '$INPUT_FORMAT', 'norm_out_format', '$NORM_OUT_FORMAT', \
    'channel_panel', $CHANNEL_PANEL_MATLAB)"

end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Elapsed time: $((end_time - start_time)) seconds"
