#!/bin/bash
#SBATCH -J csv_to_count_matrix
#SBATCH -o logs002_csv2CountMatrix/csv2CountMatrix_%A.out
#SBATCH -e logs002_csv2CountMatrix/csv2CountMatrix_%A.err
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 8
#SBATCH --time=12:00:00

set -euo pipefail

SCRIPT_DIR=""
CONDA_SH=""
PROJECT_ROOT=""
PROJECT_NAME=""
OUTPUT_DIRNAME=""
SEG_METHOD=""
OUTPUT_SUFFIX=""

usage() {
    cat <<'EOF'
Usage: 02_csv2CountMatrix.sh --script_dir DIR --conda_sh FILE \
    --project_root DIR --project_name NAME --output_dirname NAME \
    --seg_method NAME --output_suffix NAME
EOF
}

while (( $# )); do
    case "$1" in
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_sh) CONDA_SH="$2"; shift 2 ;;
        --project_root) PROJECT_ROOT="$2"; shift 2 ;;
        --project_name) PROJECT_NAME="$2"; shift 2 ;;
        --output_dirname) OUTPUT_DIRNAME="$2"; shift 2 ;;
        --seg_method) SEG_METHOD="$2"; shift 2 ;;
        --output_suffix) OUTPUT_SUFFIX="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'ERROR: unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

for required_name in \
    SCRIPT_DIR CONDA_SH PROJECT_ROOT PROJECT_NAME OUTPUT_DIRNAME SEG_METHOD OUTPUT_SUFFIX
do
    if [[ -z "${!required_name}" ]]; then
        printf 'ERROR: required argument is empty: %s\n' "$required_name" >&2
        exit 2
    fi
done

RUNNER="${SCRIPT_DIR}/csv2CountMatrix.py"
OUTPUT_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/${OUTPUT_DIRNAME}"
INPUT_CSV="${OUTPUT_DIR}/remain_reads_${PROJECT_NAME}_${SEG_METHOD}_${OUTPUT_SUFFIX}.csv"
OUTPUT_H5AD="${OUTPUT_DIR}/adata_${PROJECT_NAME}_${SEG_METHOD}_${OUTPUT_SUFFIX}.h5ad"
START_TIME=$(date +%s)

finish() {
    local status=$?
    local end_time
    end_time=$(date +%s)
    printf '运行时间: %s seconds\n' "$((end_time - START_TIME))"
    if (( status == 0 )); then
        printf 'STATUS: SUCCESS | SLURM_JOB_NAME=%s\n' "${SLURM_JOB_NAME:-N/A}"
    else
        printf 'STATUS: FAILED | SLURM_JOB_NAME=%s\n' "${SLURM_JOB_NAME:-N/A}" >&2
    fi
    exit "$status"
}
trap finish EXIT

[[ -f "$CONDA_SH" ]] || { printf 'ERROR: conda init not found: %s\n' "$CONDA_SH" >&2; exit 1; }
[[ -f "$RUNNER" ]] || { printf 'ERROR: runner not found: %s\n' "$RUNNER" >&2; exit 1; }
[[ -f "$INPUT_CSV" ]] || { printf 'ERROR: input CSV not found: %s\n' "$INPUT_CSV" >&2; exit 1; }
mkdir -p "$OUTPUT_DIR"

printf 'Input CSV: %s\n' "$INPUT_CSV"
printf 'Output h5ad: %s\n' "$OUTPUT_H5AD"
printf 'SLURM_JOB_ID=%s | NODE=%s | CPUS=%s | MEMORY_MB=%s\n' \
    "${SLURM_JOB_ID:-N/A}" "${SLURMD_NODENAME:-N/A}" \
    "${SLURM_CPUS_PER_TASK:-N/A}" "${SLURM_MEM_PER_NODE:-N/A}"

source "$CONDA_SH"
conda activate data_analysis_env

python -u "$RUNNER" \
    --input_csv "$INPUT_CSV" \
    --output_h5ad "$OUTPUT_H5AD"

[[ -f "$OUTPUT_H5AD" ]] || { printf 'ERROR: expected output missing: %s\n' "$OUTPUT_H5AD" >&2; exit 1; }
