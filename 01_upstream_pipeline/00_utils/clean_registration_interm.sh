#!/usr/bin/env bash
# 清理指定样本、对齐批次中 interm 直属的 tif/tiff/mat 文件。
# 默认仅预览；--execute 仍需交互确认。
# 需要 Bash 4+ 和 GNU coreutils。运行期间相关 pipeline 必须停止。

set -euo pipefail
shopt -s nullglob dotglob

# 默认参数
SRC_PARENT="/gpfs/share/home/2401111558/labShare/2401111558/01_project/08_projGBM/01_Data/03_rawTifDir"
SAMPLES=""
REGISTRATION_PATTERNS=""
FORMATS=""
EXECUTE=0

usage() {
    cat <<'EOF'
用法:
  bash clean_registration_interm.sh \
      --samples "GBM001 GBM002" \
      --registration_patterns "02_registration001_*" \
      --formats "tif mat" \
      [--dry_run | --execute]

参数:
  --src_parent DIR             数据根目录
  --samples NAMES              精确样本名列表，空格分隔，必须指定
  --registration_patterns PATS 对齐目录 glob 列表，空格分隔，必须指定
                              每个模式必须以 02_registration 开头
  --formats TYPES             tif / tiff / mat，空格分隔，必须指定
  --dry_run                   仅预览，默认行为
  --execute                   打印清单后交互确认，再删除
  --help                      显示帮助

清理范围:
  根目录/样本/02_registration*/Position*/interm/直属普通文件

不递归、不删除目录、不跟随符号链接。
tif 与 tiff 分开选择；扩展名匹配不区分大小写。
列表参数必须用引号包裹；样本名和目录模式不支持内含空白。
删除不可恢复且不是事务，运行期间目录不得被并发修改。
EOF
}

die() {
    printf '错误: %s\n' "$*" >&2
    exit 1
}

# 参数解析
while (( $# > 0 )); do
    case "$1" in
        --src_parent|--samples|--registration_patterns|--formats)
            (( $# >= 2 )) || die "$1 缺少参数值"
            [[ -n "$2" && "$2" != --* ]] || die "$1 参数值为空或缺失"
            case "$1" in
                --src_parent) SRC_PARENT="$2" ;;
                --samples) SAMPLES="$2" ;;
                --registration_patterns) REGISTRATION_PATTERNS="$2" ;;
                --formats) FORMATS="$2" ;;
            esac
            shift 2
            ;;
        --dry_run)
            EXECUTE=0
            shift
            ;;
        --execute)
            EXECUTE=1
            shift
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            die "未知参数: $1"
            ;;
    esac
done

[[ -n "$SAMPLES" ]] || die "必须指定 --samples"
[[ -n "$REGISTRATION_PATTERNS" ]] ||
    die "必须指定 --registration_patterns"
[[ -n "$FORMATS" ]] || die "必须指定 --formats"

# 将空格分隔列表转换为数组，拒绝多行列表
for value in "$SAMPLES" "$REGISTRATION_PATTERNS" "$FORMATS"; do
    [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] ||
        die "列表参数不能包含换行符"
done

read -r -a sample_list <<< "$SAMPLES"
read -r -a pattern_list <<< "$REGISTRATION_PATTERNS"
read -r -a format_list <<< "$FORMATS"

(( ${#sample_list[@]} > 0 )) || die "样本列表为空"
(( ${#pattern_list[@]} > 0 )) || die "对齐目录模式列表为空"
(( ${#format_list[@]} > 0 )) || die "格式列表为空"

[[ -d "$SRC_PARENT" ]] || die "根目录不存在: $SRC_PARENT"
SRC_PARENT=$(realpath -e -- "$SRC_PARENT")
[[ "$SRC_PARENT" != "/" ]] || die "不允许以 / 作为根目录"

declare -A allowed_formats=()
declare -A seen_files=()
declare -a candidates=()

for format in "${format_list[@]}"; do
    format="${format,,}"
    case "$format" in
        tif|tiff|mat)
            allowed_formats["$format"]=1
            ;;
        *)
            die "不允许的格式: $format；仅支持 tif、tiff、mat"
            ;;
    esac
done

for pattern in "${pattern_list[@]}"; do
    [[ "$pattern" == 02_registration* && "$pattern" != */* ]] ||
        die "目录模式必须以 02_registration 开头且不能含 /: $pattern"
done

# 先验证所有样本，避免参数错误时已开始删除
for sample in "${sample_list[@]}"; do
    [[ "$sample" =~ ^GBM[[:alnum:]_-]+$ ]] ||
        die "无效样本名: $sample"
    sample_dir="$SRC_PARENT/$sample"
    [[ -d "$sample_dir" && ! -L "$sample_dir" ]] ||
        die "样本目录不存在或为符号链接: $sample_dir"
done

printf '根目录: %s\n样本: %s\n对齐目录模式: %s\n格式: %s\n' \
    "$SRC_PARENT" "$SAMPLES" "$REGISTRATION_PATTERNS" "$FORMATS"
printf '执行删除: %s（0=仅预览，1=交互确认后删除）\n' "$EXECUTE"

# 收集清单。只展开固定层级，不递归、不跟随符号链接。
for sample in "${sample_list[@]}"; do
    sample_dir="$SRC_PARENT/$sample"
    matched_dirs=0
    sample_count=0

    for reg_dir in "$sample_dir"/02_registration*; do
        [[ -d "$reg_dir" && ! -L "$reg_dir" ]] || continue
        reg_name="${reg_dir##*/}"
        matched=0

        for pattern in "${pattern_list[@]}"; do
            # 此处故意不引用右侧变量，使其按 glob 匹配。
            if [[ "$reg_name" == $pattern ]]; then
                matched=1
                break
            fi
        done
        (( matched == 1 )) || continue

        matched_dirs=$((matched_dirs + 1))
        printf '[批次] %s\n' "$reg_dir"

        for position_dir in "$reg_dir"/Position*; do
            [[ -d "$position_dir" && ! -L "$position_dir" ]] || continue
            interm_dir="$position_dir/interm"
            [[ -d "$interm_dir" && ! -L "$interm_dir" ]] || continue

            for file in "$interm_dir"/*; do
                [[ -f "$file" && ! -L "$file" ]] || continue
                extension="${file##*.}"
                extension="${extension,,}"
                [[ -n "${allowed_formats[$extension]:-}" ]] || continue
                [[ -z "${seen_files[$file]:-}" ]] || continue

                seen_files["$file"]=1
                candidates+=("$file")
                sample_count=$((sample_count + 1))
                printf '[候选] %q\n' "$file"
            done
        done
    done

    printf '[样本汇总] %s | 匹配批次=%d | 新增候选文件=%d\n' \
        "$sample" "$matched_dirs" "$sample_count"
done

count=${#candidates[@]}
printf '候选文件总数: %d\n' "$count"

if (( count == 0 )); then
    printf '没有匹配文件，不执行任何删除。\n'
    exit 0
fi

if (( EXECUTE == 0 )); then
    printf 'DRY_RUN 完成，未删除任何文件。\n'
    exit 0
fi

# 删除前必须由操作者确认，禁止无交互执行。
[[ -t 0 ]] || die "--execute 必须在交互终端运行"
printf '不可恢复操作：请确认相关 pipeline 已停止且不再需要这些文件。\n'
printf '输入 DELETE %d 确认删除，其他输入取消: ' "$count"
IFS= read -r confirmation || die "未收到确认"
[[ "$confirmation" == "DELETE $count" ]] || die "已取消，未删除文件"

# 执行前重新检查清单中的文件和各层目录。
# 不支持扫描、确认、删除期间目录被并发替换。
for file in "${candidates[@]}"; do
    [[ -f "$file" && ! -L "$file" ]] ||
        die "候选文件状态变化，停止: $file"

    parent="${file%/*}"
    while [[ "$parent" != "$SRC_PARENT" ]]; do
        [[ "$parent" == "$SRC_PARENT/"* ]] ||
            die "路径超出根目录: $file"
        [[ -d "$parent" && ! -L "$parent" ]] ||
            die "目录状态变化，停止: $parent"
        parent="${parent%/*}"
    done
done

deleted=0
for file in "${candidates[@]}"; do
    if ! rm -- "$file"; then
        die "删除失败，已删除 $deleted 个文件，停止于: $file"
    fi
    deleted=$((deleted + 1))
    printf '[已删除] %q\n' "$file"
done

printf '完成: 删除 %d 个文件；未删除任何目录。\n' "$deleted"
