#!/bin/bash
#SBATCH -J mosaic_reg_compare
#SBATCH -o logs028_mosaic_registration/%x_%A.out
#SBATCH -e logs028_mosaic_registration/%x_%A.err
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 2
#SBATCH --time=01:00:00

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 28_compare_mosaic_registration.sh --project_root PATH --project_name NAME --reg_dir_suffix DIR --python_json PATH --matlab_json PATH --output_workdir DIR --output_label NAME [options]

Options:
  --agreement_tolerance_px FLOAT
  --fail_on_disagreement BOOL
  --overwrite BOOL
  --dry_run BOOL
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
PYTHON_JSON=""
MATLAB_JSON=""
OUTPUT_WORKDIR=""
OUTPUT_LABEL=""
AGREEMENT_TOLERANCE_PX="0.5"
FAIL_ON_DISAGREEMENT="true"
OVERWRITE="false"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --reg_dir_suffix) REG_DIR_SUFFIX="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --python_json) PYTHON_JSON="$2"; shift 2 ;;
        --matlab_json) MATLAB_JSON="$2"; shift 2 ;;
        --output_workdir) OUTPUT_WORKDIR="$2"; shift 2 ;;
        --output_label) OUTPUT_LABEL="$2"; shift 2 ;;
        --agreement_tolerance_px) AGREEMENT_TOLERANCE_PX="$2"; shift 2 ;;
        --fail_on_disagreement) FAIL_ON_DISAGREEMENT="$2"; shift 2 ;;
        --overwrite) OVERWRITE="$2"; shift 2 ;;
        --dry_run) DRY_RUN="$2"; shift 2 ;;
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

for value in PROJECT_ROOT PROJECT_NAME REG_DIR_SUFFIX SCRIPT_DIR CONDA_SH PYTHON_JSON MATLAB_JSON OUTPUT_WORKDIR OUTPUT_LABEL; do
    [[ -n "${!value}" ]] || { echo "Error: ${value} is required" >&2; exit 1; }
done
REGISTRATION_FOLDER="02_registration${REG_DIR_SUFFIX}"
REG_ROOT="${PROJECT_ROOT}/${PROJECT_NAME}/${REGISTRATION_FOLDER}"
PYTHON_JSON_FILE="${REG_ROOT}/${PYTHON_JSON}"
MATLAB_JSON_FILE="${REG_ROOT}/${MATLAB_JSON}"
OUTPUT_PREFIX="${REG_ROOT}/${OUTPUT_WORKDIR}/${OUTPUT_LABEL}"
OUTPUT_JSON="${OUTPUT_PREFIX}.comparison.json"
OUTPUT_CSV="${OUTPUT_PREFIX}.comparison.csv"
print_slurm_info
echo "[PARAM] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[PARAM] PROJECT_NAME=${PROJECT_NAME}"
echo "[PARAM] PYTHON_JSON=${PYTHON_JSON}"
echo "[PARAM] MATLAB_JSON=${MATLAB_JSON}"
echo "[PARAM] OUTPUT_WORKDIR=${OUTPUT_WORKDIR}"
echo "[PARAM] OUTPUT_LABEL=${OUTPUT_LABEL}"
echo "[PARAM] AGREEMENT_TOLERANCE_PX=${AGREEMENT_TOLERANCE_PX}"
echo "[PARAM] FAIL_ON_DISAGREEMENT=${FAIL_ON_DISAGREEMENT}"
echo "[PARAM] OVERWRITE=${OVERWRITE}"
echo "[PARAM] DRY_RUN=${DRY_RUN}"

SCRIPT="${SCRIPT_DIR}/p28_compare_mosaic_registration.py"
COMMAND=(
    python -u "$SCRIPT"
    --python_json "$PYTHON_JSON_FILE"
    --matlab_json "$MATLAB_JSON_FILE"
    --output_json "$OUTPUT_JSON"
    --output_csv "$OUTPUT_CSV"
    --agreement_tolerance_px "$AGREEMENT_TOLERANCE_PX"
    --fail_on_disagreement "$FAIL_ON_DISAGREEMENT"
    --overwrite "$OVERWRITE"
)

echo "[PATH] REG_ROOT=${REG_ROOT}"
echo "[PATH] PYTHON_JSON_FILE=${PYTHON_JSON_FILE}"
echo "[PATH] MATLAB_JSON_FILE=${MATLAB_JSON_FILE}"
echo "[PATH] OUTPUT_PREFIX=${OUTPUT_PREFIX}"
echo "[PATH] SCRIPT_DIR=${SCRIPT_DIR}"
echo "[PATH] CONDA_SH=${CONDA_SH}"
printf '[COMMAND] '; printf '%q ' "${COMMAND[@]}"; printf '\n'
if [[ "$DRY_RUN" == "true" ]]; then
    FINAL_STATUS="DRY_RUN_DONE"
    exit 0
fi
for path in "$PYTHON_JSON_FILE" "$MATLAB_JSON_FILE" "$CONDA_SH" "$SCRIPT"; do
    [[ -f "$path" ]] || { echo "Error: missing file: $path" >&2; exit 1; }
done
mkdir -p "$(dirname "$OUTPUT_PREFIX")"
source "$CONDA_SH"
set +u
conda activate ashlar
set -u
"${COMMAND[@]}"
[[ -s "$OUTPUT_JSON" && -s "$OUTPUT_CSV" ]] || { echo "Error: comparison outputs missing" >&2; exit 1; }
