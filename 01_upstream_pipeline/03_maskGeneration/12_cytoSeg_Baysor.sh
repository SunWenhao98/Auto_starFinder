#!/bin/bash

#SBATCH -J baysor_cyto_seg
#SBATCH -o logs_baysor/baysor_%A_%a.out
#SBATCH -e logs_baysor/baysor_%A_%a.err

#SBATCH -p C64M512G
#SBATCH -n 1
#SBATCH -c 16
#SBATCH --mem=128G

#SBATCH --time=24:00:00
#SBATCH --array=1-8%8

echo "Loading Environment..."
# module purge
source /gpfs/share/home/2300012257/anaconda3/etc/profile.d/conda.sh
conda activate cellpose

mkdir -p logs_baysor
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"

echo "============= SLURM Job Info =================="
echo "Job ID:          $SLURM_JOB_ID"
echo "Job Name:        $SLURM_JOB_NAME"
echo "Node List:       $SLURM_NODELIST"
echo "Memory per node: $SLURM_MEM_PER_NODE MB"

# ================= Config =================
SCRIPT_ROOT="/gpfs/share/home/2300012257/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline"
PREP_SCRIPT="${SCRIPT_ROOT}/03_maskGeneration/create_Baysor_input.py"
QC_SCRIPT="${SCRIPT_ROOT}/03_maskGeneration/vis_baysor_qc.py"
BAYSOR_BIN="/gpfs/share/home/2300012257/tools/bin/baysor/bin/baysor"

# ================= Input Parameters =================
PROJECT_ROOT=$1
PROJECT_NAME=$2
registration_folder=$3
ref_round=${4:-1}
OFFSET=${5:-0}

DIAMETER=${6:-15}
XY_SCALE=${7:-0.108}
Z_SCALE=${8:-0.27}
MIN_MOLECULES_PER_CELL=${9:-30}
PRIOR_CONF=${10:-1.0}
CLUSTER_NUM=${11:-10}
POLYGON=${12:-false}
COUNT_MATRIX_FORMAT=${13:-tsv}

# ================= Task Setup =================
TASK_ID=$(( SLURM_ARRAY_TASK_ID + OFFSET ))
index=$(( TASK_ID - 1 ))
reference_dir="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/round00${ref_round}"
TARGET_CSV_NAME="goodPoints_SpotFlow_0.1.csv"
DAPI_SUFFIX="ch03.tif"

# 1. Locate Spots CSV (Raw Data)
declare -a transcripts_files
readarray -t transcripts_files < <(find "${reference_dir}" -maxdepth 2 -name "${TARGET_CSV_NAME}" | sort -V)
if [ "$index" -ge "${#transcripts_files[@]}" ]; then
    echo "Error: Task ID $index exceeds number of files. Exiting."
    exit 1
fi

transcripts_file_raw="${transcripts_files[$index]}"
POSITION_NAME=$(basename "$(dirname "${transcripts_file_raw}")")

dapi_file="$(dirname "${transcripts_file_raw}")/$(basename "${transcripts_file_raw}" | sed "s/${TARGET_CSV_NAME}//")*${DAPI_SUFFIX}"
# Expand wildcard
dapi_file=$(ls ${dapi_file} 2>/dev/null | head -n 1)

if [ -z "$dapi_file" ]; then
    # Fallback search if naming convention differs
    dapi_file=$(find "$(dirname "${transcripts_file_raw}")" -name "*${DAPI_SUFFIX}" | head -n 1)
fi

echo "Found DAPI: ${dapi_file}"

dapi_dir="${PROJECT_ROOT}/${PROJECT_NAME}/${registration_folder}/${POSITION_NAME}/seg/dapi_cellpose"
output_dir="${PROJECT_ROOT}/${PROJECT_NAME}/${registration_folder}/${POSITION_NAME}/seg/baysor"
BAYSOR_INPUT_FILE="${output_dir}/${POSITION_NAME}_baysor_input.csv"

mkdir -p "${output_dir}"

transcripts_file_clean="${output_dir}/${TARGET_CSV_NAME%.*}_clean_genes.csv"

echo ">>> Cleaning gene names (removing _rbRNA/_ntRNA)..."
sed -e 's/_rbRNA//g' -e 's/_ntRNA//g' "${transcripts_file_raw}" > "${transcripts_file_clean}"

if [ ! -f "$transcripts_file_clean" ]; then
    echo "Error: Failed to create cleaned transcripts file."
    exit 1
fi

echo "--------------------------------------------------------"
echo "Processing Position: ${POSITION_NAME}"
echo "Raw CSV:             ${transcripts_file_raw}"
echo "Cleaned CSV:         ${transcripts_file_clean}"
echo "Dapi Mask Dir:       ${dapi_dir}"
echo "Output Dir:          ${output_dir}"

# ================= EXECUTION =================
npy_file="${dapi_dir}/${POSITION_NAME}_dapi2d_cellpose.npy"

if [ ! -f "$npy_file" ]; then
    echo "Error: Cellpose nuclear mask not found at ${npy_file}"
    exit 1
fi

echo ">>> Creating Baysor Input CSV..."
python "${PREP_SCRIPT}" \
    --starmap_coords "${transcripts_file_clean}" \
    --cellpose_mask "${npy_file}" \
    --output_csv "${BAYSOR_INPUT_FILE}" \
    --xy_scale ${XY_SCALE} \
    --z_scale ${Z_SCALE}

if [ ! -f "$BAYSOR_INPUT_FILE" ]; then
    echo "Error: Baysor input creation failed."
    exit 1
fi

# 2. Run Baysor
echo "--------------------------------------------------------"
echo ">>> Running Baysor Segmentation..."

if [ ! -x "$BAYSOR_BIN" ]; then
    chmod +x "$BAYSOR_BIN"
fi

time $BAYSOR_BIN run \
    "${BAYSOR_INPUT_FILE}" \
    :cell_id \
    --min-molecules-per-cell ${MIN_MOLECULES_PER_CELL} \
    --scale ${DIAMETER} \
    --prior-segmentation-confidence ${PRIOR_CONF} \
    --n-clusters ${CLUSTER_NUM} \
    --output "${output_dir}" \
    --polygon-format ${POLYGON} \
    --count-matrix-format "${COUNT_MATRIX_FORMAT}"

# 3. QC Visualization
if [ -f "${output_dir}/segmentation.csv" ]; then
    echo ">>> Baysor Finished. Generating QC Plots..."
    
    python "${QC_SCRIPT}" \
        --dapi_path "${dapi_file}" \
        --mask_path "${npy_file}" \
        --baysor_csv "${output_dir}/segmentation.csv" \
        --baysor_stats "${output_dir}/segmentation_cell_stats.csv" \
        --output_dir "${output_dir}" \
        --xy_scale ${XY_SCALE}

    echo ">>> All Steps Complete!"

else
    echo "Error: Baysor failed to generate output."
    exit 1
fi