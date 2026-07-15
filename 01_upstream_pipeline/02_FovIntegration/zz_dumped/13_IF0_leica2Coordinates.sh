#!/bin/bash

#SBATCH -J maf2TileConfiguration
#SBATCH -o logs_maf2TileConfiguration/%x_%A.out
#SBATCH -e logs_maf2TileConfiguration/%x_%A.err
#SBATCH -p C64M512G
#SBATCH --qos=normal

#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=12:00:00

#SBATCH --no-requeue
#SBATCH --export=ALL


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

# 创建日志目录
mkdir -p logs_maf2TileConfiguration
echo "Load conda environment"
source /gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh
conda activate ashlar

# 输入参数
INPUT_DIR=$1
MAF_FILE=$2
POSITION_OFFSET=$3
OUTPUT_DIR=$4
MATCH_STRING=$5
PIXEL_SIZE_UM=$6
IMAGE_XY=$7
OVERLAP_RATIO=$8
INVERT_Y_FLAG=$9

echo "Running job on $(hostname)"
echo "Start time: $(date +%Y-%m-%d_%H:%M:%S)"
Start_time=$(date +%s)

# SCRIPT_PATH="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration/21_vsi2Stitching_configuration.py"
SCRIPT_PATH="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration/22_leica2Stitching_configuration.py"

python -u "$SCRIPT_PATH" \
    --input_dir "$INPUT_DIR" \
    --maf_file "$MAF_FILE" \
    --position_offset "$POSITION_OFFSET" \
    --output_dir "$OUTPUT_DIR" \
    --match_string "$MATCH_STRING" \
    --pixel_size_um "$PIXEL_SIZE_UM" \
    --image_xy "$IMAGE_XY" \
    --overlap_ratio "$OVERLAP_RATIO" \
    $INVERT_Y_FLAG

echo "Done!"
echo "End time: $(date +%Y-%m-%d_%H:%M:%S)"
End_time=$(date +%s)
echo "Total time: $(expr $End_time - $Start_time) seconds"
