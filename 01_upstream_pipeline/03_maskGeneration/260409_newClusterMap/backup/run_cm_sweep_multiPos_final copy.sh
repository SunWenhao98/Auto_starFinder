#!/usr/bin/env bash
set -euo pipefail

# =========================================================
# run_cm_sweep_multiPos_final.sh
#
# bash run_cm_sweep_multiPos-V9.sh params-ky8.tsv  "Position1,Position109,Position217"
# bash run_cm_sweep_multiPos-V9.sh params-ky6.tsv  "Position1-108"
# =========================================================

BASE="/gpfs/share/home/2300012257/01_project/03_Cell_Segmentation/20260324_rapid_ClusterMap"

# 请根据你的实际情况修改这个Python环境变量（确保安装了ClusterMap等依赖）
PY="${PY:-/gpfs/share/home/2300012257/anaconda3/envs/ClusterMap/bin/python}"
# 脚本文件已分离至代码库
SCRIPT="/gpfs/share/home/2300012257/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/03_maskGeneration/new_clustermaptest_dist_ky_fast_new copy.py"

# 参数文件在 00_registration 里
PARAM_TSV="${1:-${BASE}/00_registration/params.tsv}"
POS_SPEC="${2:-Position012}"

Z_NUM=42
XY_SIZE=2048
GENE_CSV="${BASE}/01_data/genes.csv"
IDN="4"
ROUND_DAPI="round001"     # 目录名：round001
DAPI_ROUND_NUM="1"        # 传给 -IDR 的值（保持你原来固定 1）

LOG_ROOT="${BASE}/logs"
WORK_ROOT_BASE="${BASE}/00_registration/tmp"
OUT_ROOT_BASE="${BASE}/00_registration"

WINDOW_SIZE=300
OVERLAP=0.2

ARRAY_CONCURRENCY=20

PARTITION="C64M512G"
QOS="normal"

PREP_CPUS=60
PREP_MEM="480G"
PREP_TIME="08:00:00"

DRIVER_CPUS=1
DRIVER_MEM="2G"
DRIVER_TIME="00:30:00"

TILE_CPUS=8
TILE_MEM="128G"
TILE_TIME="24:00:00"

STITCH_CPUS=16
STITCH_MEM="192G"
STITCH_TIME="12:00:00"

RETRY_CPUS=60
RETRY_MEM="480G"
RETRY_TIME="24:00:00"
RETRY_CONCURRENCY=12
RETRY_ROUNDS=20

RESCUE_CPUS=4
RESCUE_MEM="16G"
RESCUE_TIME="04:00:00"

SHARE_PREP_ACROSS_PARAMS="${SHARE_PREP_ACROSS_PARAMS:-1}"
MAX_LIVE_PIPELINES="${MAX_LIVE_PIPELINES:-0}"
DRY_RUN="${DRY_RUN:-0}"

EXPORT_POLYGONS="${EXPORT_POLYGONS:-F}"
EXPORT_QC_PLOTS="${EXPORT_QC_PLOTS:-F}"
ROTATION="${ROTATION:-0}"
READS_FILTER="${READS_FILTER:-5}"
DAPI_SUFFIX="${DAPI_SUFFIX:-ch03.tif}"

SBATCH_RETRIES="${SBATCH_RETRIES:-6}"
SBATCH_RETRY_SLEEP="${SBATCH_RETRY_SLEEP:-2}"

mkdir -p "$LOG_ROOT"
RUN_ID="$(date +%Y%m%d_%H%M%S)_$$"

log(){ echo "$@" >&2; }
need_cmd(){ command -v "$1" >/dev/null 2>&1 || { log "ERROR: missing command: $1"; exit 1; }; }

need_cmd sbatch
need_cmd squeue
need_cmd awk
need_cmd sed
need_cmd date

[[ -x "$PY" ]] || { log "ERROR: PY not executable: $PY"; exit 1; }
[[ -f "$SCRIPT" ]] || { log "ERROR: SCRIPT not found: $SCRIPT"; exit 1; }
[[ -f "$PARAM_TSV" ]] || { log "ERROR: PARAM_TSV not found: $PARAM_TSV"; exit 1; }

log "[INFO] PY=$PY"
log "[INFO] SCRIPT=$SCRIPT"
log "[INFO] PARAM_TSV=$PARAM_TSV"
log "[INFO] POS_SPEC=$POS_SPEC"
log "[INFO] LOG_ROOT=$LOG_ROOT"
log "[INFO] SHARE_PREP_ACROSS_PARAMS=$SHARE_PREP_ACROSS_PARAMS"
log "[INFO] MAX_LIVE_PIPELINES=$MAX_LIVE_PIPELINES"
log "[INFO] DRY_RUN=$DRY_RUN"
log "[INFO] SBATCH_RETRIES=$SBATCH_RETRIES SBATCH_RETRY_SLEEP=$SBATCH_RETRY_SLEEP"

# ---------- 原子写文件（必须带目标路径） ----------
write_atomic() {
  local dst="${1:?write_atomic: missing destination path}"
  local tmp
  tmp="$(mktemp "${dst}.tmp.XXXXXX")"
  cat > "$tmp"
  chmod +x "$tmp"
  mv -f "$tmp" "$dst"
}

# ---------- sbatch 重试 ----------
sbatch_retry() {
  local attempt=1
  local sleep_s="${SBATCH_RETRY_SLEEP}"
  local out
  while (( attempt <= SBATCH_RETRIES )); do
    set +e
    out="$(sbatch --parsable "$@" 2>&1)"
    local rc=$?
    set -e
    if (( rc == 0 )) && [[ "$out" =~ ^[0-9]+ ]]; then
      echo "$out"
      return 0
    fi
    log "[WARN] sbatch failed (attempt ${attempt}/${SBATCH_RETRIES}, rc=${rc})"
    log "[WARN] sbatch output: ${out}"
    if (( attempt == SBATCH_RETRIES )); then
      log "[ERROR] sbatch still failing after retries."
      return 99
    fi
    log "[RETRY] sleep ${sleep_s}s then retry..."
    sleep "${sleep_s}"
    sleep_s=$(( sleep_s * 2 ))
    attempt=$(( attempt + 1 ))
  done
  return 99
}

# ---------- Position 展开 ----------
expand_pos_spec() {
  local spec="$1"
  local tok
  spec="${spec//,/ }"
  for tok in $spec; do
    if [[ "$tok" =~ ^[Pp]osition([0-9]+)-([0-9]+)$ ]]; then
      local a="${BASH_REMATCH[1]}" b="${BASH_REMATCH[2]}"
      if (( a <= b )); then for ((i=a;i<=b;i++)); do echo "Position${i}"; done
      else for ((i=a;i>=b;i--)); do echo "Position${i}"; done; fi
    elif [[ "$tok" =~ ^([0-9]+)-([0-9]+)$ ]]; then
      local a="${BASH_REMATCH[1]}" b="${BASH_REMATCH[2]}"
      if (( a <= b )); then for ((i=a;i<=b;i++)); do echo "Position${i}"; done
      else for ((i=a;i>=b;i--)); do echo "Position${i}"; done; fi
    else
      if [[ "$tok" =~ ^[Pp]osition[0-9]+$ ]]; then
        local n="${tok#[Pp]osition}"
        echo "Position${n}"
      else
        log "ERROR: cannot parse position token: $tok"
        exit 2
      fi
    fi
  done
}
mapfile -t POS_LIST < <(expand_pos_spec "$POS_SPEC" | awk '!seen[$0]++')
log "[INFO] Expanded positions: ${#POS_LIST[@]} -> ${POS_LIST[*]}"

# ---------- params TSV ----------
mapfile -t PARAM_LINES < <(awk 'BEGIN{FS="[ \t]+"} !/^#/ && NF>=6 {print $1"\t"$2"\t"$3"\t"$4"\t"$5"\t"$6}' "$PARAM_TSV")
log "[INFO] Params lines: ${#PARAM_LINES[@]}"
(( ${#PARAM_LINES[@]} > 0 )) || { log "ERROR: PARAM_TSV has no valid lines (need: tag IC ID IPF ICR_xy ICR_z)."; exit 3; }

IFS=$'\t' read -r PREP_TAG PREP_IC PREP_ID PREP_IPF PREP_ICR_XY PREP_ICR_Z <<< "${PARAM_LINES[0]}"
log "[INFO] PREP canonical param (from first line): TAG=${PREP_TAG} IC=${PREP_IC} ID=${PREP_ID} IPF=${PREP_IPF} ICR=${PREP_ICR_XY},${PREP_ICR_Z}"

# ---------- throttle ----------
count_live_pipelines() {
  squeue -u "$USER" -h -o "%j" 2>/dev/null | awk '$0 ~ /^cm_(prep|drive|tile|rescue|stitch|retry)_/ {c++} END{print c+0}'
}
throttle_if_needed() {
  (( MAX_LIVE_PIPELINES > 0 )) || return 0
  while true; do
    local live
    live="$(count_live_pipelines)"
    if (( live < MAX_LIVE_PIPELINES )); then return 0; fi
    log "[THROTTLE] live cm_* jobs=${live} >= MAX_LIVE_PIPELINES=${MAX_LIVE_PIPELINES}, sleep 20s..."
    sleep 20
  done
}

# ---------- done 判定 ----------
is_done_strict() {
  local out_dir="$1"
  local work_dir="$2"
  [[ -s "${out_dir}/model_final.pkl" ]] || return 1
  [[ -s "${out_dir}/remain_reads_raw.csv" || -s "${out_dir}/remain_reads.csv" ]] || return 1
  if [[ -e "${out_dir}/cell_center.csv" && ! -s "${out_dir}/cell_center.csv" ]]; then
    return 1
  fi
  if compgen -G "${work_dir}/tile_results/tile_*.pkl" > /dev/null; then
    local newest_tile
    newest_tile="$(ls -1t "${work_dir}/tile_results"/tile_*.pkl 2>/dev/null | head -n 1 || true)"
    if [[ -n "${newest_tile}" ]]; then
      if [[ "${out_dir}/model_final.pkl" -ot "${newest_tile}" ]]; then
        return 1
      fi
    fi
  fi
  return 0
}

# ---------- 写模板（一定要用 write_atomic "$dst" <<EOF） ----------
TPL_DIR="${LOG_ROOT}/_templates_${RUN_ID}"
mkdir -p "$TPL_DIR"

PREP_SBATCH="${TPL_DIR}/sbatch_prep.sh"
TILES_SBATCH="${TPL_DIR}/sbatch_tiles.sh"
RETRY_SBATCH="${TPL_DIR}/sbatch_retry.sh"
RESCUE_SBATCH="${TPL_DIR}/sbatch_rescue.sh"
STITCH_SBATCH="${TPL_DIR}/sbatch_stitch.sh"
DRIVER_SBATCH="${TPL_DIR}/sbatch_driver.sh"

# ---- PREP ----
write_atomic "$PREP_SBATCH" <<EOF
#!/bin/bash
#SBATCH -p ${PARTITION}
#SBATCH --qos=${QOS}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=${PREP_CPUS}
#SBATCH --mem=${PREP_MEM}
#SBATCH --time=${PREP_TIME}
#SBATCH -o ${LOG_ROOT}/%x.%j.out
#SBATCH -e ${LOG_ROOT}/%x.%j.err
set -euo pipefail

ts(){ date +"%F %T"; }
echo "[\$(ts)] [BEGIN] stage=prep jobid=\${SLURM_JOB_ID} node=\${SLURMD_NODENAME:-NA} POS=\${POS}" >&2

: "\${PY:?}" "\${SCRIPT:?}" "\${BASE:?}" "\${POS:?}" "\${Z_NUM:?}" "\${XY_SIZE:?}" "\${GENE_CSV:?}" "\${DAPI_DIR:?}" "\${GOOD_POINTS:?}" "\${IDN:?}" "\${SHARED_PREP_DIR:?}"
: "\${PREP_IC:?}" "\${PREP_ID:?}" "\${PREP_IPF:?}" "\${PREP_ICR_XY:?}" "\${PREP_ICR_Z:?}"
: "\${WINDOW_SIZE:?}" "\${OVERLAP:?}"
: "\${DAPI_ROUND_NUM:?}" "\${ROTATION:?}" "\${READS_FILTER:?}"

mkdir -p "\${SHARED_PREP_DIR}"

if [[ -s "\${SHARED_PREP_DIR}/manifest.json" && -s "\${SHARED_PREP_DIR}/out.pkl" && -s "\${SHARED_PREP_DIR}/global_spots.pkl" && -d "\${SHARED_PREP_DIR}/tiles" ]]; then
  echo "[\$(ts)] PREP skip (exists): \${SHARED_PREP_DIR}" >&2
  echo "[\$(ts)] [END] stage=prep status=SKIP" >&2
  exit 0
fi

ICR="\${PREP_ICR_XY},\${PREP_ICR_Z}"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1

"\${PY}" "\${SCRIPT}" \\
  -IP "\${POS}" -IZ "\${Z_NUM}" -IEP F \\
  -IDir "\${BASE}" \\
  -Igenecsv "\${GENE_CSV}" \\
  -IDapi_path "\${DAPI_DIR}" \\
  -IXY "\${XY_SIZE}" -IC "\${PREP_IC}" -ID "\${PREP_ID}" -IDR "\${DAPI_ROUND_NUM}" -IPF "\${PREP_IPF}" -ICR "\${ICR}" \\
  -OP "\${SHARED_PREP_DIR}" \\
  -Igood_points_max3d "\${GOOD_POINTS}" \\
  -IDN "\${IDN}" \\
  --stage prep \\
  --work_dir "\${SHARED_PREP_DIR}" \\
  --window_size "\${WINDOW_SIZE}" \\
  --overlap_percent "\${OVERLAP}" \\
  --rotation "\${ROTATION}" \\
  --reads_filter "\${READS_FILTER}"

[[ -s "\${SHARED_PREP_DIR}/manifest.json" && -s "\${SHARED_PREP_DIR}/out.pkl" ]] || { echo "[\$(ts)] PREP ERROR: missing manifest/out.pkl" >&2; exit 2; }
[[ -d "\${SHARED_PREP_DIR}/tiles" ]] || { echo "[\$(ts)] PREP ERROR: missing tiles/ dir" >&2; exit 3; }
[[ -s "\${SHARED_PREP_DIR}/global_spots.pkl" ]] || { echo "[\$(ts)] PREP ERROR: missing global_spots.pkl" >&2; exit 5; }
ls -1 "\${SHARED_PREP_DIR}/tiles"/tile_00000.npz >/dev/null 2>&1 || { echo "[\$(ts)] PREP ERROR: tiles missing tile_00000.npz" >&2; exit 4; }

echo "[\$(ts)] [END] stage=prep status=OK" >&2
EOF

# ---- TILES ----
write_atomic "$TILES_SBATCH" <<EOF
#!/bin/bash
#SBATCH -p ${PARTITION}
#SBATCH --qos=${QOS}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=${TILE_CPUS}
#SBATCH --mem=${TILE_MEM}
#SBATCH --time=${TILE_TIME}
#SBATCH -o ${LOG_ROOT}/%x.%A_%a.out
#SBATCH -e ${LOG_ROOT}/%x.%A_%a.err
set -euo pipefail

ts(){ date +"%F %T"; }
echo "[\$(ts)] [BEGIN] stage=tile jobid=\${SLURM_JOB_ID} array=\${SLURM_ARRAY_JOB_ID}.\${SLURM_ARRAY_TASK_ID} node=\${SLURMD_NODENAME:-NA} POS=\${POS} TAG=\${TAG}" >&2

: "\${PY:?}" "\${SCRIPT:?}" "\${BASE:?}" "\${POS:?}" "\${TAG:?}" "\${Z_NUM:?}" "\${XY_SIZE:?}" "\${GENE_CSV:?}" "\${DAPI_DIR:?}" "\${GOOD_POINTS:?}" "\${IDN:?}" "\${WORK_DIR:?}" "\${OUT_DIR:?}"
: "\${IC:?}" "\${ID:?}" "\${IPF:?}" "\${ICR_XY:?}" "\${ICR_Z:?}"
: "\${SHARED_PREP_DIR:?}" "\${DAPI_ROUND_NUM:?}"

# tiles link
if [[ ! -e "\${WORK_DIR}/tiles" ]]; then
  ln -sfn "\${SHARED_PREP_DIR}/tiles" "\${WORK_DIR}/tiles"
fi

MANIFEST="\${WORK_DIR}/manifest.json"
[[ -f "\${MANIFEST}" ]] || { echo "ERROR: manifest missing: \${MANIFEST}" >&2; exit 2; }

N_TILES=\$("\${PY}" - <<PY
import json
print(json.load(open("\${MANIFEST}"))["n_tiles"])
PY
)

TID=\${SLURM_ARRAY_TASK_ID}
[[ "\${TID}" -lt "\${N_TILES}" ]] || { echo "[\$(ts)] [END] stage=tile status=SKIP_out_of_range tid=\${TID} n=\${N_TILES}" >&2; exit 0; }

sleep \$(( (TID % 20) * 2 ))

thr=\${SLURM_CPUS_PER_TASK:-1}
(( thr > 8 )) && thr=8
export OMP_NUM_THREADS=\$thr MKL_NUM_THREADS=\$thr OPENBLAS_NUM_THREADS=\$thr NUMEXPR_NUM_THREADS=\$thr

OUTPKL="\${WORK_DIR}/tile_results/tile_\$(printf "%05d" "\${TID}").pkl"
if [[ -s "\${OUTPKL}" ]]; then
  if "\${PY}" - <<PY
import joblib, sys
p=r"""\${OUTPKL}"""
try:
    obj=joblib.load(p)
    sys.exit(0)
except Exception:
    sys.exit(3)
PY
  then
    echo "[\$(ts)] [END] stage=tile status=SKIP_exists tid=\${TID}" >&2
    exit 0
  fi
fi

ICR="\${ICR_XY},\${ICR_Z}"

"\${PY}" "\${SCRIPT}" \\
  -IP "\${POS}" -IZ "\${Z_NUM}" -IEP F \\
  -IDir "\${BASE}" \\
  -Igenecsv "\${GENE_CSV}" \\
  -IDapi_path "\${DAPI_DIR}" \\
  -IXY "\${XY_SIZE}" -IC "\${IC}" -ID "\${ID}" -IDR "\${DAPI_ROUND_NUM}" -IPF "\${IPF}" -ICR "\${ICR}" \\
  -OP "\${OUT_DIR}" \\
  -Igood_points_max3d "\${GOOD_POINTS}" \\
  -IDN "\${IDN}" \\
  --stage tile \\
  --work_dir "\${WORK_DIR}" \\
  --tile_id "\${TID}"

echo "[\$(ts)] [END] stage=tile status=OK tid=\${TID}" >&2
EOF

# ---- RETRY（复用 tiles 模板内容）----
cp -f "$TILES_SBATCH" "$RETRY_SBATCH"
chmod +x "$RETRY_SBATCH"

# ---- RESCUE ----
write_atomic "$RESCUE_SBATCH" <<EOF
#!/bin/bash
#SBATCH -p ${PARTITION}
#SBATCH --qos=${QOS}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=${RESCUE_CPUS}
#SBATCH --mem=${RESCUE_MEM}
#SBATCH --time=${RESCUE_TIME}
#SBATCH -o ${LOG_ROOT}/%x.%j.out
#SBATCH -e ${LOG_ROOT}/%x.%j.err
set -euo pipefail

ts(){ date +"%F %T"; }
echo "[\$(ts)] [BEGIN] stage=rescue jobid=\${SLURM_JOB_ID} node=\${SLURMD_NODENAME:-NA} POS=\${POS} TAG=\${TAG}" >&2

: "\${PY:?}" "\${WORK_DIR:?}" "\${POS:?}" "\${TAG:?}" "\${OUT_DIR:?}"
: "\${RETRY_CPUS:?}" "\${RETRY_MEM:?}" "\${RETRY_TIME:?}" "\${RETRY_CONCURRENCY:?}" "\${RETRY_ROUNDS:?}"
: "\${SCRIPT:?}" "\${BASE:?}" "\${Z_NUM:?}" "\${XY_SIZE:?}" "\${GENE_CSV:?}" "\${DAPI_DIR:?}" "\${GOOD_POINTS:?}" "\${IDN:?}"
: "\${IC:?}" "\${ID:?}" "\${IPF:?}" "\${ICR_XY:?}" "\${ICR_Z:?}"
: "\${SHARED_PREP_DIR:?}" "\${DAPI_ROUND_NUM:?}"

RETRY_SBATCH="${RETRY_SBATCH}"

MANIFEST="\${WORK_DIR}/manifest.json"
[[ -f "\${MANIFEST}" ]] || { echo "ERROR: manifest missing: \${MANIFEST}" >&2; exit 2; }

N_TILES=\$("\${PY}" - <<PY
import json
print(json.load(open("\${MANIFEST}"))["n_tiles"])
PY
)

missing_list() {
  N_TILES="\${N_TILES}" WORK_DIR="\${WORK_DIR}" "\${PY}" - <<'PY'
import os, joblib
work=os.environ["WORK_DIR"]
n=int(os.environ["N_TILES"])
tile_out=os.path.join(work,"tile_results")
miss=[]
for t in range(n):
    p=os.path.join(tile_out, f"tile_{t:05d}.pkl")
    if (not os.path.exists(p)) or os.path.getsize(p)==0:
        miss.append(t); continue
    try:
        obj=joblib.load(p)
    except Exception:
        miss.append(t)
print(",".join(map(str, miss)))
PY
}

ROUND=0
while (( ROUND <= RETRY_ROUNDS )); do
  MISS="\$(missing_list)"
  if [[ -z "\${MISS}" ]]; then
    echo "[\$(ts)] RESCUE ok (no missing)" >&2
    echo "[\$(ts)] [END] stage=rescue status=OK" >&2
    exit 0
  fi
  echo "[\$(ts)] RESCUE missing (round=\${ROUND}): \${MISS}" >&2

  if (( ROUND == RETRY_ROUNDS )); then
    echo "[\$(ts)] [END] stage=rescue status=FAIL still_missing" >&2
    exit 3
  fi

  RETRY_EXPORTS="ALL,PY=\${PY},SCRIPT=\${SCRIPT},BASE=\${BASE},POS=\${POS},TAG=\${TAG},Z_NUM=\${Z_NUM},XY_SIZE=\${XY_SIZE},GENE_CSV=\${GENE_CSV},DAPI_DIR=\${DAPI_DIR},GOOD_POINTS=\${GOOD_POINTS},IDN=\${IDN},WORK_DIR=\${WORK_DIR},OUT_DIR=\${OUT_DIR},IC=\${IC},ID=\${ID},IPF=\${IPF},ICR_XY=\${ICR_XY},ICR_Z=\${ICR_Z},SHARED_PREP_DIR=\${SHARED_PREP_DIR},DAPI_ROUND_NUM=\${DAPI_ROUND_NUM}"

  RETRY_JOBID=\$(sbatch --parsable \\
    --job-name="cm_retry_\${POS}_\${TAG}_\${ROUND}" \\
    --array="\${MISS}%\${RETRY_CONCURRENCY}" \\
    --cpus-per-task="\${RETRY_CPUS}" \\
    --mem="\${RETRY_MEM}" \\
    --time="\${RETRY_TIME}" \\
    --export="\${RETRY_EXPORTS}" \\
    "\${RETRY_SBATCH}")

  while squeue -j "\${RETRY_JOBID}" -h 2>/dev/null | grep -q .; do
    sleep 30
  done

  ROUND=\$((ROUND+1))
done

echo "[\$(ts)] [END] stage=rescue status=FAIL unexpected" >&2
exit 9
EOF

# ---- STITCH ----
write_atomic "$STITCH_SBATCH" <<EOF
#!/bin/bash
#SBATCH -p ${PARTITION}
#SBATCH --qos=${QOS}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=${STITCH_CPUS}
#SBATCH --mem=${STITCH_MEM}
#SBATCH --time=${STITCH_TIME}
#SBATCH -o ${LOG_ROOT}/%x.%j.out
#SBATCH -e ${LOG_ROOT}/%x.%j.err
set -euo pipefail

ts(){ date +"%F %T"; }
echo "[\$(ts)] [BEGIN] stage=stitch jobid=\${SLURM_JOB_ID} node=\${SLURMD_NODENAME:-NA} POS=\${POS} TAG=\${TAG}" >&2

: "\${PY:?}" "\${SCRIPT:?}" "\${BASE:?}" "\${POS:?}" "\${TAG:?}" "\${Z_NUM:?}" "\${XY_SIZE:?}" "\${GENE_CSV:?}" "\${DAPI_DIR:?}" "\${GOOD_POINTS:?}" "\${IDN:?}" "\${WORK_DIR:?}" "\${OUT_DIR:?}"
: "\${IC:?}" "\${ID:?}" "\${IPF:?}" "\${ICR_XY:?}" "\${ICR_Z:?}" "\${DAPI_ROUND_NUM:?}" "\${EXPORT_POLYGONS:?}" "\${EXPORT_QC_PLOTS:?}"

DONE_MARK="\${OUT_DIR}/.cm_done"
if [[ -f "\${DONE_MARK}" || -f "\${OUT_DIR}/model_final.pkl" ]]; then
  echo "[\$(ts)] [END] stage=stitch status=SKIP_done" >&2
  exit 0
fi

thr=\${SLURM_CPUS_PER_TASK:-1}
(( thr > 16 )) && thr=16
export OMP_NUM_THREADS=\$thr MKL_NUM_THREADS=\$thr OPENBLAS_NUM_THREADS=\$thr NUMEXPR_NUM_THREADS=\$thr

ICR="\${ICR_XY},\${ICR_Z}"

"\${PY}" "\${SCRIPT}" \\
  -IP "\${POS}" -IZ "\${Z_NUM}" -IEP F \\
  -IDir "\${BASE}" \\
  -Igenecsv "\${GENE_CSV}" \\
  -IDapi_path "\${DAPI_DIR}" \\
  -IXY "\${XY_SIZE}" -IC "\${IC}" -ID "\${ID}" -IDR "\${DAPI_ROUND_NUM}" -IPF "\${IPF}" -ICR "\${ICR}" \\
  -OP "\${OUT_DIR}" \\
  -Igood_points_max3d "\${GOOD_POINTS}" \\
  -IDN "\${IDN}" \\
  --stage stitch \\
  --work_dir "\${WORK_DIR}" \\
  --export_polygons "\${EXPORT_POLYGONS}" \\
  --export_qc_plots "\${EXPORT_QC_PLOTS}"

touch "\${DONE_MARK}"
echo "[\$(ts)] [END] stage=stitch status=OK" >&2
EOF

# ---- DRIVER（模板路径直接写死为本次生成的绝对路径，避免变空）----
write_atomic "$DRIVER_SBATCH" <<EOF
#!/bin/bash
#SBATCH -p ${PARTITION}
#SBATCH --qos=${QOS}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=${DRIVER_CPUS}
#SBATCH --mem=${DRIVER_MEM}
#SBATCH --time=${DRIVER_TIME}
#SBATCH -o ${LOG_ROOT}/%x.%j.out
#SBATCH -e ${LOG_ROOT}/%x.%j.err
set -euo pipefail

ts(){ date +"%F %T"; }
echo "[\$(ts)] [BEGIN] stage=drive jobid=\${SLURM_JOB_ID} node=\${SLURMD_NODENAME:-NA} POS=\${POS} TAG=\${TAG}" >&2

: "\${PY:?}" "\${POS:?}" "\${TAG:?}" "\${WORK_DIR:?}" "\${OUT_DIR:?}" "\${SHARED_PREP_DIR:?}"
: "\${ARRAY_CONCURRENCY:?}"
: "\${SCRIPT:?}" "\${BASE:?}" "\${Z_NUM:?}" "\${XY_SIZE:?}" "\${GENE_CSV:?}" "\${DAPI_DIR:?}" "\${GOOD_POINTS:?}" "\${IDN:?}"
: "\${IC:?}" "\${ID:?}" "\${IPF:?}" "\${ICR_XY:?}" "\${ICR_Z:?}" "\${DAPI_ROUND_NUM:?}"
: "\${RETRY_CPUS:?}" "\${RETRY_MEM:?}" "\${RETRY_TIME:?}" "\${RETRY_CONCURRENCY:?}" "\${RETRY_ROUNDS:?}" "\${EXPORT_POLYGONS:?}" "\${EXPORT_QC_PLOTS:?}"

TILES_SBATCH="${TILES_SBATCH}"
RESCUE_SBATCH="${RESCUE_SBATCH}"
STITCH_SBATCH="${STITCH_SBATCH}"
RETRY_SBATCH="${RETRY_SBATCH}"

[[ -s "\${TILES_SBATCH}"  ]] || { echo "[\$(ts)] DRIVER ERROR: tiles sbatch empty/missing: \${TILES_SBATCH}" >&2; exit 90; }
[[ -s "\${RESCUE_SBATCH}" ]] || { echo "[\$(ts)] DRIVER ERROR: rescue sbatch empty/missing: \${RESCUE_SBATCH}" >&2; exit 91; }
[[ -s "\${STITCH_SBATCH}" ]] || { echo "[\$(ts)] DRIVER ERROR: stitch sbatch empty/missing: \${STITCH_SBATCH}" >&2; exit 92; }
[[ -s "\${RETRY_SBATCH}"  ]] || { echo "[\$(ts)] DRIVER ERROR: retry sbatch empty/missing: \${RETRY_SBATCH}" >&2; exit 93; }

mkdir -p "\${WORK_DIR}/tile_results" "\${OUT_DIR}"

ln -sf "\${SHARED_PREP_DIR}/manifest.json"      "\${WORK_DIR}/manifest.json"
ln -sf "\${SHARED_PREP_DIR}/out.pkl"            "\${WORK_DIR}/out.pkl"
ln -sf "\${SHARED_PREP_DIR}/global_spots.pkl"   "\${WORK_DIR}/global_spots.pkl"

if [[ -e "\${WORK_DIR}/tiles" && ! -L "\${WORK_DIR}/tiles" ]]; then
  rm -rf "\${WORK_DIR}/tiles"
fi
ln -sfn "\${SHARED_PREP_DIR}/tiles" "\${WORK_DIR}/tiles"

MANIFEST="\${WORK_DIR}/manifest.json"
[[ -f "\${MANIFEST}" ]] || { echo "[\$(ts)] DRIVER ERROR: manifest missing" >&2; exit 2; }
ls -1 "\${WORK_DIR}/tiles"/tile_00000.npz >/dev/null 2>&1 || { echo "[\$(ts)] DRIVER ERROR: tiles missing tile_00000.npz" >&2; exit 4; }
[[ -s "\${WORK_DIR}/global_spots.pkl" ]] || { echo "[\$(ts)] DRIVER ERROR: global_spots.pkl missing" >&2; exit 7; }

N_TILES=\$("\${PY}" - <<PY
import json
print(json.load(open("\${MANIFEST}"))["n_tiles"])
PY
)
[[ "\${N_TILES}" =~ ^[0-9]+$ ]] || { echo "[\$(ts)] DRIVER ERROR: bad n_tiles=\${N_TILES}" >&2; exit 5; }
(( N_TILES > 0 )) || { echo "[\$(ts)] DRIVER ERROR: n_tiles<=0" >&2; exit 6; }

ARRAY_SPEC="0-\$((N_TILES-1))%\${ARRAY_CONCURRENCY}"
echo "[\$(ts)] DRIVER submit tiles POS=\${POS} TAG=\${TAG} n_tiles=\${N_TILES} array=\${ARRAY_SPEC}" >&2

TILE_EXPORTS="ALL,PY=\${PY},SCRIPT=\${SCRIPT},BASE=\${BASE},POS=\${POS},TAG=\${TAG},Z_NUM=\${Z_NUM},XY_SIZE=\${XY_SIZE},GENE_CSV=\${GENE_CSV},DAPI_DIR=\${DAPI_DIR},GOOD_POINTS=\${GOOD_POINTS},IDN=\${IDN},WORK_DIR=\${WORK_DIR},OUT_DIR=\${OUT_DIR},IC=\${IC},ID=\${ID},IPF=\${IPF},ICR_XY=\${ICR_XY},ICR_Z=\${ICR_Z},SHARED_PREP_DIR=\${SHARED_PREP_DIR},DAPI_ROUND_NUM=\${DAPI_ROUND_NUM}"

TILES_JOBID=\$(sbatch --parsable \\
  --job-name="cm_tile_\${POS}_\${TAG}" \\
  --array="\${ARRAY_SPEC}" \\
  --export="\${TILE_EXPORTS}" \\
  "\${TILES_SBATCH}")

POST_EXPORTS="ALL,PY=\${PY},SCRIPT=\${SCRIPT},BASE=\${BASE},POS=\${POS},TAG=\${TAG},Z_NUM=\${Z_NUM},XY_SIZE=\${XY_SIZE},GENE_CSV=\${GENE_CSV},DAPI_DIR=\${DAPI_DIR},GOOD_POINTS=\${GOOD_POINTS},IDN=\${IDN},WORK_DIR=\${WORK_DIR},OUT_DIR=\${OUT_DIR},IC=\${IC},ID=\${ID},IPF=\${IPF},ICR_XY=\${ICR_XY},ICR_Z=\${ICR_Z},SHARED_PREP_DIR=\${SHARED_PREP_DIR},DAPI_ROUND_NUM=\${DAPI_ROUND_NUM},RETRY_CPUS=\${RETRY_CPUS},RETRY_MEM=\${RETRY_MEM},RETRY_TIME=\${RETRY_TIME},RETRY_CONCURRENCY=\${RETRY_CONCURRENCY},RETRY_ROUNDS=\${RETRY_ROUNDS},EXPORT_POLYGONS=\${EXPORT_POLYGONS},EXPORT_QC_PLOTS=\${EXPORT_QC_PLOTS}"

RESCUE_JOBID=\$(sbatch --parsable \\
  --job-name="cm_rescue_\${POS}_\${TAG}" \\
  --dependency="afterany:\${TILES_JOBID}" \\
  --export="\${POST_EXPORTS}" \\
  "\${RESCUE_SBATCH}")

STITCH_JOBID=\$(sbatch --parsable \\
  --job-name="cm_stitch_\${POS}_\${TAG}" \\
  --dependency="afterok:\${RESCUE_JOBID}" \\
  --export="\${POST_EXPORTS}" \\
  "\${STITCH_SBATCH}")

echo -e "\${POS}\t\${TAG}\t\${IC}\t\${ID}\t\${IPF}\t\${ICR_XY}\t\${ICR_Z}\t\${TILES_JOBID}\t\${RESCUE_JOBID}\t\${STITCH_JOBID}" >> "${LOG_ROOT}/submitted.tsv"
echo "[\$(ts)] [END] stage=drive status=OK tiles=\${TILES_JOBID} rescue=\${RESCUE_JOBID} stitch=\${STITCH_JOBID}" >&2
EOF

# ---------- 提交 PREP ----------
submit_prep_for_position() {
  local POS="$1"
  local POS_ROOT_WORK="${WORK_ROOT_BASE}/${POS}"
  local SHARED_PREP_DIR="${POS_ROOT_WORK}/_shared_prep"

  local DAPI_BASE="${BASE}/01_data/${ROUND_DAPI}/${POS}"
  local DAPI_DIR=""
  if [[ -d "$DAPI_BASE" ]]; then
      DAPI_DIR=$(find "${DAPI_BASE}" -maxdepth 2 -name "*${DAPI_SUFFIX}" | sort -V | head -n 1)
  fi
  [[ -n "$DAPI_DIR" && -f "$DAPI_DIR" ]] || { log "[WARN] skip PREP ${POS}: DAPI missing in $DAPI_BASE"; echo ""; return 0; }
  
  # 直接读取原始带后缀的表，后续在Python里自动剔除后缀
  local GOOD_POINTS="${DAPI_BASE}/goodPoints_SpotFlow_0.1.csv"
  [[ -f "$GOOD_POINTS" ]] || { log "[WARN] skip PREP ${POS}: goodPoints missing: $GOOD_POINTS"; echo ""; return 0; }

  mkdir -p "$SHARED_PREP_DIR"
  if [[ -s "${SHARED_PREP_DIR}/manifest.json" && -s "${SHARED_PREP_DIR}/out.pkl" && -s "${SHARED_PREP_DIR}/global_spots.pkl" && -d "${SHARED_PREP_DIR}/tiles" ]]; then
    log "[SKIP] PREP exists: ${SHARED_PREP_DIR}"
    echo ""
    return 0
  fi

  throttle_if_needed

  local EXPORTS="ALL,PY=${PY},SCRIPT=${SCRIPT},BASE=${BASE},POS=${POS},Z_NUM=${Z_NUM},XY_SIZE=${XY_SIZE},GENE_CSV=${GENE_CSV},DAPI_DIR=${DAPI_DIR},GOOD_POINTS=${GOOD_POINTS},IDN=${IDN},SHARED_PREP_DIR=${SHARED_PREP_DIR},PREP_IC=${PREP_IC},PREP_ID=${PREP_ID},PREP_IPF=${PREP_IPF},PREP_ICR_XY=${PREP_ICR_XY},PREP_ICR_Z=${PREP_ICR_Z},WINDOW_SIZE=${WINDOW_SIZE},OVERLAP=${OVERLAP},DAPI_ROUND_NUM=${DAPI_ROUND_NUM},ROTATION=${ROTATION},READS_FILTER=${READS_FILTER}"

  if (( DRY_RUN == 1 )); then
    log "[DRY] sbatch PREP cm_prep_${POS}"
    echo "DRY"
    return 0
  fi

  local JOBID
  JOBID="$(sbatch_retry --job-name="cm_prep_${POS}" --export="${EXPORTS}" "${PREP_SBATCH}")"
  [[ -n "$JOBID" ]] || { log "ERROR: sbatch PREP empty jobid"; exit 10; }
  log "[JOB] PREP ${POS} -> ${JOBID}"
  echo "$JOBID"
}

# ---------- 提交一个 TAG（DRIVER 依赖 PREP） ----------
submit_one_tag() {
  local POS="$1" TAG="$2" IC="$3" ID="$4" IPF="$5" ICR_XY="$6" ICR_Z="$7" PREP_JOBID="$8"

  local POS_ROOT_WORK="${WORK_ROOT_BASE}/${POS}"
  # 构建输出的父目录到你熟悉的旧有路径中
  local POS_ROOT_OUT="${OUT_ROOT_BASE}/${POS}/seg/clustermap"
  local SHARED_PREP_DIR="${POS_ROOT_WORK}/_shared_prep"

  local WORK_DIR="${POS_ROOT_WORK}/${TAG}"
  # 这里丢掉了一长串参数后缀，只留下TAG参数名
  local OUT_DIR="${POS_ROOT_OUT}/${TAG}"

  mkdir -p "$WORK_DIR/tile_results" "$OUT_DIR"

  if is_done_strict "$OUT_DIR" "$WORK_DIR"; then
    log "[SKIP] DONE(strict) POS=${POS} TAG=${TAG} -> ${OUT_DIR}"
    return 0
  fi

  local DAPI_BASE="${BASE}/01_data/${ROUND_DAPI}/${POS}"
  local DAPI_DIR=""
  if [[ -d "$DAPI_BASE" ]]; then
      DAPI_DIR=$(find "${DAPI_BASE}" -maxdepth 2 -name "*${DAPI_SUFFIX}" | sort -V | head -n 1)
  fi
  [[ -n "$DAPI_DIR" && -f "$DAPI_DIR" ]] || { log "[WARN] skip ${POS}/${TAG}: DAPI missing in $DAPI_BASE"; return 0; }
  
  # 同步这里的路径
  local GOOD_POINTS="${DAPI_BASE}/goodPoints_SpotFlow_0.1.csv"
  [[ -f "$GOOD_POINTS" ]] || { log "[WARN] skip ${POS}/${TAG}: goodPoints missing: $GOOD_POINTS"; return 0; }

  throttle_if_needed

  local EXPORTS="ALL,PY=${PY},SCRIPT=${SCRIPT},BASE=${BASE},POS=${POS},TAG=${TAG},Z_NUM=${Z_NUM},XY_SIZE=${XY_SIZE},GENE_CSV=${GENE_CSV},DAPI_DIR=${DAPI_DIR},GOOD_POINTS=${GOOD_POINTS},IDN=${IDN},WORK_DIR=${WORK_DIR},OUT_DIR=${OUT_DIR},IC=${IC},ID=${ID},IPF=${IPF},ICR_XY=${ICR_XY},ICR_Z=${ICR_Z},ARRAY_CONCURRENCY=${ARRAY_CONCURRENCY},SHARED_PREP_DIR=${SHARED_PREP_DIR},RETRY_CPUS=${RETRY_CPUS},RETRY_MEM=${RETRY_MEM},RETRY_TIME=${RETRY_TIME},RETRY_CONCURRENCY=${RETRY_CONCURRENCY},RETRY_ROUNDS=${RETRY_ROUNDS},DAPI_ROUND_NUM=${DAPI_ROUND_NUM},EXPORT_POLYGONS=${EXPORT_POLYGONS},EXPORT_QC_PLOTS=${EXPORT_QC_PLOTS}"

  local DEP_ARGS=()
  if [[ -n "${PREP_JOBID}" && "${PREP_JOBID}" != "DRY" ]]; then
    DEP_ARGS+=(--dependency="afterok:${PREP_JOBID}")
  fi

  log "SUBMIT DRIVE  POS=${POS} TAG=${TAG}  OUT=${OUT_DIR}"
  if (( DRY_RUN == 1 )); then
    log "[DRY] sbatch DRIVER cm_drive_${POS}_${TAG}"
    return 0
  fi

  local JOBID
  JOBID="$(sbatch_retry --job-name="cm_drive_${POS}_${TAG}" "${DEP_ARGS[@]}" --export="${EXPORTS}" "${DRIVER_SBATCH}")"
  [[ -n "$JOBID" ]] || { log "ERROR: sbatch DRIVER empty jobid"; exit 11; }
  log "[JOB] DRIVE ${JOBID}"
}

# ---------- 主流程 ----------
log ""
log "[INFO] Submitting pipelines: positions(${#POS_LIST[@]}) × params(${#PARAM_LINES[@]})"
SUBMITTED=0

for POS in "${POS_LIST[@]}"; do
  log ""
  log "#################### POSITION: ${POS} ####################"

  PREP_JOBID=""
  if [[ "${SHARE_PREP_ACROSS_PARAMS}" == "1" ]]; then
    PREP_JOBID="$(submit_prep_for_position "$POS")"
  fi

  for line in "${PARAM_LINES[@]}"; do
    IFS=$'\t' read -r TAG IC ID IPF ICR_XY ICR_Z <<< "$line"
    submit_one_tag "$POS" "$TAG" "$IC" "$ID" "$IPF" "$ICR_XY" "$ICR_Z" "$PREP_JOBID"
    SUBMITTED=$((SUBMITTED+1))
  done
done

log ""
log "✅ Submitted combos = ${SUBMITTED}"
log "Track:  ${LOG_ROOT}/submitted.tsv"
log "Watch:  squeue -u \$USER | egrep 'cm_(prep|drive|tile|rescue|stitch|retry)_'"