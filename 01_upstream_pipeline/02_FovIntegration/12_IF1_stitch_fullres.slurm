#!/bin/bash
#SBATCH -J stitchdapi_IF
#SBATCH -o logs_fov_stitch/%x_%A.out
#SBATCH -e logs_fov_stitch/%x_%A.err
#SBATCH -p C64M512G
#SBATCH --qos=normal

#SBATCH --nodes=1
#SBATCH -c 60
#SBATCH --mem=240G
#SBATCH --time=24:00:00

#SBATCH --no-requeue
#SBATCH --export=ALL


start_time=$(date +%s)
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"
mkdir -p logs_fov_stitch

# activate conda environment and apply ImageJ to stitch the protein images
source /gpfs/share/home/2401111558/anaconda3/etc/profile.d/conda.sh
conda activate /gpfs/share/home/2401111558/anaconda3/envs/Fiji


echo "============= SLURM Job Info =================="
echo "Job ID:          $SLURM_JOB_ID"
echo "Job Name:        $SLURM_JOB_NAME"
echo "User:            $SLURM_JOB_USER"
echo "Submit Host:     $SLURM_SUBMIT_HOST"
echo "Submit Directory:$SLURM_SUBMIT_DIR"
echo "Node List:       $SLURM_NODELIST"
echo "Job Node:        $SLURMD_NODENAME"
echo "Number of Nodes: $SLURM_JOB_NUM_NODES"
echo "Partition:       $SLURM_JOB_PARTITION"

echo "============= Allocated CPUs Info ============="
echo "CPUs per task:   $SLURM_CPUS_PER_TASK"
echo "Allocated CPUs:  $SLURM_JOB_CPUS_PER_NODE"  # 实际分配的每节点CPU数

echo "Tasks per node:  $SLURM_NTASKS_PER_NODE"
echo "Total Tasks:     $SLURM_NTASKS"
echo "Memory per node: $SLURM_MEM_PER_NODE MB"
echo "==============================================="

default_script_dir="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration"

# 输入参数
IF_DIR=$1
GRID_X=$2
GRID_Y=$3
FIRST_INDEX=${4:-1}

SCRIPT_DIR=${5:-$default_script_dir}
STITCH_PATTERN=${6:-"Positions_from_file"} # Positions_from_file  && Snake_row_Right_down


echo "[DEBUG] Input directory: $IF_DIR"
echo "[DEBUG] Grid X: $GRID_X"
echo "[DEBUG] Grid Y: $GRID_Y"
echo "[DEBUG] First index: $FIRST_INDEX"
echo "[DEBUG] Output name: $OUTPUT_NAME"
echo "[DEBUG] Stitch type: $STITCH_PATTERN"


# 首先是 ref-DAPI 图像的 stitching
echo "+++++++++++++++++++++++++++++++++++++++++++++++++++"

# echo "Stitching step for directory: ref-DAPI"
# INPUT_DIR="${IF_DIR}/ref-DAPI"
# OUTPUT_NAME="stitched_ref-DAPI"
# export INPUT_DIR GRID_X GRID_Y FIRST_INDEX OUTPUT_NAME STITCH_PATTERN SCRIPT_DIR
# cp "$IF_DIR/TileConfiguration.txt" "$INPUT_DIR/TileConfiguration.txt"

# /gpfs/share/home/2401111558/11_softwares/Fiji.app/ImageJ-linux64 --headless --console "$SCRIPT_DIR/12_IF2_stitch.bsh"
# echo "Stitching done for directory: ref-DAPI"
# cp "$INPUT_DIR/TileConfiguration.registered.txt" "$IF_DIR/TileConfiguration.registered.txt"

# echo "+++++++++++++++++++++++++++++++++++++++++++++++++++"

echo "Stitching step for directory: ref-DAPI_MIP"
INPUT_DIR="${IF_DIR}/ref-DAPI_MIP"
OUTPUT_NAME="stitched_ref-DAPI_MIP"
STITCH_PATTERN="Positions_from_file_MIP"
export INPUT_DIR GRID_X GRID_Y FIRST_INDEX OUTPUT_NAME STITCH_PATTERN SCRIPT_DIR
cp "$IF_DIR/TileConfiguration.registered.txt" "$INPUT_DIR/TileConfiguration.registered.txt"

/gpfs/share/home/2401111558/11_softwares/Fiji.app/ImageJ-linux64 --headless --console "$SCRIPT_DIR/12_IF2_stitch.bsh"
echo "Stitching done for directory: ref-DAPI"
cp "$INPUT_DIR/TileConfiguration.registered.txt" "$IF_DIR/TileConfiguration.registered.txt"

echo "+++++++++++++++++++++++++++++++++++++++++++++++++++"



# # 检测 INPUT_DIR 下包含的文件夹数量，并进行 stitching; 
# for subDir in $(find "${IF_DIR}" -mindepth 1 -maxdepth 1 -type d | sort -V); do

#     dirName=$(basename "$subDir")
#     echo "+++++++++++++++++++++++++++++++++++++++++++++++++++"
#     echo "Processing directory: ${dirName}"


#     INPUT_DIR="${IF_DIR}/${dirName}"
#     OUTPUT_NAME="stitched_${dirName}"
#     STITCH_PATTERN="Positions_from_file_downsampled"
#     export INPUT_DIR GRID_X GRID_Y FIRST_INDEX OUTPUT_NAME STITCH_PATTERN SCRIPT_DIR
#     cp "$IF_DIR/TileConfiguration.registered.txt" "$INPUT_DIR/TileConfiguration.registered.txt"

#     /gpfs/share/home/2401111558/11_softwares/Fiji.app/ImageJ-linux64 --headless --console "$SCRIPT_DIR/12_IF2_stitch.bsh"
#     echo "Stitching done for directory: ${dirName}"
#     echo "+++++++++++++++++++++++++++++++++++++++++++++++++++"
# done

end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Elapsed time: $(($end_time - $start_time)) seconds"