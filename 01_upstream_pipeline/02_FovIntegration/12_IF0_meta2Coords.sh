#!/bin/bash

#SBATCH -J meta2CoordsTile
#SBATCH -o logs_meta2CoordsTile/%x_%A.out  
#SBATCH -e logs_meta2CoordsTile/%x_%A.err


#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=24:00:00

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
mkdir -p logs_meta2CoordsTile
echo "Load conda environment"
source /gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh
conda activate bioformats_env

# 输入参数
INPUT_DIR=$1
OUTPUT_DIR=$2
MATCH_STRING=$3

pixel_size_um=$4
image_xy=$5
overlap_ratio=$6
INVERT_Y_FLAG=${7:-""}      # --invert_y

maf_file=$8
position_offset=$9
microscope=${10:-"Leica"}

echo "Input directory: $INPUT_DIR"
echo "Output directory: $OUTPUT_DIR"
echo "Match string: $MATCH_STRING"
echo "Pixel size (um): $pixel_size_um"
echo "Image XY: $image_xy"
echo "Overlap ratio: $overlap_ratio"
echo "Invert Y flag: $INVERT_Y_FLAG"
echo "MAF file: $maf_file"
echo "Position offset: $position_offset"
echo "Microscope: $microscope"


# === 执行你的程序 ===
echo "Running job on $(hostname)"
echo "Start time: $(date +%Y-%m-%d_%H:%M:%S)"
Start_time=$(date +%s)

# SCRIPT_PATH="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration/21_vsi2Stitching_configuration.py"
# SCRIPT_PATH="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration/21_vsi2Stitching_configuration_v2.py"

# python -u "$SCRIPT_PATH" \
#     --input_dir $INPUT_DIR \
#     --output_dir $OUTPUT_DIR \
#     --match_string $MATCH_STRING

case "$microscope" in
    "Leica")
        echo "Running Leica stitching configuration..."
        python -u "/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration/22_leica2Stitching_configuration.py" \
            --input_dir "$INPUT_DIR" \
            --output_dir "$OUTPUT_DIR" \
            --match_string "$MATCH_STRING" \
            --pixel_size_um $pixel_size_um \
            --image_xy $image_xy \
            --overlap_ratio $overlap_ratio \
            --maf_file "$maf_file" \
            --position_offset $position_offset \
            $INVERT_Y_FLAG

        ;;
    "Olympus")
        echo "Running Olympus stitching configuration..."
        python -u "/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/02_FovIntegration/21_vsi2Stitching_configuration_v2.py" \
            --input_dir "$INPUT_DIR" \
            --output_dir "$OUTPUT_DIR" \
            --match_string "$MATCH_STRING" \
            --pixel_size_um $pixel_size_um \
            --image_xy $image_xy \
            --overlap_ratio $overlap_ratio \
            $INVERT_Y_FLAG
        ;;
    *)
        echo "Error: Unknown microscope type '$microscope'. Please specify 'Leica' or 'Olympus'."
        exit 1
        ;;
esac

echo "Done!"
echo "End time: $(date +%Y-%m-%d_%H:%M:%S)"
End_time=$(date +%s)
echo "Total time: $(expr $End_time - $Start_time) seconds"