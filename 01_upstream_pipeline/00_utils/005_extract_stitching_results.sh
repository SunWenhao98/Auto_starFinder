#!/bin/bash

set -euo pipefail

### 使用方法 ------------------------------------------------------------
# 功能：
#   从 rawTifDir 下指定样本、registration pattern 和 stitching round 中提取
#   stitching_results，并按以下层级完整复制到输出根目录：
#     OUTPUT_ROOT/<sample>/<stitching_round>/stitching_results
#
# 默认行为：
#   dry-run，只打印源目录与目标目录映射，不创建目录、不复制文件。
#   只有传入 --execute 才使用 cp -a 完整复制 stitching_results。
#
# 示例：
#   bash 005_extract_stitching_results.sh \
#     --sample GBM001 \
#     --sample GBM003 \
#     --registration_pattern '02_registration001*' \
#     --stitching_round IFraw_uint8 \
#     --output_root /path/to/extracted_stitching_results
#
#   bash 005_extract_stitching_results.sh \
#     --sample GBM001 \
#     --sample GBM003 \
#     --stitching_round IFraw_uint8 \
#     --output_root /path/to/extracted_stitching_results \
#     --execute
#
# 参数：
#   --sample NAME                    指定样本目录名；可重复传入。
#   --stitching_round NAME           指定 stitching round，例如 IFraw_uint8。
#   --output_root DIR                必填；提取结果的输出根目录。
#   --base_dir DIR                   rawTifDir 根目录。
#                                    默认使用项目 03_rawTifDir。
#   --registration_pattern PATTERN   registration 目录匹配模式。
#                                    默认 02_registration001*。
#   --execute                        实际执行复制；不传则 dry-run。
#   -h, --help                       打印帮助并退出。
#
# 注意：
#   1. 每个样本的 registration pattern 必须恰好匹配一个一级子目录。
#   2. 所有源路径和目标路径会先完成校验，再开始任何复制。
#   3. 目标 stitching_results 已存在时直接报错，不覆盖、不合并。
#   4. output_root 不得位于 base_dir 内，避免写入 rawTifDir。

usage() {
    sed -n '/^### 使用方法/,/^usage()/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
}

BASE_DIR="/gpfs/share/home/2401111558/labShare/2401111558/01_project/08_projGBM/01_Data/03_rawTifDir"
REGISTRATION_PATTERN="02_registration001*"
STITCHING_ROUND=""
OUTPUT_ROOT=""
EXECUTE=false
SAMPLES=()

while [ "$#" -gt 0 ]; do
    case "$1" in
        --sample)
            SAMPLES+=("${2:-}")
            shift 2
            ;;
        --stitching_round)
            STITCHING_ROUND="${2:-}"
            shift 2
            ;;
        --output_root)
            OUTPUT_ROOT="${2:-}"
            shift 2
            ;;
        --base_dir)
            BASE_DIR="${2:-}"
            shift 2
            ;;
        --registration_pattern)
            REGISTRATION_PATTERN="${2:-}"
            shift 2
            ;;
        --execute)
            EXECUTE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "错误: 未知参数: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [ "${#SAMPLES[@]}" -eq 0 ]; then
    echo "错误: 至少需要通过 --sample 指定一个样本" >&2
    exit 1
fi

if [ -z "${STITCHING_ROUND}" ]; then
    echo "错误: --stitching_round 不能为空" >&2
    exit 1
fi

if [ -z "${OUTPUT_ROOT}" ]; then
    echo "错误: --output_root 不能为空" >&2
    exit 1
fi

if [ -z "${BASE_DIR}" ] || [ -z "${REGISTRATION_PATTERN}" ]; then
    echo "错误: --base_dir 和 --registration_pattern 不能为空" >&2
    exit 1
fi

if [ ! -d "${BASE_DIR}" ]; then
    echo "错误: base_dir 不存在: ${BASE_DIR}" >&2
    exit 1
fi

if [ -e "${OUTPUT_ROOT}" ] && [ ! -d "${OUTPUT_ROOT}" ]; then
    echo "错误: output_root 已存在但不是目录: ${OUTPUT_ROOT}" >&2
    exit 1
fi

case "${STITCHING_ROUND}" in
    ""|.|..|*/*)
        echo "错误: --stitching_round 必须是单层目录名: ${STITCHING_ROUND}" >&2
        exit 1
        ;;
esac

BASE_DIR_CANON=$(realpath -m -- "${BASE_DIR}")
OUTPUT_ROOT_CANON=$(realpath -m -- "${OUTPUT_ROOT}")
case "${OUTPUT_ROOT_CANON}/" in
    "${BASE_DIR_CANON}/"*)
        echo "错误: output_root 不得等于或位于 base_dir 内: ${OUTPUT_ROOT}" >&2
        exit 1
        ;;
esac

SOURCE_DIRS=()
DESTINATION_DIRS=()
declare -A SEEN_SAMPLES=()

echo "开始检查 stitching_results 提取任务"
echo "base_dir: ${BASE_DIR}"
echo "registration_pattern: ${REGISTRATION_PATTERN}"
echo "stitching_round: ${STITCHING_ROUND}"
echo "output_root: ${OUTPUT_ROOT}"
echo "mode: $([ "${EXECUTE}" = true ] && echo execute || echo dry-run)"
echo "samples: ${SAMPLES[*]}"
echo "=================================================="

for sample_name in "${SAMPLES[@]}"; do
    case "${sample_name}" in
        ""|.|..|*/*)
            echo "错误: --sample 必须是单层目录名: ${sample_name}" >&2
            exit 1
            ;;
    esac

    if [ -n "${SEEN_SAMPLES[${sample_name}]+x}" ]; then
        echo "错误: 重复指定样本: ${sample_name}" >&2
        exit 1
    fi
    SEEN_SAMPLES["${sample_name}"]=1

    sample_dir="${BASE_DIR}/${sample_name}"
    if [ ! -d "${sample_dir}" ]; then
        echo "错误: 样本目录不存在: ${sample_dir}" >&2
        exit 1
    fi

    registration_dirs=()
    while IFS= read -r -d '' registration_dir; do
        registration_dirs+=("${registration_dir}")
    done < <(
        find "${sample_dir}" -mindepth 1 -maxdepth 1 -type d \
            -name "${REGISTRATION_PATTERN}" -print0 | sort -z
    )

    if [ "${#registration_dirs[@]}" -eq 0 ]; then
        echo "错误: ${sample_name} 未找到匹配的 registration: ${REGISTRATION_PATTERN}" >&2
        exit 1
    fi

    if [ "${#registration_dirs[@]}" -ne 1 ]; then
        echo "错误: ${sample_name} 匹配到 ${#registration_dirs[@]} 个 registration，要求恰好一个:" >&2
        printf '  - %s\n' "${registration_dirs[@]}" >&2
        exit 1
    fi

    source_dir="${registration_dirs[0]}/${STITCHING_ROUND}/stitching_results"
    destination_dir="${OUTPUT_ROOT}/${sample_name}/${STITCHING_ROUND}/stitching_results"

    if [ ! -d "${source_dir}" ]; then
        echo "错误: 源 stitching_results 不存在: ${source_dir}" >&2
        exit 1
    fi

    if [ -e "${destination_dir}" ]; then
        echo "错误: 目标已存在，拒绝覆盖或合并: ${destination_dir}" >&2
        exit 1
    fi

    SOURCE_DIRS+=("${source_dir}")
    DESTINATION_DIRS+=("${destination_dir}")
done

echo "所有路径校验通过，共 ${#SOURCE_DIRS[@]} 个样本。"

for index in "${!SOURCE_DIRS[@]}"; do
    source_dir="${SOURCE_DIRS[${index}]}"
    destination_dir="${DESTINATION_DIRS[${index}]}"

    if [ "${EXECUTE}" = true ]; then
        mkdir -p "$(dirname "${destination_dir}")"
        cp -a -- "${source_dir}" "${destination_dir}"
        echo "[COPY] ${source_dir} -> ${destination_dir}"
    else
        echo "[DRY-RUN] ${source_dir} -> ${destination_dir}"
    fi
done

echo "=================================================="
if [ "${EXECUTE}" = true ]; then
    echo "实际复制样本数: ${#SOURCE_DIRS[@]}"
    echo "STATUS: SUCCESS"
else
    echo "dry-run 完成；确认无误后加 --execute 执行复制。"
fi
