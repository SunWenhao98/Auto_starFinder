import argparse
import pandas as pd
import numpy as np
import math
import os
from scipy.spatial import cKDTree

def rotate_points(xy, radians, origin=(0, 0)):
    """
    Rotates 2D coordinates around a specific origin using vectorization.
    (Matches the calculation process exactly - CLOCKWISE in image coordinates)
    """
    x, y = xy
    offset_x, offset_y = origin
    adjusted_x = (x - offset_x)
    adjusted_y = (y - offset_y)
    
    cos_rad = math.cos(radians)
    sin_rad = math.sin(radians)
    
    # 图像坐标系下的顺时针旋转公式
    qx = offset_x + (cos_rad * adjusted_x - sin_rad * adjusted_y)
    qy = offset_y + (sin_rad * adjusted_x + cos_rad * adjusted_y)
    
    qx = np.floor(qx + 0.5).astype(int)
    qy = np.floor(qy + 0.5).astype(int)
    
    return pd.DataFrame({'column': qx, 'row': qy})

def main():
    parser = argparse.ArgumentParser(description="Restore _rbRNA and _ntRNA suffixes by mapping processed coordinates back to rotated raw coordinates.")
    
    # 文件路径参数
    parser.add_argument('--raw_csv', required=True, help="原始未清洗的CSV文件路径 (包含x, y, z, Gene)")
    parser.add_argument('--processed_csv', required=True, help="计算后的输出CSV文件路径 (包含gene_name, spot_location_1/2/3)")
    parser.add_argument('--output_csv', required=True, help="匹配还原后缀后的输出CSV文件路径")
    
    # 图像与旋转参数
    parser.add_argument('--img_c', type=int, required=True, help="原始图片的宽度/列数 (用于计算旋转原点)")
    parser.add_argument('--img_r', type=int, required=True, help="原始图片的高度/行数 (用于计算旋转原点)")
    parser.add_argument('--rotation_deg', type=float, default=90.0, help="旋转角度 (默认90度。顺时针为正)")
    
    # 匹配算法参数
    parser.add_argument('--tolerance', type=float, default=2.0, help="坐标匹配的最大允许误差范围 (像素/坐标单位，默认2.0)")

    args = parser.parse_args()

    # 1. 检查输入文件
    if not os.path.exists(args.raw_csv):
        raise FileNotFoundError(f"Raw CSV not found: {args.raw_csv}")
    if not os.path.exists(args.processed_csv):
        raise FileNotFoundError(f"Processed CSV not found: {args.processed_csv}")

    print(f"Loading raw transcripts from: {args.raw_csv}")
    raw_df = pd.read_csv(args.raw_csv)
    
    print(f"Loading processed spots from: {args.processed_csv}")
    processed_df = pd.read_csv(args.processed_csv)

    # 2. 从原始 Gene 列中提取 clean_gene (用于缩小匹配范围)
    # 这样可以避免把 BACE2 的点误匹配给临近的 TIMP1
    raw_df['clean_gene'] = raw_df['Gene'].str.replace(r'_rbRNA|_ntRNA', '', regex=True)

    # 3. 对原始数据应用相同的旋转逻辑，获取预测的 spot_location
    print(f"Applying {args.rotation_deg} degree rotation to raw coordinates...")
    origin = [int(args.img_c / 2 + 0.5), int(args.img_r / 2 + 0.5)]
    
    if args.rotation_deg % 360 != 0:
        xy_coords = np.array([raw_df['x'], raw_df['y']], dtype=int)
        rotated_coords = rotate_points(xy_coords, math.radians(args.rotation_deg), origin)
        raw_df['rot_x'] = rotated_coords['column']
        raw_df['rot_y'] = rotated_coords['row']
    else:
        raw_df['rot_x'] = raw_df['x']
        raw_df['rot_y'] = raw_df['y']

    # 4. 基于 cKDTree 进行高速空间坐标匹配
    print(f"Matching coordinates with tolerance <= {args.tolerance}...")
    
    # 新建一个列用于存储还原后的基因名，默认先使用当前的无后缀名
    processed_df['restored_gene'] = processed_df['gene_name']
    
    match_count = 0
    miss_count = 0

    # 按照 base_gene 和 Z轴进行分组匹配 (极大提升准确率和计算速度)
    grouped_processed = processed_df.groupby(['gene_name', 'spot_location_3'])
    
    for (gene, z_axis), proc_group in grouped_processed:
        # 在原始数据中找到相同基因且相同 Z轴层面的点
        raw_group = raw_df[(raw_df['clean_gene'] == gene) & (raw_df['z'] == z_axis)]
        
        if raw_group.empty:
            miss_count += len(proc_group)
            continue
            
        # 提取目标坐标和查询坐标
        # Raw Data (树的构建集)
        raw_coords = raw_group[['rot_x', 'rot_y']].values
        raw_genes = raw_group['Gene'].values  # 带有 _ntRNA / _rbRNA 的全名
        
        # Processed Data (查询集)
        query_coords = proc_group[['spot_location_1', 'spot_location_2']].values
        
        # 构建 KD 树
        tree = cKDTree(raw_coords)
        
        # 查询最近邻点 (距离限制为 tolerance)
        distances, indices = tree.query(query_coords, distance_upper_bound=args.tolerance)
        
        # 将匹配成功的名称写回 processed_df
        for i, (idx, dist) in enumerate(zip(indices, distances)):
            if dist <= args.tolerance and idx < len(raw_group):
                original_index = proc_group.index[i]
                processed_df.at[original_index, 'restored_gene'] = raw_genes[idx]
                match_count += 1
            else:
                miss_count += 1

    # 用还原后的数据覆盖原来的 gene_name 列 (或者你也可以选择保留为两列，这里选择覆盖以匹配原格式)
    processed_df['gene'] = processed_df['gene_name']
    processed_df['gene_name'] = processed_df['restored_gene']
    processed_df.drop(columns=['restored_gene'], inplace=True)

    print(f"Matching Complete. Matched: {match_count}, Missed (or Out of Tolerance): {miss_count}")

    # 5. 导出结果
    print(f"Saving restored data to: {args.output_csv}")
    processed_df.to_csv(args.output_csv, index=False)
    print("Done!")

if __name__ == "__main__":
    main()