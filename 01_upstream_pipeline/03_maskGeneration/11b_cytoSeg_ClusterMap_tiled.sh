#!/bin/bash

#SBATCH -J clustermap_tiled
#SBATCH -o logs011_clustermap/%x_%j.out
#SBATCH -e logs011_clustermap/%x_%j.err
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 1
#SBATCH --time=48:00:00

# ClusterMap with every subtile as its own Slurm task. This job only submits and waits:
#   prepare  one task per position: load, preprocess, split, write the subtile inputs
#   tile     one task per subtile (arrays of at most ARRAY_CHUNK tasks), after all prepare tasks
#   merge    one task per position: stitch the subtile results in tile order and write the usual outputs
# Each stage starts when the previous one has finished; tasks killed for memory run again with twice the CPUs.
# Each stage is 11_cytoSeg_ClusterMap.sh --stage ...; all its options are passed through unchanged
# (--sub_num N > 0 is required: it gives the N x N subtiles of each position).
# It exits 0 only when every merge task completed, so later steps can depend on this job with afterok.

set -euo pipefail

print_usage() {
    echo "Usage: $0 [11_cytoSeg_ClusterMap.sh options] [--partition P] [--prepare_cpus N] [--tile_cpus N] [--merge_cpus N] [--stage_time T] [--array_tasks N] [--log_dir DIR]"
}

PARTITION="C64M512G"
PREPARE_CPUS="8"
TILE_CPUS="2"
MERGE_CPUS="8"
STAGE_TIME="12:00:00"
ARRAY_TASKS=""
ARRAY_CHUNK="200"
RETRIES="2"
LOG_DIR=""
PROJECT_ROOT=""
PROJECT_NAME=""
REF_ROUND="1"
DAPI_SUFFIX="ch03.tif"
OFFSET="0"
OUTPUT_LABEL="auto"
SCRIPT_DIR=""
SUB_NUM="0"
PASS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --partition) PARTITION="$2"; shift 2 ;;
        --prepare_cpus) PREPARE_CPUS="$2"; shift 2 ;;
        --tile_cpus) TILE_CPUS="$2"; shift 2 ;;
        --merge_cpus) MERGE_CPUS="$2"; shift 2 ;;
        --stage_time) STAGE_TIME="$2"; shift 2 ;;
        --array_tasks) ARRAY_TASKS="$2"; shift 2 ;;
        --log_dir) LOG_DIR="$2"; shift 2 ;;
        --stage) echo "--stage is set by this script" >&2; exit 2 ;;
        --offset) OFFSET="$2"; shift 2 ;;
        --output_label) OUTPUT_LABEL="$2"; shift 2 ;;
        --project_root) PROJECT_ROOT="$2"; PASS+=("$1" "$2"); shift 2 ;;
        --project_name) PROJECT_NAME="$2"; PASS+=("$1" "$2"); shift 2 ;;
        --ref_round) REF_ROUND="$2"; PASS+=("$1" "$2"); shift 2 ;;
        --dapi_suffix) DAPI_SUFFIX="$2"; PASS+=("$1" "$2"); shift 2 ;;
        --script_dir) SCRIPT_DIR="$2"; PASS+=("$1" "$2"); shift 2 ;;
        --sub_num) SUB_NUM="$2"; PASS+=("$1" "$2"); shift 2 ;;
        -h|--help) print_usage; exit 0 ;;
        --*) PASS+=("$1" "$2"); shift 2 ;;
        *) print_usage >&2; exit 2 ;;
    esac
done

finish() {
    local exit_code=$?
    echo "STATUS: $( (( exit_code == 0 )) && echo SUCCESS || echo FAILED ) | SLURM_JOB_NAME=${SLURM_JOB_NAME:-N/A}"
}
trap finish EXIT

WRAPPER="${SCRIPT_DIR}/11_cytoSeg_ClusterMap.sh"
[[ -f "$WRAPPER" ]] || { echo "Stage wrapper not found (--script_dir): $WRAPPER" >&2; exit 1; }
(( SUB_NUM > 0 )) || { echo "--sub_num N > 0 is required (N x N subtiles per position)" >&2; exit 2; }
TILES_PER_FOV=$((SUB_NUM * SUB_NUM))
if [[ -z "$ARRAY_TASKS" ]]; then
    printf -v ROUND_DIR "round%03d" "$((10#${REF_ROUND}))"
    TOTAL=$(find -L "${PROJECT_ROOT}/${PROJECT_NAME}/01_data/${ROUND_DIR}" -maxdepth 2 -type f -name "*${DAPI_SUFFIX}" | wc -l)
    ARRAY_TASKS=$((TOTAL - OFFSET))
fi
(( ARRAY_TASKS > 0 )) || { echo "No positions to run (array_tasks=${ARRAY_TASKS})" >&2; exit 1; }
if [[ "$OUTPUT_LABEL" == "auto" ]]; then
    # the stages must share one output directory; same name pattern as the wrapper's auto label
    OUTPUT_LABEL="$(date +%Y%m%d_%H%M%S)_${SLURM_JOB_ID:-$$}"
fi
PASS+=(--output_label "$OUTPUT_LABEL")
LOG_DIR="${LOG_DIR:-$PWD/logs011_clustermap}"
mkdir -p "$LOG_DIR"

submit() {
    # waits while the account is at its job submit limit (array tasks count), so a stage is never half submitted
    local out
    while true; do
        if out=$(sbatch --parsable -p "$PARTITION" -N 1 --time="$STAGE_TIME" -o "$LOG_DIR/%x_%A_%a.out" \
                -e "$LOG_DIR/%x_%A_%a.err" "$@" 2>&1); then
            grep -E '^[0-9]+' <<< "$out" | tail -1
            return 0
        fi
        if grep -q "SubmitJobLimit" <<< "$out"; then
            sleep 120
            continue
        fi
        echo "$out" >&2
        return 1
    done
}

wait_jobs() {
    # finished jobs leave squeue ("Invalid job id" once all are gone); any other squeue error is retried
    local out
    while true; do
        if out=$(squeue -h -j "$(IFS=,; echo "$*")" 2>&1); then
            [[ -z "$out" ]] && return 0
        elif grep -q "Invalid job id" <<< "$out"; then
            return 0
        fi
        sleep 60
    done
}

# Submit every (offset, task list) pair in ROUND_OFFSETS / ROUND_SPECS for one stage and wait for all of them.
# Tasks killed for memory are submitted again with twice the CPUs (memory follows CPUs), at most RETRIES times;
# anything else that did not complete is recorded in FAILED.
run_stage() {
    local name=$1 stage=$2 cpus=$3 attempt i j states oom bad
    local -a jobs offs specs
    for (( attempt=0; ${#ROUND_SPECS[@]} > 0; attempt++ )); do
        jobs=()
        for i in "${!ROUND_SPECS[@]}"; do
            j=$(submit -J "${PROJECT_NAME}_cm_${name}" -c "$cpus" --array="${ROUND_SPECS[$i]}" \
                "$WRAPPER" "${PASS[@]}" --offset "${ROUND_OFFSETS[$i]}" --stage "$stage" --tiles_per_fov "$TILES_PER_FOV")
            echo "${name}: offset ${ROUND_OFFSETS[$i]} tasks ${ROUND_SPECS[$i]} cpus ${cpus} -> job ${j}"
            jobs+=("$j")
            [[ "$stage" == "tile" ]] && TILE_JOBS+=("$j")
        done
        wait_jobs "${jobs[@]}"
        offs=(); specs=()
        for i in "${!jobs[@]}"; do
            states=$(sacct -X -n -P -j "${jobs[$i]}" --format=JobID,State)
            oom=$(awk -F'|' '$2 ~ /^OUT_OF_ME/ {sub(/.*_/, "", $1); print $1}' <<< "$states" | paste -sd, -)
            bad=$(awk -F'|' '$2 != "COMPLETED" && $2 !~ /^OUT_OF_ME/ {sub(/.*_/, "", $1); print $1}' <<< "$states" | paste -sd, -)
            [[ -n "$bad" ]] && FAILED+=("${name} offset ${ROUND_OFFSETS[$i]} tasks ${bad}")
            if [[ -n "$oom" ]]; then
                if (( attempt < RETRIES )); then
                    offs+=("${ROUND_OFFSETS[$i]}"); specs+=("$oom")
                else
                    FAILED+=("${name} offset ${ROUND_OFFSETS[$i]} tasks ${oom} (out of memory at ${cpus} CPUs)")
                fi
            fi
        done
        ROUND_OFFSETS=(${offs[@]+"${offs[@]}"}); ROUND_SPECS=(${specs[@]+"${specs[@]}"})
        cpus=$((cpus * 2 > 64 ? 64 : cpus * 2))
    done
}

echo "Start: $(date '+%Y-%m-%d %H:%M:%S') | positions ${ARRAY_TASKS} (offset ${OFFSET}) x ${TILES_PER_FOV} subtiles | output label ${OUTPUT_LABEL}"
FAILED=(); TILE_JOBS=()
ROUND_OFFSETS=("$OFFSET"); ROUND_SPECS=("1-${ARRAY_TASKS}")
run_stage prepare prepare "$PREPARE_CPUS"
ROUND_OFFSETS=(); ROUND_SPECS=()
N_TILES=$((ARRAY_TASKS * TILES_PER_FOV))
for (( start=0; start<N_TILES; start+=ARRAY_CHUNK )); do
    ROUND_OFFSETS+=("$((OFFSET * TILES_PER_FOV + start))")
    ROUND_SPECS+=("1-$(( N_TILES - start < ARRAY_CHUNK ? N_TILES - start : ARRAY_CHUNK ))")
done
run_stage tile tile "$TILE_CPUS"
ROUND_OFFSETS=("$OFFSET"); ROUND_SPECS=("1-${ARRAY_TASKS}")
run_stage merge merge "$MERGE_CPUS"

# process_tile turns an exception into "no cells"; in a merged result that would pass silently
tile_errors=$(for j in "${TILE_JOBS[@]}"; do cat "$LOG_DIR/${PROJECT_NAME}_cm_tile_${j}"_*.out 2>/dev/null; done | grep -c "^Error processing tile" || true)
echo "End: $(date '+%Y-%m-%d %H:%M:%S') | tasks not completed: ${#FAILED[@]} | tile errors: ${tile_errors}"
for f in ${FAILED[@]+"${FAILED[@]}"}; do echo "  not completed: $f"; done
if (( ${#FAILED[@]} > 0 || tile_errors > 0 )); then
    exit 1
fi
