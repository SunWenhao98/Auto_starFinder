#!/bin/bash

set -euo pipefail

### 使用方法 ------------------------------------------------------------
# 功能：
#   备份 rawTifDir 下各样本的 02_registration001* 目录中 goodPoints* 文件。
#   默认只扫描一级 Position* 子目录内的顶层 goodPoints* 文件：
#     BASE_DIR/<sample>/02_registration001*/Position*/goodPoints*
#   不递归搜索 Position* 更深层目录。
#
# 默认行为：
#   dry-run，只打印将要备份的文件，不创建目录、不复制文件。
#   只有传入 --execute 才执行 cp -p 复制。
#
# 示例：
#   bash 004_backup_goodpoints_top_level.sh
#
#   bash 004_backup_goodpoints_top_level.sh --execute
#
#   bash 004_backup_goodpoints_top_level.sh \
#     --base-dir /path/to/03_rawTifDir \
#     --backup-root /path/to/goodPoints_backup_YYMMDD_HHMMSS \
#     --sample-pattern 'GBM*' \
#     --registration-pattern '02_registration001*' \
#     --child-pattern 'Position*' \
#     --file-pattern 'goodPoints*' \
#     --execute
#
# 参数：
#   --base-dir DIR                 rawTifDir 根目录。
#   --backup-root DIR              备份输出目录；默认在 base-dir 的父目录下创建带时间戳目录。
#   --sample-pattern PATTERN       样本目录匹配模式，默认 *。
#   --registration-pattern PATTERN registration 目录匹配模式，默认 02_registration001*。
#   --child-pattern PATTERN        registration 下一级子目录匹配模式，默认 Position*。
#   --file-pattern PATTERN         goodPoints 文件匹配模式，默认 goodPoints*。
#   --include-registration-root    同时备份 registration 根目录顶层的 goodPoints* 文件。
#   --execute                      实际执行复制；不传则 dry-run。
#   -h, --help                     打印帮助并退出。
#
# 注意：
#   1. 本脚本只复制普通文件，不复制目录。
#   2. 每一层都只使用 -maxdepth 1，不做递归搜索。
#   3. 备份目录会保留相对路径：sample/registration/Position/file。
#   4. 目标文件已存在时默认报错退出，避免覆盖既有备份。

usage() {
    sed -n '/^### 使用方法/,/^usage()/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
}

timestamp() {
    date '+%y%m%d_%H%M%S'
}

BASE_DIR="/gpfs/share/home/2401111558/labShare/2401111558/01_project/08_projGBM/01_Data/03_rawTifDir"
BACKUP_ROOT=""
SAMPLE_PATTERN="*"
REGISTRATION_PATTERN="02_registration001*"
CHILD_PATTERN="Position*"
FILE_PATTERN="goodPoints*"
INCLUDE_REGISTRATION_ROOT=false
EXECUTE=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --base-dir)
            BASE_DIR="${2:-}"
            shift 2
            ;;
        --backup-root)
            BACKUP_ROOT="${2:-}"
            shift 2
            ;;
        --sample-pattern)
            SAMPLE_PATTERN="${2:-}"
            shift 2
            ;;
        --registration-pattern)
            REGISTRATION_PATTERN="${2:-}"
            shift 2
            ;;
        --child-pattern)
            CHILD_PATTERN="${2:-}"
            shift 2
            ;;
        --file-pattern)
            FILE_PATTERN="${2:-}"
            shift 2
            ;;
        --include-registration-root)
            INCLUDE_REGISTRATION_ROOT=true
            shift
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

if [ -z "${BASE_DIR}" ]; then
    echo "错误: --base-dir 不能为空" >&2
    exit 1
fi

if [ ! -d "${BASE_DIR}" ]; then
    echo "错误: base-dir 不存在: ${BASE_DIR}" >&2
    exit 1
fi

if [ -z "${BACKUP_ROOT}" ]; then
    BASE_PARENT_DIR=$(dirname "${BASE_DIR}")
    BACKUP_ROOT="${BASE_PARENT_DIR}/zz_goodPoints_backup_$(timestamp)"
fi

if [ "${BACKUP_ROOT}" = "${BASE_DIR}" ]; then
    echo "错误: backup-root 不能等于 base-dir" >&2
    exit 1
fi

if [ -e "${BACKUP_ROOT}" ] && [ ! -d "${BACKUP_ROOT}" ]; then
    echo "错误: backup-root 已存在但不是目录: ${BACKUP_ROOT}" >&2
    exit 1
fi

MANIFEST_PATH="${BACKUP_ROOT}/backup_manifest.tsv"

echo "开始扫描 goodPoints 备份目标"
echo "base-dir: ${BASE_DIR}"
echo "backup-root: ${BACKUP_ROOT}"
echo "sample-pattern: ${SAMPLE_PATTERN}"
echo "registration-pattern: ${REGISTRATION_PATTERN}"
echo "child-pattern: ${CHILD_PATTERN}"
echo "file-pattern: ${FILE_PATTERN}"
echo "include-registration-root: ${INCLUDE_REGISTRATION_ROOT}"
echo "mode: $([ "${EXECUTE}" = true ] && echo execute || echo dry-run)"
echo "=================================================="

if [ "${EXECUTE}" = true ]; then
    mkdir -p "${BACKUP_ROOT}"
    printf 'status\tsource\tdestination\tbytes\n' > "${MANIFEST_PATH}"
fi

found_count=0
copied_count=0
skipped_count=0

backup_file() {
    local source_file="$1"
    local rel_path="$2"
    local dest_file="${BACKUP_ROOT}/${rel_path}"
    local dest_dir
    local bytes

    dest_dir=$(dirname "${dest_file}")
    bytes=$(wc -c < "${source_file}" | tr -d ' ')
    found_count=$((found_count + 1))

    if [ -e "${dest_file}" ]; then
        echo "[SKIP] 目标已存在: ${dest_file}"
        skipped_count=$((skipped_count + 1))
        if [ "${EXECUTE}" = true ]; then
            printf 'skip_exists\t%s\t%s\t%s\n' "${source_file}" "${dest_file}" "${bytes}" >> "${MANIFEST_PATH}"
        fi
        return 0
    fi

    if [ "${EXECUTE}" = true ]; then
        mkdir -p "${dest_dir}"
        cp -p "${source_file}" "${dest_file}"
        printf 'copied\t%s\t%s\t%s\n' "${source_file}" "${dest_file}" "${bytes}" >> "${MANIFEST_PATH}"
        copied_count=$((copied_count + 1))
        echo "[COPY] ${source_file} -> ${dest_file}"
    else
        echo "[DRY-RUN] ${source_file} -> ${dest_file} (${bytes} bytes)"
    fi
}

while IFS= read -r -d '' sample_dir; do
    sample_name=$(basename "${sample_dir}")

    case "${sample_name}" in
        zz_goodPoints_backup_*)
            continue
            ;;
    esac

    while IFS= read -r -d '' registration_dir; do
        registration_name=$(basename "${registration_dir}")

        if [ "${INCLUDE_REGISTRATION_ROOT}" = true ]; then
            while IFS= read -r -d '' goodpoints_file; do
                file_name=$(basename "${goodpoints_file}")
                backup_file "${goodpoints_file}" "${sample_name}/${registration_name}/${file_name}"
            done < <(find "${registration_dir}" -maxdepth 1 -type f -name "${FILE_PATTERN}" -print0 | sort -z)
        fi

        while IFS= read -r -d '' child_dir; do
            child_name=$(basename "${child_dir}")
            while IFS= read -r -d '' goodpoints_file; do
                file_name=$(basename "${goodpoints_file}")
                backup_file "${goodpoints_file}" "${sample_name}/${registration_name}/${child_name}/${file_name}"
            done < <(find "${child_dir}" -maxdepth 1 -type f -name "${FILE_PATTERN}" -print0 | sort -z)
        done < <(find "${registration_dir}" -maxdepth 1 -type d -name "${CHILD_PATTERN}" -print0 | sort -z)

    done < <(find "${sample_dir}" -maxdepth 1 -type d -name "${REGISTRATION_PATTERN}" -print0 | sort -z)

done < <(find "${BASE_DIR}" -maxdepth 1 -type d -name "${SAMPLE_PATTERN}" -print0 | sort -z)

echo "=================================================="
echo "发现 goodPoints 文件数: ${found_count}"
echo "实际复制文件数: ${copied_count}"
echo "跳过文件数: ${skipped_count}"
if [ "${EXECUTE}" = true ]; then
    echo "manifest: ${MANIFEST_PATH}"
    echo "STATUS: SUCCESS"
else
    echo "dry-run 完成；确认无误后加 --execute 执行复制。"
fi
