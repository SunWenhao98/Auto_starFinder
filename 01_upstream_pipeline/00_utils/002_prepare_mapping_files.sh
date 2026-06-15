#!/bin/bash

set -euo pipefail

### 使用方法 ------------------------------------------------------------
# 功能：
#   按目标目录 basename 映射复制文件。扫描 BASE_DIR 下匹配 PATTERN 的一级子目录，
#   对每个目标目录 TARGET_DIR，读取 SOURCE_DIR/$(basename TARGET_DIR)/<item>，
#   并复制到 TARGET_DIR/DEST_SUBDIR 下。
#
# 适用场景：
#   - prepare_spotiflow.sh 这类 Position 结果复制：
#     BASE_DIR/Position001/ <- SOURCE_DIR/Position001/goodPoints_max3d_0.2_tri.csv
#
# 示例：
#   bash prepare_position_files.sh \
#     --source-dir /path/to/source_registration \
#     --base-dir /path/to/target_registration \
#     --pattern 'Position*' \
#     --item goodPoints_max3d_0.2_tri.csv
#
#   bash prepare_position_files.sh \
#     --source-dir /path/to/source_registration \
#     --base-dir /path/to/target_registration \
#     --pattern 'Position*' \
#     --dest-subdir spotiflow \
#     --item goodPoints_max3d_0.2_tri.csv:goodPoints.csv \
#     --item qc_summary.tsv
#
# 参数：
#   -b, --base-dir DIR       待扫描的目标基础目录。
#   -s, --source-dir DIR     源基础目录，内部应含有与目标 basename 同名的子目录。
#   -p, --pattern PATTERN    find -name 使用的目标目录匹配模式，默认 Position*。
#   -d, --dest-subdir DIR    每个匹配目录内的目标子目录，默认 .。
#   -i, --item SPEC          待复制文件，可重复传入多个。
#                            SPEC 支持 source_name 或 source_name:dest_name。
#   -h, --help               打印帮助并退出。
#
# 注意：
#   1. 本脚本只复制文件，不复制目录。
#   2. 这是 basename-mapping copy，不适合普通 flat copy；普通复制请用 prepare_files.sh。
#   3. 目标已存在时 cp 会覆盖同名文件。

usage() {
    sed -n '/^### 使用方法/,/^usage()/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
}

BASE_DIR=""
SOURCE_DIR=""
DIR_PATTERN="Position*"
DEST_SUBDIR="."
ITEMS_TO_COPY=()

add_item() {
    local item_spec="$1"
    if [ -z "${item_spec}" ]; then
        echo "错误: --item 不能传入空值" >&2
        exit 1
    fi
    ITEMS_TO_COPY+=("${item_spec}")
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        -b|--base-dir)
            BASE_DIR="${2:-}"
            shift 2
            ;;
        -s|--source-dir)
            SOURCE_DIR="${2:-}"
            shift 2
            ;;
        -p|--pattern)
            DIR_PATTERN="${2:-}"
            shift 2
            ;;
        -d|--dest-subdir)
            DEST_SUBDIR="${2:-}"
            shift 2
            ;;
        -i|--item)
            add_item "${2:-}"
            shift 2
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

if [ -z "${BASE_DIR}" ] || [ -z "${SOURCE_DIR}" ] || [ -z "${DIR_PATTERN}" ] || [ -z "${DEST_SUBDIR}" ]; then
    echo "错误: --base-dir、--source-dir、--pattern、--dest-subdir 均不能为空" >&2
    exit 1
fi

if [ "${#ITEMS_TO_COPY[@]}" -eq 0 ]; then
    echo "错误: 至少需要通过 --item 指定一个待复制文件" >&2
    exit 1
fi

if [ ! -d "${BASE_DIR}" ]; then
    echo "错误: 目标基础目录不存在: ${BASE_DIR}" >&2
    exit 1
fi

if [ ! -d "${SOURCE_DIR}" ]; then
    echo "错误: 源基础目录不存在: ${SOURCE_DIR}" >&2
    exit 1
fi

echo "开始扫描并处理目录: ${BASE_DIR}"
echo "匹配模式: ${DIR_PATTERN}"
echo "源基础目录: ${SOURCE_DIR}"
echo "目标子目录: ${DEST_SUBDIR}"
echo "待复制文件:"
for ITEM_SPEC in "${ITEMS_TO_COPY[@]}"; do
    echo "  - ${ITEM_SPEC}"
done
echo "=================================================="

count=0
while IFS= read -r -d '' TARGET_DIR; do
    target_name=$(basename "${TARGET_DIR}")
    echo "正在处理: ${TARGET_DIR}"
    echo "  -> 映射名称: ${target_name}"

    if [ "${DEST_SUBDIR}" = "." ]; then
        DEST_DIR="${TARGET_DIR}"
    else
        DEST_DIR="${TARGET_DIR}/${DEST_SUBDIR}"
    fi

    mkdir -p "${DEST_DIR}"
    echo "  -> 正在拷贝文件..."

    for ITEM_SPEC in "${ITEMS_TO_COPY[@]}"; do
        SOURCE_NAME="${ITEM_SPEC%%:*}"
        DEST_NAME="${ITEM_SPEC#*:}"

        if [ "${SOURCE_NAME}" = "${ITEM_SPEC}" ]; then
            DEST_NAME="${SOURCE_NAME}"
        fi

        if [ -z "${SOURCE_NAME}" ] || [ -z "${DEST_NAME}" ]; then
            echo "     - 警告: 复制项规格无效，跳过: ${ITEM_SPEC}"
            continue
        fi

        SOURCE_FILE="${SOURCE_DIR}/${target_name}/${SOURCE_NAME}"
        DEST_FILE="${DEST_DIR}/${DEST_NAME}"

        if [ -f "${SOURCE_FILE}" ]; then
            cp "${SOURCE_FILE}" "${DEST_FILE}"
            echo "     - 已拷贝: ${target_name}/${SOURCE_NAME} -> ${DEST_FILE}"
            count=$((count + 1))
        else
            echo "     - 警告: 源文件未找到，跳过: ${SOURCE_FILE}"
        fi
    done

    echo "  -> 处理完成."
    echo "--------------------------------------------------"
done < <(find "${BASE_DIR}" -maxdepth 1 -type d -name "${DIR_PATTERN}" -print0)

echo "总计拷贝文件数：${count}"
echo "所有操作已完成。"
