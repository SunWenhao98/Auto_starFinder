#!/bin/bash

#SBATCH -J segResultsStitch
#SBATCH -o logs_segResultsStitch/segResultsStitch_%A_%a.out
#SBATCH -e logs_segResultsStitch/segResultsStitch_%A_%a.err

#SBATCH -p C64M512G
#SBATCH -n 1
#SBATCH -c 60
##SBATCH --mem=480G

#SBATCH --time=12:00:00


echo "Loading Environment..."
# module purge
source /gpfs/share/home/${USER}/anaconda3/etc/profile.d/conda.sh
conda activate data_analysis_env

mkdir -p logs_segResultsStitch
start_time=$(date +%s)
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"


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

echo "============= CPU/Memory Allocation ============="
echo "CPUs per task:   $SLURM_CPUS_PER_TASK"
echo "Allocated CPUs:  $SLURM_JOB_CPUS_PER_NODE"

echo "Tasks per node:  $SLURM_NTASKS_PER_NODE"
echo "Total Tasks:     $SLURM_NTASKS"
echo "Memory per node: $SLURM_MEM_PER_NODE MB"


echo "Stitching segmented results..."
# scripts for stitching tiles
# PYTHON_SCRIPT="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/04_CellReadsIntegration/segResultsStitch_v1_20260112.py"


INPUT_XY=$1
INPUT_DIR=$2
OUTPUT_DIR=$3
SEG_METHOD=$4
IF_DIRNAME=$5
suffix=$6
PYTHON_SCRIPT=$7

# notes for suffix: 

echo "[INFO] input_xy: $INPUT_XY"
echo "[INFO] input_dir: $INPUT_DIR"
echo "[INFO] output_dir: $OUTPUT_DIR"
echo "[INFO] seg_method: $SEG_METHOD"
echo "[INFO] if_dirname: $IF_DIRNAME"
echo "[INFO] python_script: $PYTHON_SCRIPT"


# 提取脚本的文件名（去掉前面的目录路径），方便准确匹配
SCRIPT_NAME=$(basename "$PYTHON_SCRIPT")

# 使用 case 语句进行条件分支判断
case "$SCRIPT_NAME" in
    "segResultsStitch_v1_20260112.py")
        echo "Running: $SCRIPT_NAME (Full version with all parameters)"
        python -u "$PYTHON_SCRIPT" \
            --input_xy "$INPUT_XY" \
            --input_dir "$INPUT_DIR" \
            --output_dir "$OUTPUT_DIR" \
            --seg_method "$SEG_METHOD" \
            --IF_dirname "$IF_DIRNAME" \
            --suffix "$suffix"
        ;;
        
    "segResultsStitch_v2_simple.py")
        echo "Running: $SCRIPT_NAME (Simple version with fewer parameters)"
        python -u "$PYTHON_SCRIPT" \
            --input_dir "$INPUT_DIR" \
            --output_dir "$OUTPUT_DIR" \
            --seg_method "$SEG_METHOD" \
            --suffix "$suffix"
        ;;
        
    # 后续如果有 v3、v4 版本，直接在这里继续添加即可
    # "segResultsStitch_v3.py")
    #     python -u "$PYTHON_SCRIPT" --your_new_args ...
    #     ;;

    *)
        # 默认匹配（相当于 default），用来捕捉意料之外的脚本输入
        echo "Error: Unknown python script '$SCRIPT_NAME'"
        echo "Please configure the parameters for this script in the case statement."
        exit 1
        ;;
esac


end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "运行时间: $(($end_time - $start_time)) seconds"

