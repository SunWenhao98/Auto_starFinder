import xml.etree.ElementTree as ET

def filter_maf_file(input_file, output_file):
    # 解析 XML 文件
    # 注意：ElementTree 默认不保留 XML 声明和注释
    # 我们会手动添加声明以确保结构一致
    try:
        tree = ET.parse(input_file)
        root = tree.getroot()

        # 记录初始数量，用于对比
        initial_count = len(root.findall('XYZStagePointDefinition'))
        
        # 查找所有子节点并筛选
        # 我们使用列表推导式找到需要删除的节点
        to_remove = []
        for point in root.findall('XYZStagePointDefinition'):
            pos_id_str = point.get('PositionID')
            if pos_id_str:
                pos_id = int(pos_id_str)
                # 闭区间删除：331 <= id <= 488
                if 331 <= pos_id <= 488:
                    to_remove.append(point)

        # 执行删除操作
        for point in to_remove:
            root.remove(point)

        final_count = len(root.findall('XYZStagePointDefinition'))
        deleted_count = initial_count - final_count

        # 写入文件
        # xml_declaration=True 会自动添加 <?xml version='1.0' encoding='utf-8'?>
        # encoding="utf-8" 确保字符集正确
        tree.write(output_file, encoding="utf-8", xml_declaration=True)
        
        # 由于 LAS X 格式通常包含特定的注释头，我们需要手动补回这些信息
        prepend_header(output_file)

        print(f"处理完成！")
        print(f"原始位置数量: {initial_count}")
        print(f"已删除数量: {deleted_count} (ID 331 到 488)")
        print(f"剩余位置数量: {final_count}")
        print(f"结果已保存至: {output_file}")

    except Exception as e:
        print(f"发生错误: {e}")

def prepend_header(file_path):
    """手动添加 Leica 特有的注释头以保持文件结构完全一致"""
    header = [
        '<!--Leica Application Suite X (LAS X)-->\n',
        '<!--Leica Microsystems CMS GmbH-->\n',
        '<!--http://www.confocal-microscopy.com-->\n',
        '<!--LAS X 4.6.1.27508-->\n'
    ]
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.readlines()

    # 在第一行 <?xml...?> 之后插入注释
    new_content = [content[0]] + header + content[1:]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_content)

if __name__ == "__main__":
    # 请确保将 'input.maf' 替换为你实际的文件名
    filter_maf_file('input.maf', 'output.maf')