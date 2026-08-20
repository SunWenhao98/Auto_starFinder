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
Usage: 28_compare_mosaic_registration.sh --python_json FILE --matlab_json FILE --output_prefix PATH [options]

Options:
  --agreement_tolerance_px FLOAT  [0.5]
  --fail_on_disagreement BOOL     [true]
  --script_dir PATH
  --conda_env NAME                [ashlar]
  --overwrite BOOL                [false]
  --dry_run BOOL                  [false]
  -h, --help
USAGE
}

is_true() {
    case "${1,,}" in true|1|yes) return 0 ;; false|0|no|"") return 1 ;; *) exit 1 ;; esac
}

SCRIPT_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration"
PYTHON_JSON=""
MATLAB_JSON=""
OUTPUT_PREFIX=""
AGREEMENT_TOLERANCE_PX="0.5"
FAIL_ON_DISAGREEMENT="true"
CONDA_ENV="ashlar"
OVERWRITE="false"
DRY_RUN="false"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --python_json) PYTHON_JSON="$2"; shift 2 ;;
        --matlab_json) MATLAB_JSON="$2"; shift 2 ;;
        --output_prefix) OUTPUT_PREFIX="$2"; shift 2 ;;
        --agreement_tolerance_px) AGREEMENT_TOLERANCE_PX="$2"; shift 2 ;;
        --fail_on_disagreement) FAIL_ON_DISAGREEMENT="$2"; shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; shift 2 ;;
        --conda_env) CONDA_ENV="$2"; shift 2 ;;
        --overwrite) OVERWRITE="$2"; shift 2 ;;
        --dry_run) DRY_RUN="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: Unknown parameter: $1" >&2; exit 1 ;;
    esac
done
[[ -n "$PYTHON_JSON" && -n "$MATLAB_JSON" && -n "$OUTPUT_PREFIX" ]] || { echo "Error: --python_json, --matlab_json, and --output_prefix are required" >&2; exit 1; }
SCRIPT="${SCRIPT_DIR}/p28_compare_mosaic_registration.py"
OUTPUT_JSON="${OUTPUT_PREFIX}.comparison.json"
OUTPUT_CSV="${OUTPUT_PREFIX}.comparison.csv"
COMMAND=(python -u "$SCRIPT" --python_json "$PYTHON_JSON" --matlab_json "$MATLAB_JSON" --output_json "$OUTPUT_JSON" --output_csv "$OUTPUT_CSV" --agreement_tolerance_px "$AGREEMENT_TOLERANCE_PX" --fail_on_disagreement "$FAIL_ON_DISAGREEMENT" --overwrite "$OVERWRITE")
printf '[COMMAND] '; printf '%q ' "${COMMAND[@]}"; printf '\n'
if is_true "$DRY_RUN"; then exit 0; fi
for path in "$PYTHON_JSON" "$MATLAB_JSON" "$SCRIPT"; do [[ -f "$path" ]] || { echo "Error: missing file: $path" >&2; exit 1; }; done
mkdir -p "$(dirname "$OUTPUT_PREFIX")"
trap 'exit_code=$?; if [[ $exit_code -ne 0 ]]; then echo "STATUS: FAILED | SLURM_JOB_NAME=${SLURM_JOB_NAME:-N/A}"; fi' EXIT
source "/gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh"
set +u
conda activate "$CONDA_ENV"
set -u
"${COMMAND[@]}"
[[ -s "$OUTPUT_JSON" && -s "$OUTPUT_CSV" ]] || { echo "Error: comparison outputs missing" >&2; exit 1; }
echo "STATUS: SUCCESS | SLURM_JOB_NAME=${SLURM_JOB_NAME:-N/A}"
trap - EXIT
