#!/bin/bash

set -euo pipefail

### 使用方法 ------------------------------------------------------------
# 功能：
#   通用 flat copy 工具：扫描 BASE_DIR 下匹配 PATTERN 的一级子目录，
#   将 SOURCE_DIR 中指定的一个或多个文件/目录复制到每个目标目录的 DEST_SUBDIR 下。
#
# 适用场景：
#   - 复制 CodeBook：genes_tri.csv -> 01_data/genes.csv
#   - 复制配置文件：config_level1.ini、config_level2.ini -> scripts/
#   - 复制流程脚本：01_global_registration.sh 等 -> scripts/
#   - 复制固定源数据目录：Position218 -> 02_registration*/
#
# 示例：
#   bash prepare_files.sh \
#     --base-dir /path/to/rawTifDir \
#     --source-dir /path/to/CodeBook \
#     --pattern 'GBM*' \
#     --dest-subdir 01_data \
#     --item genes_tri.csv:genes.csv
#
#   bash prepare_files.sh \
#     --base-dir /path/to/submit_root \
#     --source-dir /path/to/source_scripts \
#     --pattern 'submit*' \
#     --dest-subdir scripts \
#     --item config_level1.ini \
#     --item config_level2.ini
#
#   bash prepare_files.sh \
#     --base-dir /path/to/registration_root \
#     --source-dir /path/to/spotiflow_t0.1 \
#     --pattern '02_registration*' \
#     --dest-subdir . \
#     --copy-mode dir \
#     --item Position218
#
# 参数：
#   -b, --base-dir DIR       待扫描的基础目录。
#   -s, --source-dir DIR     待复制文件/目录所在目录。
#   -p, --pattern PATTERN    find -name 使用的目标目录匹配模式，默认 submit*。
#   -d, --dest-subdir DIR    每个匹配目录内的目标子目录，默认 scripts；传 . 表示匹配目录本身。
#   -i, --item SPEC          待复制项，可重复传入多个。
#                            SPEC 支持 source_name 或 source_name:dest_name。
#   -m, --copy-mode MODE     复制类型：file、dir、auto，默认 auto。
#   -h, --help               打印帮助并退出。
#
# 注意：
#   1. 这是 flat copy：源路径始终是 SOURCE_DIR/source_name。
#   2. 如需 SOURCE_DIR/<目标目录名>/file 的映射复制，请使用 prepare_mapping_files.sh。
#   3. 目标已存在时 cp 会覆盖同名文件；目录复制遵循 cp -r 的默认行为。

usage() {
    sed -n '/^### 使用方法/,/^usage()/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
}

BASE_DIR=""
SOURCE_DIR=""
DIR_PATTERN="submit*"
DEST_SUBDIR="scripts"
COPY_MODE="auto"
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
        -m|--copy-mode)
            COPY_MODE="${2:-}"
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
    echo "错误: 至少需要通过 --item 指定一个待复制项" >&2
    exit 1
fi

case "${COPY_MODE}" in
    file|dir|auto) ;;
    *)
        echo "错误: --copy-mode 只能是 file、dir 或 auto: ${COPY_MODE}" >&2
        exit 1
        ;;
esac

if [ ! -d "${BASE_DIR}" ]; then
    echo "错误: 基础目录不存在: ${BASE_DIR}" >&2
    exit 1
fi

if [ ! -d "${SOURCE_DIR}" ]; then
    echo "错误: 源目录不存在: ${SOURCE_DIR}" >&2
    exit 1
fi

copy_one_item() {
    local source_path="$1"
    local dest_path="$2"

    case "${COPY_MODE}" in
        file)
            if [ ! -f "${source_path}" ]; then
                echo "     - 警告: 源文件未找到，跳过: ${source_path}"
                return 1
            fi
            cp "${source_path}" "${dest_path}"
            ;;
        dir)
            if [ ! -d "${source_path}" ]; then
                echo "     - 警告: 源目录未找到，跳过: ${source_path}"
                return 1
            fi
            cp -r "${source_path}" "${dest_path}"
            ;;
        auto)
            if [ -f "${source_path}" ]; then
                cp "${source_path}" "${dest_path}"
            elif [ -d "${source_path}" ]; then
                cp -r "${source_path}" "${dest_path}"
            else
                echo "     - 警告: 源文件/目录未找到，跳过: ${source_path}"
                return 1
            fi
            ;;
    esac

    return 0
}

echo "开始扫描并处理目录: ${BASE_DIR}"
echo "匹配模式: ${DIR_PATTERN}"
echo "源目录: ${SOURCE_DIR}"
echo "目标子目录: ${DEST_SUBDIR}"
echo "复制模式: ${COPY_MODE}"
echo "待复制项:"
for ITEM_SPEC in "${ITEMS_TO_COPY[@]}"; do
    echo "  - ${ITEM_SPEC}"
done
echo "=================================================="

count=0
while IFS= read -r -d '' TARGET_DIR; do
    echo "正在处理: ${TARGET_DIR}"

    if [ "${DEST_SUBDIR}" = "." ]; then
        DEST_DIR="${TARGET_DIR}"
    else
        DEST_DIR="${TARGET_DIR}/${DEST_SUBDIR}"
    fi

    echo "  -> 正在创建目录: ${DEST_DIR}"
    mkdir -p "${DEST_DIR}"

    echo "  -> 正在拷贝文件/目录..."
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

        SOURCE_PATH="${SOURCE_DIR}/${SOURCE_NAME}"
        DEST_PATH="${DEST_DIR}/${DEST_NAME}"

        if copy_one_item "${SOURCE_PATH}" "${DEST_PATH}"; then
            echo "     - 已拷贝: ${SOURCE_NAME} -> ${DEST_PATH}"
            count=$((count + 1))
        fi
    done

    echo "  -> 处理完成."
    echo "--------------------------------------------------"
done < <(find "${BASE_DIR}" -maxdepth 1 -type d -name "${DIR_PATTERN}" -print0)

echo "总计拷贝次数：${count}"
echo "所有操作已完成。"
