#!/bin/bash
# ==============================================================================
# copy_h5ad_downstream.sh
# ==============================================================================
# 功能：从样本的集成结果文件夹中，按条件子串匹配子文件夹，拷贝指定文件到下游目录。
#       常用于将 upstream 集成后的 h5ad 文件分发到 downstream 分析目录。
#
# === 使用方法 ===
#
# 基本用法（使用脚本内默认参数）：
#   ./copy_h5ad_downstream.sh
#
# 常用场景：为特定样本拷贝 h5ad 文件到下游分析目录：
#   ./copy_h5ad_downstream.sh \
#       --samples "GBM003 GBM004" \
#       --conditions "GBM260421p2_mat260625 GBM260421p2_mat260626"
#
# 试运行（先看效果，不实际拷贝）：
#   ./copy_h5ad_downstream.sh --dry-run
#
# 覆盖目标已有文件：
#   ./copy_h5ad_downstream.sh --overwrite
#
# === 匹配方式 ===
#   对每个 condition 字符串，在样本的集成文件夹下遍历子文件夹名，
#   取文件夹名中包含该 condition 的子串匹配文件夹，拷贝其中匹配的文件。
#
#   目录结构示例：
#   {src_parent}/GBM003/03_integration*/
#       GBM260421p2_mat260625_xxx/
#           result.h5ad          ← 匹配 condition="GBM260421p2_mat260625"
#       GBM260421p2_mat260626_yyy/
#           result.h5ad          ← 匹配 condition="GBM260421p2_mat260626"
#   →
#   {dst_parent}/GBM260421p2_mat260625/001_rawh5ad/result.h5ad
#   {dst_parent}/GBM260421p2_mat260626/001_rawh5ad/result.h5ad
#
# === 参数说明 ===
#
#   --src-parent DIR   源父目录
#                      默认: labShare/.../03_rawTifDir
#   --samples NAMES    样本名列表（空格分隔，引号包裹）
#                      默认: "GBM001 GBM002 ... GBM009"
#   --integ-glob PAT   集成文件夹 glob 模式
#                      默认: "03_integration*"
#   --conditions NAMES 条件子串列表（空格分隔，引号包裹），每个 condition
#                      同时作为目标目录名的一部分
#                      默认: "GBM260421p2_mat260625 ..."
#   --file-pattern PAT 要拷贝的文件名通配模式
#                      默认: "*.h5ad"
#   --dst-parent DIR   目标父目录
#                      默认: 01_project/.../04_DownstreamDir
#   --dst-subdir NAME  目标子目录名，最终路径 {dst_parent}/{condition}/{dst_subdir}/
#                      默认: "001_rawh5ad"
#   --dry-run          仅打印待执行操作，不实际拷贝
#   --overwrite        覆盖目标已有同名文件（默认跳过）
#   -v, --verbose      详细输出
#   --help             显示本帮助信息
#
# 注意：拷贝用 cp 而非 mv，保留源数据；大文件无进度条。
#
# ==============================================================================

set -euo pipefail

# ===== Defaults =====
# 当前场景默认路径
DEF_SRC_PARENT="/gpfs/share/home/2401111558/labShare/2401111558/01_project/08_projGBM/01_Data/03_rawTifDir"
DEF_DST_PARENT="/gpfs/share/home/2401111558/01_project/08_projGBM/01_Data/04_DownstreamDir"
DEF_SAMPLES="GBM001 GBM002 GBM003 GBM004 GBM005 GBM006 GBM007 GBM008 GBM009"
DEF_INTEG_GLOB="03_integration*"
DEF_CONDITIONS="GBMp1p2p3_mat260714"
DEF_FILE_PATTERN="*.h5ad"
DEF_DST_SUBDIR="001_rawh5ad"

# ===== Parse Arguments =====
SRC_PARENT="$DEF_SRC_PARENT"
DST_PARENT="$DEF_DST_PARENT"
SAMPLES="$DEF_SAMPLES"
INTEG_GLOB="$DEF_INTEG_GLOB"
CONDITIONS="$DEF_CONDITIONS"
FILE_PATTERN="$DEF_FILE_PATTERN"
DST_SUBDIR="$DEF_DST_SUBDIR"
DRY_RUN=0
OVERWRITE=0
VERBOSE=0

usage() {
    cat <<EOF
功能: 从样本集成文件夹中按条件子串匹配子文件夹，拷贝文件到下游目录。

用法:
  ./$(basename "$0") [选项]

常用示例:
  ./$(basename "$0") --samples "GBM003 GBM004" --conditions "GBM260421p2_mat260625"
  ./$(basename "$0") --dry-run                          # 试运行
  ./$(basename "$0") --overwrite                        # 覆盖已有

选项:
  --src-parent DIR   源父目录 (默认: labShare/.../03_rawTifDir)
  --samples NAMES    样本名列表，空格分隔，引号包裹 (默认: GBM001-GBM009)
  --integ-glob PAT   集成文件夹 glob 模式 (默认: 03_integration*)
  --conditions NAMES 条件子串列表，引号包裹，同时作为目标目录名
  --file-pattern PAT 要拷贝的文件通配模式 (默认: *.h5ad)
  --dst-parent DIR   目标父目录 (默认: .../04_DownstreamDir)
  --dst-subdir NAME  目标子目录名，路径 {condition}/{dst-subdir}/ (默认: 001_rawh5ad)
  --dry-run          仅打印，不实际拷贝
  --overwrite        覆盖目标已有文件 (默认跳过)
  -v, --verbose      详细输出
  --help             显示本帮助
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --src-parent)   SRC_PARENT="$2";   shift 2 ;;
        --samples)      SAMPLES="$2";      shift 2 ;;
        --integ-glob)   INTEG_GLOB="$2";   shift 2 ;;
        --conditions)   CONDITIONS="$2";   shift 2 ;;
        --file-pattern) FILE_PATTERN="$2"; shift 2 ;;
        --dst-parent)   DST_PARENT="$2";   shift 2 ;;
        --dst-subdir)   DST_SUBDIR="$2";   shift 2 ;;
        --dry-run)      DRY_RUN=1;         shift   ;;
        --overwrite)    OVERWRITE=1;       shift   ;;
        -v|--verbose)   VERBOSE=1;         shift   ;;
        --help)         usage               ;;
        *) echo "错误: 未知参数 $1"; usage ;;
    esac
done

# ===== Configuration Summary =====
echo "========================================"
echo "  copy_h5ad_downstream.sh"
echo "========================================"
echo "  源父目录:       $SRC_PARENT"
echo "  目标父目录:     $DST_PARENT"
echo "  样本:           $SAMPLES"
echo "  集成文件夹:     $INTEG_GLOB"
echo "  条件列表:       $CONDITIONS"
echo "  文件模式:       $FILE_PATTERN"
echo "  目标子目录:     $DST_SUBDIR"
echo "  Dry-run:        $([ $DRY_RUN -eq 1 ] && echo '是' || echo '否')"
echo "  覆盖已有:       $([ $OVERWRITE -eq 1 ] && echo '是' || echo '否（跳过已存在）')"
echo "========================================"

# ===== Validation =====
if [ ! -d "$SRC_PARENT" ]; then
    echo "错误: 源父目录不存在: $SRC_PARENT" >&2
    exit 1
fi
if [ ! -d "$DST_PARENT" ]; then
    echo "错误: 目标父目录不存在: $DST_PARENT" >&2
    exit 1
fi

# ===== Main Loop =====
COPY_COUNT=0
SKIP_COUNT=0

for sample in $SAMPLES; do
    # 1. 查找集成文件夹（取第一个匹配）
    integ_dirs=("$SRC_PARENT/$sample"/$INTEG_GLOB)
    if [ ${#integ_dirs[@]} -eq 0 ] || [ ! -d "${integ_dirs[0]}" ]; then
        echo "  跳过 $sample: 未找到匹配 $INTEG_GLOB 的集成文件夹"
        continue
    fi
    integ_dir="${integ_dirs[0]}"

    # 2. 对每个条件，在集成文件夹中查找包含该条件子串的子文件夹
    for condition in $CONDITIONS; do
        found=0
        for sub_dir in "$integ_dir"/*/; do
            # 去掉末尾斜杠，取文件夹名
            sub_dir_name=$(basename "$sub_dir")
            # 子串匹配：文件夹名是否包含 condition
            if [[ "$sub_dir_name" == *"$condition"* ]]; then
                found=1
                # 3. 在匹配的子文件夹中查找文件
                for f in "$sub_dir"$FILE_PATTERN; do
                    if [ ! -f "$f" ]; then
                        continue
                    fi
                    fname=$(basename "$f")
                    # 目标路径
                    dst_dir="$DST_PARENT/$condition/$DST_SUBDIR"
                    dst_file="$dst_dir/$fname"

                    # 检查目标文件是否已存在
                    if [ -f "$dst_file" ] && [ $OVERWRITE -eq 0 ]; then
                        if [ $VERBOSE -eq 1 ]; then
                            echo "  跳过（已存在）: $dst_file"
                        fi
                        SKIP_COUNT=$((SKIP_COUNT + 1))
                        continue
                    fi

                    # 确保目标目录存在
                    if [ $DRY_RUN -eq 0 ]; then
                        mkdir -p "$dst_dir"
                    fi

                    # 打印或执行拷贝
                    if [ $DRY_RUN -eq 1 ]; then
                        echo "  [DRY-RUN] cp \"$f\" → \"$dst_file\""
                    else
                        # 用 cp 而非 mv，保留源数据
                        # 大文件拷贝显示进度
                        if [ $VERBOSE -eq 1 ]; then
                            echo "  拷贝: $f → $dst_file"
                        fi
                        cp "$f" "$dst_file"
                        echo "  完成: $dst_file"
                    fi
                    COPY_COUNT=$((COPY_COUNT + 1))
                done
            fi
        done
        if [ $found -eq 0 ] && [ $VERBOSE -eq 1 ]; then
            echo "  注意: $sample/$integ_dir_name 下未找到包含 '$condition' 的子文件夹"
        fi
    done
done

# ===== Summary =====
echo "========================================"
if [ $DRY_RUN -eq 1 ]; then
    echo "  Dry-run 完成: 待拷贝 $COPY_COUNT 文件, 将跳过 $SKIP_COUNT 文件"
    echo "  请移除 --dry-run 执行实际拷贝"
else
    echo "  拷贝完成: 成功 $COPY_COUNT 文件, 跳过 $SKIP_COUNT 文件"
fi
echo "========================================"
