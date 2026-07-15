#!/bin/bash
#SBATCH -J prepare_raw_symlinks
#SBATCH -o logs_prepare_raw_symlinks/%x_%A.out
#SBATCH -e logs_prepare_raw_symlinks/%x_%A.err
#SBATCH -p C64M256G
#SBATCH --qos=normal
#SBATCH -n 1
#SBATCH -c 1
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --no-requeue
#SBATCH --export=ALL

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 20_prepare_raw_data_symlinks.sh --source_project_root PATH --target_project_root PATH --project_name NAME [options]

Create sample-level raw data symlinks under TARGET_PROJECT_ROOT/PROJECT_NAME/01_data.

Required:
  --source_project_root PATH   Source project root containing PROJECT_NAME/01_data
  --target_project_root PATH   Target project root where PROJECT_NAME/01_data is prepared
  --project_name NAME          Sample/project name

Options:
  --entries LIST               Comma-separated 01_data entries [round001,IF,round011]
  --force BOOL                 Replace existing symlinks when true [false]
  -h, --help                   Show this help and exit
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

### 参数默认值 ---
SOURCE_PROJECT_ROOT=""
TARGET_PROJECT_ROOT=""
PROJECT_NAME=""
ENTRIES="round001,IF,round011"
FORCE="false"

### 参数解析 ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --source_project_root) SOURCE_PROJECT_ROOT="$2"; shift 2 ;;
        --target_project_root) TARGET_PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --entries) ENTRIES="$2"; shift 2 ;;
        --force) FORCE="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: Unknown parameter: $1" >&2; print_usage >&2; exit 1 ;;
    esac
done

### 必填检查 ---
[[ -n "$SOURCE_PROJECT_ROOT" ]] || { echo "Error: --source_project_root is required" >&2; exit 1; }
[[ -n "$TARGET_PROJECT_ROOT" ]] || { echo "Error: --target_project_root is required" >&2; exit 1; }
[[ -n "$PROJECT_NAME" ]] || { echo "Error: --project_name is required" >&2; exit 1; }

### 环境准备 ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="${SCRIPT_DIR}/p20_prepare_raw_data_symlinks.py"
LOG_DIR="logs_prepare_raw_symlinks"

mkdir -p "$LOG_DIR"
start_time=$(date +%s)
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"
print_slurm_info

### 参数打印 ---
echo "[PARAM] SOURCE_PROJECT_ROOT=${SOURCE_PROJECT_ROOT}"
echo "[PARAM] TARGET_PROJECT_ROOT=${TARGET_PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] ENTRIES=${ENTRIES}"
echo "[PARAM] FORCE=${FORCE}"

### 执行 Python ---
PY_ARGS=(
    --source_project_root "$SOURCE_PROJECT_ROOT"
    --target_project_root "$TARGET_PROJECT_ROOT"
    --project_name "$PROJECT_NAME"
    --entries "$ENTRIES"
)

if is_true "$FORCE"; then
    PY_ARGS+=(--force)
fi

python -u "$PY_SCRIPT" "${PY_ARGS[@]}"

end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Elapsed time: $((end_time - start_time)) seconds"
