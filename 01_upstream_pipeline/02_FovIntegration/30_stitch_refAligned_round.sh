#!/bin/bash
#SBATCH -J stitch_refAligned_round
#SBATCH -o logs_refAligned_round/%x_%A.out
#SBATCH -e logs_refAligned_round/%x_%A.err
#SBATCH -p C64M512G
#SBATCH --qos=normal
#SBATCH -n 1
#SBATCH -c 60
#SBATCH --mem=480G
#SBATCH --time=72:00:00
#SBATCH --no-requeue
#SBATCH --export=ALL

set -euo pipefail

print_usage() {
    cat <<'USAGE'
Usage: 30_stitch_refAligned_round.sh --work_dir PATH --initial_input_dir PATH --raw_round_dir PATH --registration_dir PATH --direct_channels LIST [options]

Run the common reference-aligned round stitching workflow inside one SLURM job:
  22_ashlar_stitch_initial.sh -> 23_prepare_moveImages_tileconfig.sh -> 24_ashlar_stitch_mosaic.sh for each direct channel

The 11/12 registration and TileConfiguration workflows are intentionally not
included. This wrapper assumes TileConfiguration.txt, registration shift logs,
and raw round images already exist.

Required:
  --work_dir PATH                   Round work directory
  --initial_input_dir PATH          Input image directory for initial Ashlar stitch
  --raw_round_dir PATH              Raw round directory containing PositionXXX folders
  --registration_dir PATH           Registration directory containing shift logs
  --direct_channels LIST            Comma-separated channels to direct stitch

Workflow paths:
  --stitch_result_dir PATH          Output directory for stitched images [WORK_DIR/stitching_results]
  --initial_config_file FILE        Initial TileConfiguration input [WORK_DIR/TileConfiguration.txt]
  --registered_config_file FILE     Registered config output [WORK_DIR/TileConfiguration.registered.txt]
  --initial_output_prefix PREFIX    Initial stitch output prefix [STITCH_RESULT_DIR/stitched_ref_ashlar]

Step 22 options:
  --initial_make_3d BOOL            Write 3D initial mosaic [false]
  --initial_rotate90 BOOL           Rotate initial FOVs before stitching [false]
  --initial_rotate_positions BOOL   Diagnostic metadata rotation [false]
  --pixel_size_um FLOAT             Pixel size in um/pixel [0.142]
  --max_shift_px FLOAT              Maximum corrective shift in pixels [150]
  --filter_sigma FLOAT              Gaussian sigma for alignment filtering [1.0]
  --stitch_alpha FLOAT              Ashlar alpha for automatic max_error [0.01]
  --max_error VALUE                 Explicit Ashlar max_error or auto [auto]
  --initial_slice_indices LIST      Comma-separated 1-based z slices []

Step 23 options:
  --output_ref_name NAME            Copied ref config filename [TileConfigurationRef.txt]
  --output_round_config_name NAME   Round raw config filename [TileConfigurationIF.txt]
  --raw_prefix NAME                 Output raw channel layout under WORK_DIR [IF_raw]
  --ref_channel NAME                Reference channel name [ref-DAPI]
  --channels LIST                   Raw channel order [488-CD144,561-CA9,647-CD31,DAPI]
  --link_mode MODE                  symlink, hardlink, or copy [symlink]
  --input_format FORMAT             preserve, uint8, or uint16 [preserve]
  --output_format FORMAT            preserve, uint8, or uint16 [uint8]
  --prepare_rotate90 BOOL           Rotate shift coordinates [false]
  --shift_sign FLOAT                Shift direction multiplier [1.0]

Step 24 options:
  --direct_config_file FILE         Direct stitch config [WORK_DIR/OUTPUT_ROUND_CONFIG_NAME]
  --direct_input_root PATH          Direct channel root [WORK_DIR/RAW_PREFIX]
  --direct_output_dir PATH          Direct output directory [STITCH_RESULT_DIR]
  --direct_output_prefixes LIST     Comma-separated output prefixes; same length as --direct_channels []
  --direct_make_3d BOOL             Write 3D direct mosaics [false]
  --direct_rotate90 BOOL            Rotate direct FOVs before stitching [false]
  --direct_slice_indices LIST       Comma-separated 1-based z slices []

Script/runtime options:
  --script_22 FILE                  Step 22 wrapper [SCRIPT_DIR/22_ashlar_stitch_initial.sh]
  --script_23 FILE                  Step 23 wrapper [SCRIPT_DIR/23_prepare_moveImages_tileconfig.sh]
  --script_24 FILE                  Step 24 wrapper [SCRIPT_DIR/24_ashlar_stitch_mosaic.sh]
  --conda_env NAME                  Conda environment passed to child wrappers [ashlar]
  --dry_run BOOL                    Print child commands without executing [false]
  -h, --help                        Show this help and exit
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

print_cmd() {
    local quoted=()
    local arg
    for arg in "$@"; do
        printf -v arg '%q' "$arg"
        quoted+=("$arg")
    done
    printf '%s\n' "${quoted[*]}"
}

run_step() {
    local label="$1"
    shift
    echo "STATUS: ${label}_START"
    echo "[CMD] $(print_cmd "$@")"
    if is_true "$DRY_RUN"; then
        echo "STATUS: ${label}_DRY_RUN_DONE"
    else
        "$@"
        echo "STATUS: ${label}_DONE"
    fi
}

split_csv() {
    local input="$1"
    local -n out_ref="$2"
    IFS=',' read -r -a out_ref <<< "$input"
    local i
    for i in "${!out_ref[@]}"; do
        out_ref[$i]="$(echo "${out_ref[$i]}" | xargs)"
    done
}

### 参数默认值 ---
WORK_DIR=""
STITCH_RESULT_DIR=""
INITIAL_INPUT_DIR=""
INITIAL_CONFIG_FILE=""
REGISTERED_CONFIG_FILE=""
INITIAL_OUTPUT_PREFIX=""

RAW_ROUND_DIR=""
REGISTRATION_DIR=""
OUTPUT_REF_NAME="TileConfigurationRef.txt"
OUTPUT_ROUND_CONFIG_NAME="TileConfigurationIF.txt"
RAW_PREFIX="IF_raw"
REF_CHANNEL="ref-DAPI"
CHANNELS="488-CD144,561-CA9,647-CD31,DAPI"
LINK_MODE="symlink"
INPUT_FORMAT="preserve"
OUTPUT_FORMAT="uint8"
PREPARE_ROTATE90="false"
SHIFT_SIGN="1.0"

DIRECT_CONFIG_FILE=""
DIRECT_INPUT_ROOT=""
DIRECT_OUTPUT_DIR=""
DIRECT_CHANNELS=""
DIRECT_OUTPUT_PREFIXES=""

INITIAL_MAKE_3D="false"
INITIAL_ROTATE90="false"
INITIAL_ROTATE_POSITIONS="false"
PIXEL_SIZE_UM="0.142"
MAX_SHIFT_PX="150"
FILTER_SIGMA="1.0"
STITCH_ALPHA="0.01"
MAX_ERROR="auto"
INITIAL_SLICE_INDICES=""

DIRECT_MAKE_3D="false"
DIRECT_ROTATE90="false"
DIRECT_SLICE_INDICES=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_22="${SCRIPT_DIR}/22_ashlar_stitch_initial.sh"
SCRIPT_23="${SCRIPT_DIR}/23_prepare_moveImages_tileconfig.sh"
SCRIPT_24="${SCRIPT_DIR}/24_ashlar_stitch_mosaic.sh"
CONDA_ENV="ashlar"
DRY_RUN="false"

### 参数解析 ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --work_dir) WORK_DIR="$2"; shift 2 ;;
        --stitch_result_dir) STITCH_RESULT_DIR="$2"; shift 2 ;;
        --initial_input_dir) INITIAL_INPUT_DIR="$2"; shift 2 ;;
        --initial_config_file) INITIAL_CONFIG_FILE="$2"; shift 2 ;;
        --registered_config_file) REGISTERED_CONFIG_FILE="$2"; shift 2 ;;
        --initial_output_prefix) INITIAL_OUTPUT_PREFIX="$2"; shift 2 ;;
        --raw_round_dir) RAW_ROUND_DIR="$2"; shift 2 ;;
        --registration_dir) REGISTRATION_DIR="$2"; shift 2 ;;
        --output_ref_name) OUTPUT_REF_NAME="$2"; shift 2 ;;
        --output_round_config_name) OUTPUT_ROUND_CONFIG_NAME="$2"; shift 2 ;;
        --raw_prefix) RAW_PREFIX="$2"; shift 2 ;;
        --ref_channel) REF_CHANNEL="$2"; shift 2 ;;
        --channels) CHANNELS="$2"; shift 2 ;;
        --link_mode) LINK_MODE="$2"; shift 2 ;;
        --input_format) INPUT_FORMAT="$2"; shift 2 ;;
        --output_format) OUTPUT_FORMAT="$2"; shift 2 ;;
        --prepare_rotate90) PREPARE_ROTATE90="$2"; shift 2 ;;
        --shift_sign) SHIFT_SIGN="$2"; shift 2 ;;
        --direct_config_file) DIRECT_CONFIG_FILE="$2"; shift 2 ;;
        --direct_input_root) DIRECT_INPUT_ROOT="$2"; shift 2 ;;
        --direct_output_dir) DIRECT_OUTPUT_DIR="$2"; shift 2 ;;
        --direct_channels) DIRECT_CHANNELS="$2"; shift 2 ;;
        --direct_output_prefixes) DIRECT_OUTPUT_PREFIXES="$2"; shift 2 ;;
        --initial_make_3d) INITIAL_MAKE_3D="$2"; shift 2 ;;
        --initial_rotate90) INITIAL_ROTATE90="$2"; shift 2 ;;
        --initial_rotate_positions) INITIAL_ROTATE_POSITIONS="$2"; shift 2 ;;
        --pixel_size_um) PIXEL_SIZE_UM="$2"; shift 2 ;;
        --max_shift_px) MAX_SHIFT_PX="$2"; shift 2 ;;
        --filter_sigma) FILTER_SIGMA="$2"; shift 2 ;;
        --stitch_alpha) STITCH_ALPHA="$2"; shift 2 ;;
        --max_error) MAX_ERROR="$2"; shift 2 ;;
        --initial_slice_indices) INITIAL_SLICE_INDICES="$2"; shift 2 ;;
        --direct_make_3d) DIRECT_MAKE_3D="$2"; shift 2 ;;
        --direct_rotate90) DIRECT_ROTATE90="$2"; shift 2 ;;
        --direct_slice_indices) DIRECT_SLICE_INDICES="$2"; shift 2 ;;
        --script_22) SCRIPT_22="$2"; shift 2 ;;
        --script_23) SCRIPT_23="$2"; shift 2 ;;
        --script_24) SCRIPT_24="$2"; shift 2 ;;
        --conda_env) CONDA_ENV="$2"; shift 2 ;;
        --dry_run) DRY_RUN="$2"; shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        *) echo "Error: Unknown parameter: $1" >&2; print_usage >&2; exit 1 ;;
    esac
done

### 必填检查与派生默认 ---
[[ -n "$WORK_DIR" ]] || { echo "Error: --work_dir is required" >&2; exit 1; }
[[ -n "$INITIAL_INPUT_DIR" ]] || { echo "Error: --initial_input_dir is required" >&2; exit 1; }
[[ -n "$RAW_ROUND_DIR" ]] || { echo "Error: --raw_round_dir is required" >&2; exit 1; }
[[ -n "$REGISTRATION_DIR" ]] || { echo "Error: --registration_dir is required" >&2; exit 1; }
[[ -n "$DIRECT_CHANNELS" ]] || { echo "Error: --direct_channels is required" >&2; exit 1; }

if [[ -z "$STITCH_RESULT_DIR" ]]; then
    STITCH_RESULT_DIR="${WORK_DIR}/stitching_results"
fi
if [[ -z "$INITIAL_CONFIG_FILE" ]]; then
    INITIAL_CONFIG_FILE="${WORK_DIR}/TileConfiguration.txt"
fi
if [[ -z "$REGISTERED_CONFIG_FILE" ]]; then
    REGISTERED_CONFIG_FILE="${WORK_DIR}/TileConfiguration.registered.txt"
fi
if [[ -z "$INITIAL_OUTPUT_PREFIX" ]]; then
    INITIAL_OUTPUT_PREFIX="${STITCH_RESULT_DIR}/stitched_ref_ashlar"
fi
if [[ -z "$DIRECT_CONFIG_FILE" ]]; then
    DIRECT_CONFIG_FILE="${WORK_DIR}/${OUTPUT_ROUND_CONFIG_NAME}"
fi
if [[ -z "$DIRECT_INPUT_ROOT" ]]; then
    DIRECT_INPUT_ROOT="${WORK_DIR}/${RAW_PREFIX}"
fi
if [[ -z "$DIRECT_OUTPUT_DIR" ]]; then
    DIRECT_OUTPUT_DIR="$STITCH_RESULT_DIR"
fi

is_true "$DRY_RUN" || true
is_true "$INITIAL_MAKE_3D" || true
is_true "$INITIAL_ROTATE90" || true
is_true "$INITIAL_ROTATE_POSITIONS" || true
is_true "$PREPARE_ROTATE90" || true
is_true "$DIRECT_MAKE_3D" || true
is_true "$DIRECT_ROTATE90" || true

DIRECT_CHANNEL_ARRAY=()
DIRECT_PREFIX_ARRAY=()
split_csv "$DIRECT_CHANNELS" DIRECT_CHANNEL_ARRAY
if [[ -n "$DIRECT_OUTPUT_PREFIXES" ]]; then
    split_csv "$DIRECT_OUTPUT_PREFIXES" DIRECT_PREFIX_ARRAY
    if [[ ${#DIRECT_CHANNEL_ARRAY[@]} -ne ${#DIRECT_PREFIX_ARRAY[@]} ]]; then
        echo "Error: --direct_output_prefixes must have the same length as --direct_channels" >&2
        exit 1
    fi
else
    for channel in "${DIRECT_CHANNEL_ARRAY[@]}"; do
        DIRECT_PREFIX_ARRAY+=("${DIRECT_OUTPUT_DIR}/stitched_${channel}_ashlar")
    done
fi

if ! is_true "$DRY_RUN"; then
    [[ -f "$SCRIPT_22" ]] || { echo "Error: script_22 not found: $SCRIPT_22" >&2; exit 1; }
    [[ -f "$SCRIPT_23" ]] || { echo "Error: script_23 not found: $SCRIPT_23" >&2; exit 1; }
    [[ -f "$SCRIPT_24" ]] || { echo "Error: script_24 not found: $SCRIPT_24" >&2; exit 1; }
    mkdir -p "$STITCH_RESULT_DIR" "$DIRECT_OUTPUT_DIR" logs_refAligned_round
else
    mkdir -p logs_refAligned_round
fi

start_time=$(date +%s)
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"
print_slurm_info

echo "[PARAM] WORK_DIR=${WORK_DIR}"
echo "[PARAM] STITCH_RESULT_DIR=${STITCH_RESULT_DIR}"
echo "[PARAM] INITIAL_INPUT_DIR=${INITIAL_INPUT_DIR}"
echo "[PARAM] INITIAL_CONFIG_FILE=${INITIAL_CONFIG_FILE}"
echo "[PARAM] REGISTERED_CONFIG_FILE=${REGISTERED_CONFIG_FILE}"
echo "[PARAM] INITIAL_OUTPUT_PREFIX=${INITIAL_OUTPUT_PREFIX}"
echo "[PARAM] RAW_ROUND_DIR=${RAW_ROUND_DIR}"
echo "[PARAM] REGISTRATION_DIR=${REGISTRATION_DIR}"
echo "[PARAM] OUTPUT_REF_NAME=${OUTPUT_REF_NAME}"
echo "[PARAM] OUTPUT_ROUND_CONFIG_NAME=${OUTPUT_ROUND_CONFIG_NAME}"
echo "[PARAM] RAW_PREFIX=${RAW_PREFIX}"
echo "[PARAM] REF_CHANNEL=${REF_CHANNEL}"
echo "[PARAM] CHANNELS=${CHANNELS}"
echo "[PARAM] LINK_MODE=${LINK_MODE}"
echo "[PARAM] INPUT_FORMAT=${INPUT_FORMAT}"
echo "[PARAM] OUTPUT_FORMAT=${OUTPUT_FORMAT}"
echo "[PARAM] PREPARE_ROTATE90=${PREPARE_ROTATE90}"
echo "[PARAM] SHIFT_SIGN=${SHIFT_SIGN}"
echo "[PARAM] DIRECT_CONFIG_FILE=${DIRECT_CONFIG_FILE}"
echo "[PARAM] DIRECT_INPUT_ROOT=${DIRECT_INPUT_ROOT}"
echo "[PARAM] DIRECT_OUTPUT_DIR=${DIRECT_OUTPUT_DIR}"
echo "[PARAM] DIRECT_CHANNELS=${DIRECT_CHANNELS}"
echo "[PARAM] DIRECT_OUTPUT_PREFIXES=${DIRECT_OUTPUT_PREFIXES}"
echo "[PARAM] INITIAL_MAKE_3D=${INITIAL_MAKE_3D}"
echo "[PARAM] INITIAL_ROTATE90=${INITIAL_ROTATE90}"
echo "[PARAM] INITIAL_ROTATE_POSITIONS=${INITIAL_ROTATE_POSITIONS}"
echo "[PARAM] PIXEL_SIZE_UM=${PIXEL_SIZE_UM}"
echo "[PARAM] MAX_SHIFT_PX=${MAX_SHIFT_PX}"
echo "[PARAM] FILTER_SIGMA=${FILTER_SIGMA}"
echo "[PARAM] STITCH_ALPHA=${STITCH_ALPHA}"
echo "[PARAM] MAX_ERROR=${MAX_ERROR}"
echo "[PARAM] INITIAL_SLICE_INDICES=${INITIAL_SLICE_INDICES}"
echo "[PARAM] DIRECT_MAKE_3D=${DIRECT_MAKE_3D}"
echo "[PARAM] DIRECT_ROTATE90=${DIRECT_ROTATE90}"
echo "[PARAM] DIRECT_SLICE_INDICES=${DIRECT_SLICE_INDICES}"
echo "[PARAM] SCRIPT_22=${SCRIPT_22}"
echo "[PARAM] SCRIPT_23=${SCRIPT_23}"
echo "[PARAM] SCRIPT_24=${SCRIPT_24}"
echo "[PARAM] CONDA_ENV=${CONDA_ENV}"
echo "[PARAM] DRY_RUN=${DRY_RUN}"

run_step "STEP22" \
    bash "$SCRIPT_22" \
    --input_dir "$INITIAL_INPUT_DIR" \
    --config_file "$INITIAL_CONFIG_FILE" \
    --output_image_prefix "$INITIAL_OUTPUT_PREFIX" \
    --registered_config_file "$REGISTERED_CONFIG_FILE" \
    --make_3d "$INITIAL_MAKE_3D" \
    --rotate90 "$INITIAL_ROTATE90" \
    --rotate_positions "$INITIAL_ROTATE_POSITIONS" \
    --pixel_size_um "$PIXEL_SIZE_UM" \
    --max_shift_px "$MAX_SHIFT_PX" \
    --filter_sigma "$FILTER_SIGMA" \
    --stitch_alpha "$STITCH_ALPHA" \
    --max_error "$MAX_ERROR" \
    --slice_indices "$INITIAL_SLICE_INDICES" \
    --conda_env "$CONDA_ENV"

run_step "STEP23" \
    bash "$SCRIPT_23" \
    --if_dir "$WORK_DIR" \
    --raw_if_dir "$RAW_ROUND_DIR" \
    --registration_dir "$REGISTRATION_DIR" \
    --ref_config "$REGISTERED_CONFIG_FILE" \
    --output_ref_name "$OUTPUT_REF_NAME" \
    --output_if_name "$OUTPUT_ROUND_CONFIG_NAME" \
    --raw_prefix "$RAW_PREFIX" \
    --ref_channel "$REF_CHANNEL" \
    --channels "$CHANNELS" \
    --link_mode "$LINK_MODE" \
    --input_format "$INPUT_FORMAT" \
    --output_format "$OUTPUT_FORMAT" \
    --rotate90 "$PREPARE_ROTATE90" \
    --shift_sign "$SHIFT_SIGN" \
    --conda_env "$CONDA_ENV"

for idx in "${!DIRECT_CHANNEL_ARRAY[@]}"; do
    channel="${DIRECT_CHANNEL_ARRAY[$idx]}"
    output_prefix="${DIRECT_PREFIX_ARRAY[$idx]}"
    run_step "STEP24_${channel}" \
        bash "$SCRIPT_24" \
        --input_dir "${DIRECT_INPUT_ROOT}/${channel}" \
        --config_file "$DIRECT_CONFIG_FILE" \
        --output_image_prefix "$output_prefix" \
        --make_3d "$DIRECT_MAKE_3D" \
        --rotate90 "$DIRECT_ROTATE90" \
        --pixel_size_um "$PIXEL_SIZE_UM" \
        --slice_indices "$DIRECT_SLICE_INDICES" \
        --conda_env "$CONDA_ENV"
done

echo "STATUS: SUCCESS"
end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Elapsed time: $((end_time - start_time)) seconds"
