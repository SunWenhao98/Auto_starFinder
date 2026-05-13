#!/bin/bash

#SBATCH -J comseg_pipeline
#SBATCH -o logs_comseg/comseg_%A_%a.out
#SBATCH -e logs_comseg/comseg_%A_%a.err

#SBATCH -p C64M512G
#SBATCH -n 1
#SBATCH -c 16
#SBATCH --mem=128G

#SBATCH --time=24:00:00
#SBATCH --array=1-8%8

echo "Loading Environment..."
# module purge
source /gpfs/share/home/2300012257/anaconda3/etc/profile.d/conda.sh
conda activate ComSeg

mkdir -p logs_comseg
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"

echo "============= SLURM Job Info =================="
echo "Job ID:          $SLURM_JOB_ID"
echo "Job Name:        $SLURM_JOB_NAME"
echo "Node List:       $SLURM_NODELIST"
echo "Job Node:        $SLURMD_NODENAME"
echo "Allocated CPUs:  $SLURM_JOB_CPUS_PER_NODE"
echo "Memory per node: $SLURM_MEM_PER_NODE MB"

# ================= Configuration =================
SCRIPT_ROOT="/gpfs/share/home/2300012257/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline"
PYTHON_SCRIPT="${SCRIPT_ROOT}/03_maskGeneration/run_comseg.py"

# ================= Input Parameters =================
PROJECT_ROOT=$1
PROJECT_NAME=$2
registration_folder=$3
ref_round=${4:-1}
OFFSET=${5:-0}

# ComSeg configuration parameters
MEAN_CELL_DIAMETER=${6:-15}    # in micrometer
MAX_CELL_RADIUS=${7:-15}       # in micrometer (for final association)
PIXEL_SCALE_XY=${8:-0.108}     # um per pixel
PIXEL_SCALE_Z=${9:-0.27}       # um per z-step
MIN_RNA=${10:-30}              # Minimum RNAs per cell
LEIDEN_RESOLUTION=${11:-0.5}   # Leiden clustering resolution
N_PCS=${12:-10}                # Number of PCs for dimensionality reduction
N_NEIGHBORS=${13:-40}          # Graph construction neighbors
CLASSIFY_NEIGHBORS=${14:-15}   # Neighbors for nuclei classification
MERGE_CORR=${15:-0.8}          # Correlation threshold to merge similar clusters
COMMUNITY_MIN_SIZE=${16:-10}    # Minimum size of RNA community

DAPI_SUFFIX="ch03.tif" 
SPOT_CSV_NAME="goodPoints_SpotFlow_0.1.csv"

# ================= Task Setup =================
TASK_ID=$(( SLURM_ARRAY_TASK_ID + OFFSET ))
index=$(( TASK_ID - 1 ))

reference_dir="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/round00${ref_round}"

# 1. Locate DAPI files (Used as reference for positioning/QC)
declare -a dapi_files
readarray -t dapi_files < <(find "${reference_dir}" -maxdepth 2 -name "*${DAPI_SUFFIX}" | sort -V)

if [ "$index" -ge "${#dapi_files[@]}" ]; then
    echo "Error: Task ID $index exceeds number of files (${#dapi_files[@]}). Exiting."
    exit 1
fi

dapi_file="${dapi_files[$index]}"
POSITION_NAME=$(basename "$(dirname "${dapi_file}")")

# 2. Locate Spots CSV
transcripts_file_raw="$(dirname "${dapi_file}")/${SPOT_CSV_NAME}"
if [ ! -f "$transcripts_file_raw" ]; then
    echo "Error: Transcripts CSV not found at: ${transcripts_file_raw}"
    exit 1
fi

# 3. Locate Prior Mask (Cellpose Output)
mask_dir="${PROJECT_ROOT}/${PROJECT_NAME}/${registration_folder}/${POSITION_NAME}/seg/dapi_cellpose"
mask_file="${mask_dir}/${POSITION_NAME}_dapi2d_cellpose.tif"
if [ ! -f "$mask_file" ]; then
    echo "Error: Prior mask file not found at: ${mask_file}"
    exit 1
fi

output_dir="${PROJECT_ROOT}/${PROJECT_NAME}/${registration_folder}/${POSITION_NAME}/seg/comseg"
interm_dir="${PROJECT_ROOT}/${PROJECT_NAME}/${registration_folder}/${POSITION_NAME}/interm/comseg_prep"
mkdir -p "${output_dir}"
mkdir -p "${interm_dir}"

transcripts_file_clean="${interm_dir}/${SPOT_CSV_NAME%.*}_clean_genes.csv"

echo ">>> Cleaning gene names (removing _rbRNA/_ntRNA)..."
sed -e 's/_rbRNA//g' -e 's/_ntRNA//g' "${transcripts_file_raw}" > "${transcripts_file_clean}"

if [ ! -f "$transcripts_file_clean" ]; then
    echo "Error: Failed to create cleaned transcripts file."
    exit 1
fi

echo "------------------------------------------------"
echo "Processing Position: ${POSITION_NAME}"
echo "DAPI File:           ${dapi_file}"
echo "Raw CSV:             ${transcripts_file_raw}"
echo "Cleaned CSV:         ${transcripts_file_clean}"
echo "Prior Mask:          ${mask_file}"
echo "Output Directory:    ${output_dir}"
echo "Interm Directory:    ${interm_dir}"
echo "Params:              Dia=${MEAN_CELL_DIAMETER}um, Rad=${MAX_CELL_RADIUS}um, Scale=${PIXEL_SCALE_XY}, MinRNA=${MIN_RNA}, Res=${LEIDEN_RESOLUTION}"
echo "------------------------------------------------"

# ================= EXECUTION =================

if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Critical Error: Python script not found at ${PYTHON_SCRIPT}"
    exit 1
fi

echo ">>> Running ComSeg Pipeline..."

time python -u "${PYTHON_SCRIPT}" \
    --position_name "${POSITION_NAME}" \
    --dapi_path "${dapi_file}" \
    --spots_path "${transcripts_file_clean}" \
    --mask_path "${mask_file}" \
    --output_dir "${output_dir}" \
    --temp_dir "${interm_dir}" \
    --mean_cell_diameter "${MEAN_CELL_DIAMETER}" \
    --max_cell_radius "${MAX_CELL_RADIUS}" \
    --n_neighbors "${N_NEIGHBORS}" \
    --scale_xy "${PIXEL_SCALE_XY}" \
    --scale_z "${PIXEL_SCALE_Z}" \
    --min_rna "${MIN_RNA}" \
    --leiden_resolution "${LEIDEN_RESOLUTION}" \
    --n_pcs "${N_PCS}" \
    --classify_neighbors "${CLASSIFY_NEIGHBORS}" \
    --merge_corr "${MERGE_CORR}" \
    --commu_min "${COMMUNITY_MIN_SIZE}"

if [ -f "${output_dir}/cell_center.csv" ]; then
    echo ">>> ComSeg Finished Successfully!"
    echo "Results generated in: ${output_dir}"

else
    echo "Error: ComSeg failed to generate 'cell_center.csv'. Check logs above."
    exit 1
fi