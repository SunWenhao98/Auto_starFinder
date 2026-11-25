#!/bin/bash
#SBATCH -J estimate_flat_field
#SBATCH -o logs033_flat_field/%x_%A.out
#SBATCH -e logs033_flat_field/%x_%A.err
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 4
#SBATCH --time=08:00:00

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 33_estimate_flat_field.sh --input_manifest PATH --output_dir PATH
    --script_dir PATH --conda_sh PATH [--sigma PIXELS]

Input CSV columns: round,channel,source_tiff
Use ref, IF or seqE for round. Paths can be relative to the CSV directory.
The new output directory contains sensor-oriented TIFFs and profiles.csv.
Prepare logs033_flat_field in the submission directory before sbatch.
USAGE
}

finish() {
    local exit_code=$?
    local status="SUCCESS"
    if (( exit_code != 0 )); then
        status="FAILED"
    fi
    echo "结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "运行时间: $(($(date +%s) - START_TIME)) seconds"
    echo "STATUS: ${status} | SLURM_JOB_NAME=${SLURM_JOB_NAME:-N/A}"
}

INPUT_MANIFEST=""
OUTPUT_DIR=""
SCRIPT_DIR=""
CONDA_SH=""
SIGMA=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --input_manifest) INPUT_MANIFEST="$2"; shift 2 ;;
        --output_dir) OUTPUT_DIR="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --sigma) SIGMA="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: unknown parameter: $1" >&2; print_usage >&2; exit 1 ;;
    esac
done

START_TIME=$(date +%s)
trap finish EXIT
RUNNER="${SCRIPT_DIR}/p33_estimate_flat_field.py"
OPTIONS=()
if [[ -n "$SIGMA" ]]; then
    OPTIONS+=(--sigma "$SIGMA")
fi

echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Job ID:              ${SLURM_JOB_ID:-N/A}"
echo "Node:                ${SLURMD_NODENAME:-N/A}"
echo "CPUs per task:       ${SLURM_CPUS_PER_TASK:-N/A}"
echo "Memory per CPU (MB): ${SLURM_MEM_PER_CPU:-N/A}"
echo "Input manifest:      ${INPUT_MANIFEST}"
echo "Output directory:    ${OUTPUT_DIR}"
echo "Gaussian sigma:      ${SIGMA:-runner default}"
echo "Runner:              ${RUNNER}"
echo "Environment:         ashlar (${CONDA_SH})"

source "$CONDA_SH"
set +u
conda activate ashlar
set -u

python -u "$RUNNER" \
    --input_manifest "$INPUT_MANIFEST" \
    --output_dir "$OUTPUT_DIR" \
    "${OPTIONS[@]}"

if [[ ! -s "${OUTPUT_DIR}/profiles.csv" ]]; then
    echo "Error: missing flat-field manifest: ${OUTPUT_DIR}/profiles.csv" >&2
    exit 1
fi
