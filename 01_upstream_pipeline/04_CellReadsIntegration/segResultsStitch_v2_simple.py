import os
import argparse
import numpy as np
import pandas as pd
from glob import glob
import re
import warnings
warnings.filterwarnings("ignore")

def command_args():
    desc = "Merge reads and cell centers from multiple FOVs without spatial stitching"
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('-ID', '--input_dir', type=str, required=True, help='The input project directory containing Position folders')
    parser.add_argument('-OD', '--output_dir', type=str, required=True, help='Output directory for merged results')
    parser.add_argument('-SM', '--seg_method', type=str, required=True, help='Segmentation method: clustermap or watershed')
    parser.add_argument('--suffix', type=str, required=False, default='merged', help='Suffix for output files')
    return parser.parse_args()

def main():
    args = command_args()
    input_regpath = args.input_dir
    outputpath = args.output_dir
    seg_method = args.seg_method
    os.makedirs(outputpath, exist_ok=True)

    proj_name = os.path.basename(os.path.normpath(input_regpath))
    cell_center_path = os.path.join(outputpath, f"cell_centers_{proj_name}_{seg_method}_{args.suffix}.csv")
    remain_reads_path = os.path.join(outputpath, f"remain_reads_{proj_name}_{seg_method}_{args.suffix}.csv")

    print("============ MERGING FOVS ============")
    
    # 查找所有的 Position 文件夹
    pos_dirs = sorted(glob(os.path.join(input_regpath, 'Position*')))
    if not pos_dirs:
        print(f"Error: No Position folders found in {input_regpath}")
        return

    all_reads = []
    all_cells = []
    cell_barcode_offset = 0  # 用于累加 cell_barcode，确保全局唯一

    processed_tiles = 0

    for pos_dir in pos_dirs:
        # 提取 FOV 编号
        match = re.search(r'Position(\d+)', os.path.basename(pos_dir))
        if not match:
            continue
        tile_order = int(match.group(1))
        
        dfpath = os.path.join(pos_dir, 'seg', seg_method)
        reads_file = os.path.join(dfpath, 'remain_reads_raw.csv')
        cells_file = os.path.join(dfpath, 'cell_center.csv')
        
        if not os.path.exists(reads_file) or not os.path.exists(cells_file):
            print(f"- Tile {tile_order}: Missing reads or cells file. Skipping.")
            continue
            
        print(f"Processing tile {tile_order}...")
        
        # 读取数据
        remain_reads_t = pd.read_csv(reads_file, index_col=0).reset_index()
        cell_center_t = pd.read_csv(cells_file, index_col=0)
        
        # 统一列名格式
        if seg_method == 'clustermap':
            remain_reads_t.rename(columns={'clustermap': 'cell_barcode'}, inplace=True)
            cell_center_t.rename(columns={'x': 'column', 'y': 'row'}, inplace=True)
        elif seg_method == 'watershed':
            remain_reads_t.rename(columns={
                'Gene': 'gene', 
                'x': 'spot_location_1',
                'y': 'spot_location_2',
                'z': 'spot_location_3'
            }, inplace=True)
            cell_center_t.rename(columns={'x': 'column', 'y': 'row'}, inplace=True)

        # 记录来源 Tile 信息 (不再需要 gridc_gridr)
        remain_reads_t['tilenum'] = tile_order
        cell_center_t['tilenum'] = tile_order

        # 备份原始 barcode
        remain_reads_t['raw_cell_barcode'] = remain_reads_t['cell_barcode']
        cell_center_t['raw_cell_barcode'] = cell_center_t['cell_barcode']

        # 处理 cell_barcode 累加机制，保证不同FOV的细胞ID不重复
        process_mask = remain_reads_t['cell_barcode'] == -1
        
        # 对属于有效细胞的 reads 进行 barcode 累加
        remain_reads_t.loc[~process_mask, 'cell_barcode'] = remain_reads_t.loc[~process_mask, 'cell_barcode'] + cell_barcode_offset
        # -1 类的 reads (例如无细胞归属的 process reads) 设为 0
        remain_reads_t.loc[process_mask, 'cell_barcode'] = 0
        
        # 对细胞中心的 barcode 进行累加
        cell_center_t['cell_barcode'] = cell_center_t['cell_barcode'] + cell_barcode_offset

        # 基础过滤: 仅移除 noise (is_noise == -1)
        if 'is_noise' in remain_reads_t.columns:
            reads_filtered = remain_reads_t[remain_reads_t['is_noise'] != -1]
        else:
            reads_filtered = remain_reads_t

        all_reads.append(reads_filtered)
        all_cells.append(cell_center_t)
        processed_tiles += 1

        # 更新 offset，供下一个 tile 使用
        if len(cell_center_t) > 0:
            cell_barcode_offset = np.max(cell_center_t['cell_barcode'])

    if processed_tiles == 0:
        print("No valid tiles processed.")
        return

    # 合并所有数据
    print("\n============ FINAL CONCATENATION ============")
    final_reads = pd.concat(all_reads, ignore_index=True)
    final_cells = pd.concat(all_cells, ignore_index=True)

    # 去重及格式化处理
    final_reads = final_reads.drop_duplicates(subset=None, keep='first')
    
    # 重命名空间坐标列（保持与下游分析一致）
    if 'spot_location_1' in final_reads.columns:
        final_reads.rename(columns={'spot_location_1': 'column', 'spot_location_2': 'row', 'spot_location_3': 'z'}, inplace=True)
    if 'z_axis' in final_cells.columns:
        final_cells.rename(columns={'z_axis': 'z'}, inplace=True)

    # 强制转换数据类型
    # 注意：如果有些数据是2D的没有z列，这里需要兼容处理
    read_cols_to_int = ['column', 'row', 'cell_barcode', 'raw_cell_barcode']
    if 'z' in final_reads.columns: read_cols_to_int.append('z')
    final_reads[read_cols_to_int] = final_reads[read_cols_to_int].fillna(0).astype(int)

    cell_cols_to_int = ['cell_barcode', 'column', 'row', 'raw_cell_barcode']
    if 'z' in final_cells.columns: cell_cols_to_int.append('z')
    final_cells[cell_cols_to_int] = final_cells[cell_cols_to_int].fillna(0).astype(int)

    print(f"Total tiles merged: {processed_tiles}")
    print(f"Total valid cells: {len(final_cells)}")
    print(f"Total valid reads (noise filtered): {len(final_reads)}")

    # 保存结果
    final_cells.to_csv(cell_center_path, index=False)
    final_reads.to_csv(remain_reads_path, index=False)
    print(f"\n✅ Results saved to {outputpath}")

if __name__ == '__main__':
    main()