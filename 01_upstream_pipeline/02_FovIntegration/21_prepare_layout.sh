#!/bin/bash
#SBATCH -J prepare_noRef_layout
#SBATCH -o logs_prepare_noRef_layout/%x_%A.out
#SBATCH -e logs_prepare_noRef_layout/%x_%A.err
#SBATCH -p C64M256G
#SBATCH --qos=normal
#SBATCH -n 1
#SBATCH -c 4

#SBATCH --time=04:00:00
#SBATCH --no-requeue
#SBATCH --export=ALL

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 21_prepare_layout.sh --project_root PATH --project_name NAME --reg_dir_suffix NAME [options]

Prepare independent raw-channel folders for strict TileConfiguration stitching.

Required:
  --project_root PATH        Project root directory
  --project_name NAME        Project/sample name under project_root
  --reg_dir_suffix NAME      Registration directory name, e.g. 02_registration001_GBM008

Options:
  --rawdata_round NAME       Raw data round under 01_data [IF]
  --stitching_workdir NAME   Work directory under registration dir [IFindep]
  --channel_mode MODE        LeicaIF, OlympusIF, LeicaSeqE, or LeicaRef [LeicaIF]
  --manifest_name NAME       Manifest filename [extra_layout_manifest.csv]
  --link_mode MODE           symlink, hardlink, or copy [copy]
  --output_format FORMAT     preserve, uint8, or uint16 [preserve]
  --script_dir PATH          Directory containing p21_prepare_noRef_layout.py
  --conda_env NAME           Conda environment name [ashlar]
  -h, --help                 Show this help and exit
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
    echo "Partition:       ${SLURM_JOB_PARTITION:-}"
    echo "CPUs per task:   ${SLURM_CPUS_PER_TASK:-}"
    echo "Memory per node: ${SLURM_MEM_PER_NODE:-} MB"
    echo "==============================================="
}

resolve_channel_mapping() {
    case "$1" in
        LeicaIF)
            echo "ch00=raw-561-CA9,ch01=raw-488-CD144,ch02=raw-647-CD31,ch03=raw-DAPI"
            ;;
        OlympusIF)
            echo "ch00=raw-488-CD144,ch01=raw-561-CA9,ch02=raw-647-CD31,ch03=raw-DAPI"
            ;;
        LeicaSeqE)
            echo "ch00=raw-647-GCnt,ch01=raw-561-GTrb,ch02=raw-Padlayer,ch03=raw-DAPI"
            ;;
        LeicaRef)
            echo "ch00=raw-561,ch01=raw-488,ch02=raw-647,ch03=raw-refDAPI"
            ;;
        *)
            echo "Error: Unsupported channel_mode for step 21: $1" >&2
            echo "Supported modes: LeicaIF, OlympusIF, LeicaSeqE, LeicaRef" >&2
            exit 1
            ;;
    esac
}

### 参数默认值 ---
DEFAULT_SCRIPT_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration"
PROJECT_ROOT=""
PROJECT_NAME=""
RAWDATA_ROUND="IF"
REG_DIR_SUFFIX=""
STITCHING_WORKDIR="IFindep"
CHANNEL_MODE="LeicaIF"
MANIFEST_NAME="extra_layout_manifest.csv"
LINK_MODE="copy"
OUTPUT_FORMAT="preserve"
SCRIPT_DIR="$DEFAULT_SCRIPT_DIR"
CONDA_ENV="ashlar"

### 参数解析 ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --rawdata_round) RAWDATA_ROUND="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --stitching_workdir) STITCHING_WORKDIR="$2"; shift 2 ;;
        --channel_mode) CHANNEL_MODE="$2"; shift 2 ;;
        --manifest_name) MANIFEST_NAME="$2"; shift 2 ;;
        --link_mode) LINK_MODE="$2"; shift 2 ;;
        --output_format) OUTPUT_FORMAT="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_env) CONDA_ENV="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: Unknown parameter: $1" >&2; print_usage >&2; exit 1 ;;
    esac
done

### 必填检查与路径推导 ---
[[ -n "$PROJECT_ROOT" ]] || { echo "Error: --project_root is required" >&2; exit 1; }
[[ -n "$PROJECT_NAME" ]] || { echo "Error: --project_name is required" >&2; exit 1; }
[[ -n "$REG_DIR_SUFFIX" ]] || { echo "Error: --reg_dir_suffix is required" >&2; exit 1; }

RAW_ROUND_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/${RAWDATA_ROUND}"
OUTPUT_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/${REG_DIR_SUFFIX}/${STITCHING_WORKDIR}"
CHANNELS="$(resolve_channel_mapping "$CHANNEL_MODE")"

### 环境准备 ---
PY_SCRIPT="${SCRIPT_DIR}/p21_prepare_noRef_layout.py"
LOG_DIR="logs_prepare_noRef_layout"

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
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] REG_DIR_SUFFIX=${REG_DIR_SUFFIX}"
echo "[PARAM] RAWDATA_ROUND=${RAWDATA_ROUND}"
echo "[PARAM] STITCHING_WORKDIR=${STITCHING_WORKDIR}"
echo "[PARAM] CHANNEL_MODE=${CHANNEL_MODE}"
echo "[PARAM] CHANNELS=${CHANNELS}"
echo "[PARAM] RAW_ROUND_DIR=${RAW_ROUND_DIR}"
echo "[PARAM] OUTPUT_DIR=${OUTPUT_DIR}"
echo "[PARAM] MANIFEST_NAME=${MANIFEST_NAME}"
echo "[PARAM] LINK_MODE=${LINK_MODE}"
echo "[PARAM] OUTPUT_FORMAT=${OUTPUT_FORMAT}"
echo "[PARAM] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PARAM] CONDA_ENV=${CONDA_ENV}"

### 执行 Python ---
PY_ARGS=(
    --raw_round_dir "$RAW_ROUND_DIR"
    --output_dir "$OUTPUT_DIR"
    --channels "$CHANNELS"
    --manifest_name "$MANIFEST_NAME"
    --link_mode "$LINK_MODE"
    --output_format "$OUTPUT_FORMAT"
)

echo "Running TE/extra channel layout preparation"
python -u "$PY_SCRIPT" "${PY_ARGS[@]}"

end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Elapsed time: $((end_time - start_time)) seconds"
