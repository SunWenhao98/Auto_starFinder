#!/bin/bash
#SBATCH -o logs_global_readDecoding/global_readDecoding_%A_%a.out
#SBATCH -e logs_global_readDecoding/global_readDecoding_%A_%a.err
#SBATCH -J gRD
#SBATCH -p C64M512G
#SBATCH -n 1
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --array=1-25%25

module purge
module load matlab/2023a

mkdir -p logs_global_readDecoding
start_time=$(date +%s)
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"


CORE_MATLAB_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/core_programs"
export CORE_MATLAB_DIR

# SCRIPT_DIR=${SLURM_SUBMIT_DIR:-$(pwd)}
# PROJECT_NAME=$(basename "$(dirname "$SCRIPT_DIR")")
# echo "脚本所在目录 (SCRIPT_DIR): ${SCRIPT_DIR}"
# echo "自动获取的项目名称 (PROJECT_NAME): ${PROJECT_NAME}"


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




# PROJECT_ROOT="/gpfs/share/home/2401111558/01_project/07_Olympus_TEST/01_Data/01_GBM_series/81_correlationAnalysis"
PROJECT_ROOT=$1
PROJECT_NAME=$2
registration_folder=$3

image_width=${4:-2304}
image_depth=${5:-38}
ref_round=${6:-1}
channel_num=${7:-3}
round_num=${8:-6}

intensity_threshold=${9:-0.2}
spotfinding_method=${10:-'max3d'}  # SpotFlow
decoding_mode=${11:-'normal'}      # normal / seqD / seqF / seqDF
codeMap_mode=${12:-'Olympus'}      # Olympus / Leica_rj
loading_mode=${13:-'local_registration'}
IntensityThresh_perRound=${14:-0}   # 0 means no filtering based on per-round intensity
voxel_size=${15:-[1,1,1]}
decoding_rounds=${16:-11}

OFFSET=${17:-0}

echo "[INFO] PROJECT_ROOT: $PROJECT_ROOT"
echo "[INFO] PROJECT_NAME: $PROJECT_NAME"
echo "[INFO] registration_folder: $registration_folder"


# OFFSET=${OFFSET:-0}
TASK_ID=$(( SLURM_ARRAY_TASK_ID + OFFSET ))
# 这个逻辑适合访问 Position ID 连续的情形；
# POSITION_NAME=$(printf "Position%03d" $TASK_ID)


# Position ID 不从001开始，且不连续
index=$((TASK_ID - 1))

DATA_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/round001"
declare -a positions
readarray -t positions < <(find -L "${DATA_DIR}" -maxdepth 1 -type d -name "Position*" | sort -V)

if [ ${#positions[@]} -eq 0 ]; then
    echo "错误: 在目录 ${DATA_DIR} 中未找到任何 'Position*' 文件夹。" >&2
    exit 1
fi

if [[ "$index" -lt 0 || "$index" -ge ${#positions[@]} ]]; then
    echo "错误: SLURM_ARRAY_TASK_ID (${TASK_ID}) 超出有效范围 [1-${#positions[@]}]。" >&2
    exit 1
fi

POSITION_NAME=$(basename "${positions[$index]}")

echo "任务 (Task ID): ${TASK_ID}"
echo "选中的 Position 文件夹名称: ${POSITION_NAME}"
echo "------------------- start processing ..."


# 使用 case 语句根据 $decoding_mode 的值来选择分支
case "$decoding_mode" in
    seqD)
        echo "Running 'seqD' mode (single part decoding)..."
        
        # regular / double / duo mode for global reads decoding
        matlab -batch "addpath(genpath('$CORE_MATLAB_DIR')); core_matlab_new('$PROJECT_NAME', 'global_reads_decoding', '$POSITION_NAME', \
            $image_width, $image_depth, $ref_round, $channel_num, $round_num, \
            '$PROJECT_ROOT', '01_data', '$registration_folder', 'log', 'spotfinding_method', '$spotfinding_method', \
            'voxel_size', $voxel_size, 'end_bases', ['G','A'], 'barcode_mode', 'regular', 'split_loc', [], \
            'intensity_threshold', $intensity_threshold, 'IntensityThresh_perRound', $IntensityThresh_perRound, \
            'loading_mode', '$loading_mode', 'codeMap_mode', '$codeMap_mode', 'decoding_rounds', $decoding_rounds)"   
        ;;

    seqF)
        echo "Running 'seqF' mode (single part decoding)..."
        
        # regular / double / duo mode for global reads decoding
        matlab -batch "addpath(genpath('$CORE_MATLAB_DIR')); core_matlab_new('$PROJECT_NAME', 'global_reads_decoding', '$POSITION_NAME', \
            $image_width, $image_depth, $ref_round, $channel_num, $round_num, \
            '$PROJECT_ROOT', '01_data', '$registration_folder', 'log', 'spotfinding_method', '$spotfinding_method', \
            'voxel_size', $voxel_size, 'end_bases', ['A','A'], 'barcode_mode', 'regular', 'split_loc', [], \
            'intensity_threshold', $intensity_threshold, 'IntensityThresh_perRound', $IntensityThresh_perRound, \
            'loading_mode', '$loading_mode', 'codeMap_mode', '$codeMap_mode', 'decoding_rounds', $decoding_rounds)"   
        ;;

    seqF_real)
        echo "Running 'seqF' mode (single part decoding)..."
        
        # tri mode for global reads decoding
        matlab -batch "addpath(genpath('$CORE_MATLAB_DIR')); core_matlab_new('$PROJECT_NAME', 'global_reads_decoding', '$POSITION_NAME', \
            $image_width, $image_depth, $ref_round, $channel_num, $round_num, \
            '$PROJECT_ROOT', '01_data', '$registration_folder', 'log', 'spotfinding_method', '$spotfinding_method', \
            'voxel_size', $voxel_size, 'end_bases', ['A','A'], 'barcode_mode', 'regular', 'split_loc', [], \
            'intensity_threshold', $intensity_threshold, 'IntensityThresh_perRound', $IntensityThresh_perRound, \
            'loading_mode', '$loading_mode', 'codeMap_mode', '$codeMap_mode', 'decoding_rounds', $decoding_rounds)"   
        ;;

    seqDF)
        echo "Running 'seqDF' mode (double/duo decoding)..."
        
        # regular / double / duo mode for global reads decoding
        matlab -batch "addpath(genpath('$CORE_MATLAB_DIR')); core_matlab_new('$PROJECT_NAME', 'global_reads_decoding', '$POSITION_NAME', \
            $image_width, $image_depth, $ref_round, $channel_num, $round_num, \
            '$PROJECT_ROOT', '01_data', '$registration_folder', 'log', 'spotfinding_method', '$spotfinding_method', \
            'voxel_size', $voxel_size, 'end_bases', ['G','A','A','A'], 'barcode_mode', 'double', 'split_loc', 6, \
            'intensity_threshold', $intensity_threshold, 'IntensityThresh_perRound', $IntensityThresh_perRound, \
            'loading_mode', '$loading_mode', 'codeMap_mode', '$codeMap_mode', 'decoding_rounds', $decoding_rounds)"   
        ;;

    normal)
        echo "Running 'normal' mode (tri decoding)..."
        
        # tri mode for global reads decoding
        matlab -batch "addpath(genpath('$CORE_MATLAB_DIR')); core_matlab_new('$PROJECT_NAME', 'global_reads_decoding', '$POSITION_NAME', \
            $image_width, $image_depth, $ref_round, $channel_num, $round_num, \
            '$PROJECT_ROOT', '01_data', '$registration_folder', 'log', 'spotfinding_method', '$spotfinding_method', \
            'voxel_size', $voxel_size, 'end_bases', ['G','G','A','A','A'], 'barcode_mode', 'tri', 'split_loc', [6, 12], \
            'intensity_threshold', $intensity_threshold, 'IntensityThresh_perRound', $IntensityThresh_perRound, \
            'loading_mode', '$loading_mode', 'codeMap_mode', '$codeMap_mode', 'decoding_rounds', $decoding_rounds)"
        ;;

    seqD_nc)
        echo "Running 'seqD_nc' mode (single part decoding)..."
        
        # regular / double / duo mode for global reads decoding
        matlab -batch "addpath(genpath('$CORE_MATLAB_DIR')); core_matlab_new('$PROJECT_NAME', 'global_reads_decoding', '$POSITION_NAME', \
            $image_width, $image_depth, $ref_round, $channel_num, $round_num, \
            '$PROJECT_ROOT', '01_data', '$registration_folder', 'log', 'spotfinding_method', '$spotfinding_method', \
            'voxel_size', $voxel_size, 'end_bases', ['G','A'], 'barcode_mode', 'single_nc', 'split_loc', 2, \
            'intensity_threshold', $intensity_threshold, 'IntensityThresh_perRound', $IntensityThresh_perRound, \
            'loading_mode', '$loading_mode', 'codeMap_mode', '$codeMap_mode', 'decoding_rounds', $decoding_rounds)"   
        ;;

    *)
        # 错误处理：如果 $6 既不是 'normal' 也不是 'test'
        echo "Error: Unknown decoding_mode '$decoding_mode'." >&2
        echo "Valid modes are 'normal' or 'test'." >&2
        exit 1 # 以错误状态退出
        ;;
esac

end_time=$(date +%s)
echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "运行时间: $(($end_time - $start_time)) seconds"




# 2304, 30, 1, 3, 10, \
# 2304, 16, 1, 2, 1, \
# 3072, 42, 1, 3, 10, \
