#!/bin/bash
#SBATCH -o logs_load_save_rawData/load_save_rawData_%A_%a.out
#SBATCH -e logs_load_save_rawData/load_save_rawData_%A_%a.err
#SBATCH -J load_save_rawData
#SBATCH -p C64M512G
#SBATCH -c 8
#SBATCH --mem=128G
#SBATCH --time=24:00:00
#SBATCH --array=1-2%10

module purge
module load matlab/2023a

mkdir -p logs_load_save_rawData
start_time=$(date +%s)


CORE_MATLAB_DIR="/gpfs/share/home/2401111558/00_scripts/02_auto_starFinder/03.starpipeline.inuse/new_StarFinder/01_upstream_pipeline/core_programs"
export CORE_MATLAB_DIR

# SCRIPT_DIR=${SLURM_SUBMIT_DIR:-$(pwd)}
# PROJECT_NAME=$(basename "$(dirname "$SCRIPT_DIR")")
# echo "脚本所在目录 (SCRIPT_DIR): ${SCRIPT_DIR}"
# echo "自动获取的项目名称 (PROJECT_NAME): ${PROJECT_NAME}"




PROJECT_ROOT="/gpfs/share/home/2401111558/01_project/07_Olympus_TEST/01_Data/01_GBM_series/80_rmContaminant_25.0815/01_rmContaminantTest"

PROJECT_NAME=$1
registration_folder=$2


echo "[INFO] PROJECT_ROOT: $PROJECT_ROOT"
echo "[INFO] PROJECT_NAME: $PROJECT_NAME"
echo "[INFO] registration_folder: $registration_folder"

OFFSET=${OFFSET:-0}
TASK_ID=$(( SLURM_ARRAY_TASK_ID + OFFSET ))
# 这个逻辑适合访问 Position ID 连续的情形；
# POSITION_NAME=$(printf "Position%03d" $TASK_ID)


# Position ID 不从001开始，且不连续
index=$((TASK_ID - 1))

DATA_DIR="${PROJECT_ROOT}/${PROJECT_NAME}/01_data/round001"
declare -a positions
readarray -t positions < <(find "${DATA_DIR}" -maxdepth 1 -type d -name "Position*" | sort -V)

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

matlab -batch "addpath(genpath('$CORE_MATLAB_DIR')); core_matlab_new('$PROJECT_NAME', 'load_save_rawData', '$POSITION_NAME', \
    2304, 30, 1, 3, 9, \
  '$PROJECT_ROOT', '01_data', '$registration_folder', 'log', 'sqrt_pieces', 4, \
  'percen_max', $pernormmax)"


end_time=$(date +%s)
echo "运行时间: $(($end_time - $start_time)) seconds"