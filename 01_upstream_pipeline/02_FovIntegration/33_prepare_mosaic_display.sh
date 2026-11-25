#!/bin/bash
#SBATCH -J mosaic_display
#SBATCH -o logs033_mosaic_display/%x_%A.out
#SBATCH -e logs033_mosaic_display/%x_%A.err
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 8
#SBATCH --time=08:00:00

set -euo pipefail

# Previously generated jobs still submit this path and prepare its original logs.
DISPLAY_ARGS=("$@")
while [[ $# -gt 0 ]]; do
    case "$1" in
        --script_dir) exec "${2}/35_prepare_mosaic_display.sh" "${DISPLAY_ARGS[@]}" ;;
        -h|--help)
            echo "Usage: 33_prepare_mosaic_display.sh --script_dir PATH [35_prepare_mosaic_display.sh options]"
            exit 0
            ;;
        *) shift 2 ;;
    esac
done

echo "Error: --script_dir is required" >&2
exit 2
