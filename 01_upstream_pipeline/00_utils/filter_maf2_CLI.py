import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT_MARKER = b"<XYZStagePointDefinitionList"


def extract_preamble(raw_bytes):
    """Return the original MAF header before the stage-point root element."""
    root_offset = raw_bytes.find(ROOT_MARKER)
    if root_offset < 0:
        raise ValueError("MAF root element XYZStagePointDefinitionList not found")
    return raw_bytes[:root_offset]


def filter_maf_file(input_file, output_file, start_id, end_id):
    try:
        input_path = Path(input_file)
        output_path = Path(output_file)
        raw_bytes = input_path.read_bytes()
        preamble = extract_preamble(raw_bytes)
        root = ET.fromstring(raw_bytes)

        # 记录初始数量，用于对比
        initial_count = len(root.findall('XYZStagePointDefinition'))
        
        # 查找所有子节点并筛选
        # 我们使用列表推导式找到需要删除的节点
        to_remove = []
        for point in root.findall('XYZStagePointDefinition'):
            pos_id_str = point.get('PositionID')
            if pos_id_str:
                pos_id = int(pos_id_str)
                # 闭区间删除
                if start_id <= pos_id <= end_id:
                    to_remove.append(point)

        # 执行删除操作
        for point in to_remove:
            root.remove(point)

        final_count = len(root.findall('XYZStagePointDefinition'))
        deleted_count = initial_count - final_count

        # ElementTree 不保留 XML 声明和 LAS X 注释，需把原始 MAF 文件头原样拼回。
        output_bytes = preamble + ET.tostring(root, encoding="utf-8")
        if not output_bytes.startswith(preamble):
            raise ValueError("serialized MAF preamble changed unexpectedly")
        output_path.write_bytes(output_bytes)

        print(f"处理完成！")
        print(f"原始位置数量: {initial_count}")
        print(f"已删除数量: {deleted_count} (ID {start_id} 到 {end_id})")
        print(f"剩余位置数量: {final_count}")
        print(f"结果已保存至: {output_file}")

    except Exception as e:
        print(f"发生错误: {e}")

def build_parser():
    parser = argparse.ArgumentParser(
        description="删除指定 PositionID 区间内的 XYZStagePointDefinition 元素。",
        epilog=(
            "示例:\n"
            "  python filter_maf2.py --input_file input.maf --output_file output.maf "
            "--start_id 331 --end_id 488"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input_file", required=True, help="输入 MAF 文件路径")
    parser.add_argument("--output_file", required=True, help="输出 MAF 文件路径")
    parser.add_argument("--start_id", required=True, type=int, help="删除区间起始 PositionID")
    parser.add_argument("--end_id", required=True, type=int, help="删除区间结束 PositionID")
    return parser

def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.start_id > args.end_id:
        parser.error("start_id 必须小于或等于 end_id")
    filter_maf_file(args.input_file, args.output_file, args.start_id, args.end_id)

if __name__ == "__main__":
    main()
