#!/bin/bash

set -euo pipefail

### 使用方法 ------------------------------------------------------------
# 功能：
#   清理匹配目录下的 registration log 目录。默认 dry-run，只打印将要删除的目录；
#   只有显式传入 --execute 才会执行 rm -rf。
#
# 示例：
#   bash cleanup_registration_logs.sh \
#     --base-dir /path/to/submit_batch \
#     --pattern 'submit*'
#
#   bash cleanup_registration_logs.sh \
#     --base-dir /path/to/submit_batch \
#     --pattern 'submit*' \
#     --relative-log-dir scripts/logs_local_registration \
#     --execute
#
# 参数：
#   -b, --base-dir DIR          待扫描的基础目录。
#   -p, --pattern PATTERN       find -name 使用的目标目录匹配模式，默认 submit*。
#   -r, --relative-log-dir DIR  每个匹配目录下要清理的相对日志目录，默认 scripts/logs_local_registration。
#   --execute                   真正删除；不传时只 dry-run。
#   -h, --help                  打印帮助并退出。
#
# 注意：
#   1. 本脚本包含删除操作，默认不会删除任何文件。
#   2. 使用 --execute 前请先运行 dry-run 确认目标目录列表。
#   3. 原 cleanup_logs.sh 保持不变；本脚本是命名更明确、参数化的替代工具。

usage() {
    sed -n '/^### 使用方法/,/^usage()/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
}

BASE_DIR=""
DIR_PATTERN="submit*"
RELATIVE_LOG_DIR="scripts/logs_local_registration"
EXECUTE=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        -b|--base-dir)
            BASE_DIR="${2:-}"
            shift 2
            ;;
        -p|--pattern)
            DIR_PATTERN="${2:-}"
            shift 2
            ;;
        -r|--relative-log-dir)
            RELATIVE_LOG_DIR="${2:-}"
            shift 2
            ;;
        --execute)
            EXECUTE=1
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

if [ -z "${BASE_DIR}" ] || [ -z "${DIR_PATTERN}" ] || [ -z "${RELATIVE_LOG_DIR}" ]; then
    echo "错误: --base-dir、--pattern、--relative-log-dir 均不能为空" >&2
    exit 1
fi

if [ "${RELATIVE_LOG_DIR}" = "." ] || [ "${RELATIVE_LOG_DIR}" = "/" ] || [[ "${RELATIVE_LOG_DIR}" = /* ]]; then
    echo "错误: --relative-log-dir 必须是安全的相对目录，不能是 .、/ 或绝对路径: ${RELATIVE_LOG_DIR}" >&2
    exit 1
fi

if [ ! -d "${BASE_DIR}" ]; then
    echo "错误: 基础目录不存在: ${BASE_DIR}" >&2
    exit 1
fi

if [ "${EXECUTE}" -eq 1 ]; then
    echo "运行模式: execute，将删除匹配日志目录"
else
    echo "运行模式: dry-run，只打印将要删除的目录"
fi

echo "扫描目录: ${BASE_DIR}"
echo "匹配模式: ${DIR_PATTERN}"
echo "日志相对目录: ${RELATIVE_LOG_DIR}"
echo "=================================================="

count=0
while IFS= read -r -d '' TARGET_DIR; do
    LOG_DIR="${TARGET_DIR}/${RELATIVE_LOG_DIR}"

    if [ -d "${LOG_DIR}" ]; then
        if [ "${EXECUTE}" -eq 1 ]; then
            echo "删除: ${LOG_DIR}"
            rm -rf "${LOG_DIR}"
        else
            echo "将删除: ${LOG_DIR}"
        fi
        count=$((count + 1))
    else
        echo "跳过 (未找到): ${LOG_DIR}"
    fi
done < <(find "${BASE_DIR}" -maxdepth 1 -type d -name "${DIR_PATTERN}" -print0 | sort -z)

echo "=================================================="
if [ "${EXECUTE}" -eq 1 ]; then
    echo "删除目录数：${count}"
else
    echo "dry-run 匹配目录数：${count}"
fi
echo "脚本执行完毕。"
