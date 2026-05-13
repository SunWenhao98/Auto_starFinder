import os, sys, copy, math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.spatial import distance
from tqdm import tqdm
from glob import glob
import matplotlib
from itertools import chain
import warnings
import argparse
warnings.filterwarnings("ignore")

############################# FUNCTIONS #############################

# Read in FIJI Tile Coordinates (TileConfiguration.registered.txt and TileConfiguration.txt)
def get_coords(path, grid=False):
      f = open(path) 
      line = f.readline()
      list = []
      while line:
            if line.startswith('tile'):
                  a = np.array(line.replace('tile_','').replace('.tif; ; (',',').replace(', ',',').replace(')\n','').split(','))
                  if not grid:
                        a = [float(x) for x in a] # Remove rounding for raw coordinates
                  else:
                        # 修改网格位置计算逻辑
                        a = a.astype(float)
                        # 使用列优先顺序计算网格位置
                        tile_num = int(a[0])
                        if tile_num <= 11:  # 第一列
                            grid_x = 0
                            grid_y = tile_num - 1
                        else:
                            grid_x = (tile_num - 1) // 11  # 计算列号
                            grid_y = (tile_num - 1) % 11  # 计算行号
                        a = [a[0], grid_x, grid_y]
                  list.append(a)
            line = f.readline()
      coords_df = np.array(list)
      f.close
      return coords_df

# Find closest cell center for multiassigned reads
def closest_node(node, nodes):
      closest_index = distance.cdist([node], nodes).argmin()
      return nodes[closest_index], closest_index

def idxs_within_coords(df, top_edge, bottom_edge, right_edge, left_edge, include=True):
      if include:
            idxs = df[(df['column'] <= right_edge) & (df['column'] >= left_edge) & (df['row'] >= top_edge) & (df['row'] <= bottom_edge)]['cell_barcode'].tolist()
      else:
            idxs = df[(df['column'] < right_edge) & (df['column'] > left_edge) & (df['row'] > top_edge) & (df['row'] < bottom_edge)]['cell_barcode'].tolist()
      return idxs

def calculate_valid_region_bounds(coords_df_tuned, t_grid_c, t_grid_r, upper_left, img_c, img_r):
      """
      计算当前tile的有效区域边界（去除overlap），类似create_tile_config.py的逻辑
      返回: (start_x_norm, end_x_norm, start_y_norm, end_y_norm) - 相对于tile左上角的局部坐标
      """
      current_x = upper_left[0]  # 当前tile的左上角x坐标（全局）
      current_y = upper_left[1]  # 当前tile的左上角y坐标（全局）
      
      # 初始化边界为tile的完整范围
      start_x_global = current_x
      start_y_global = current_y
      end_x_global = current_x + img_c
      end_y_global = current_y + img_r
      
      # 检查左边的tile
      left_tile_col = t_grid_c - 1
      if left_tile_col >= 0:
            left_indices = coords_df_tuned.index[
                  (coords_df_tuned['column_count'] == left_tile_col) & 
                  (coords_df_tuned['row_count'] == t_grid_r)
            ]
            if len(left_indices) > 0:
                  order_left = left_indices[0]
                  if coords_df_tuned.loc[order_left, 'tile'] != 0:
                        left_tile_upper_left = coords_df_tuned.loc[order_left, ['column_coord_obs', 'row_coord_obs']]
                        left_tile_x = left_tile_upper_left[0]
                        # 计算overlap的中点，类似create_tile_config.py第88行
                        overlap_midpoint = int((left_tile_x + img_c - current_x) / 2 + 0.5) + current_x
                        start_x_global = overlap_midpoint
      
      # 检查右边的tile
      right_tile_col = t_grid_c + 1
      right_indices = coords_df_tuned.index[
            (coords_df_tuned['column_count'] == right_tile_col) & 
            (coords_df_tuned['row_count'] == t_grid_r)
      ]
      if len(right_indices) > 0:
            order_right = right_indices[0]
            if coords_df_tuned.loc[order_right, 'tile'] != 0:
                  right_tile_upper_left = coords_df_tuned.loc[order_right, ['column_coord_obs', 'row_coord_obs']]
                  right_tile_x = right_tile_upper_left[0]
                  # 计算overlap的中点，类似create_tile_config.py第100行
                  overlap_midpoint = int((current_x + img_c - right_tile_x) / 2 + 0.5) + right_tile_x
                  end_x_global = overlap_midpoint
      
      # 检查上边的tile
      top_tile_row = t_grid_r - 1
      if top_tile_row >= 0:
            top_indices = coords_df_tuned.index[
                  (coords_df_tuned['column_count'] == t_grid_c) & 
                  (coords_df_tuned['row_count'] == top_tile_row)
            ]
            if len(top_indices) > 0:
                  order_top = top_indices[0]
                  if coords_df_tuned.loc[order_top, 'tile'] != 0:
                        top_tile_upper_left = coords_df_tuned.loc[order_top, ['column_coord_obs', 'row_coord_obs']]
                        top_tile_y = top_tile_upper_left[1]
                        # 计算overlap的中点，类似create_tile_config.py第94行
                        overlap_midpoint = int((top_tile_y + img_r - current_y) / 2 + 0.5) + current_y
                        start_y_global = overlap_midpoint
      
      # 检查下边的tile
      bottom_tile_row = t_grid_r + 1
      bottom_indices = coords_df_tuned.index[
            (coords_df_tuned['column_count'] == t_grid_c) & 
            (coords_df_tuned['row_count'] == bottom_tile_row)
      ]
      if len(bottom_indices) > 0:
            order_bottom = bottom_indices[0]
            if coords_df_tuned.loc[order_bottom, 'tile'] != 0:
                  bottom_tile_upper_left = coords_df_tuned.loc[order_bottom, ['column_coord_obs', 'row_coord_obs']]
                  bottom_tile_y = bottom_tile_upper_left[1]
                  # 计算overlap的中点，类似create_tile_config.py第106行
                  overlap_midpoint = int((current_y + img_r - bottom_tile_y) / 2 + 0.5) + bottom_tile_y
                  end_y_global = overlap_midpoint
      
      start_x_norm = start_x_global - current_x
      start_y_norm = start_y_global - current_y
      end_x_norm = end_x_global - current_x
      end_y_norm = end_y_global - current_y
      
      return start_x_norm, end_x_norm, start_y_norm, end_y_norm

def filter_multi_assign(grouping):
    
      (id, df) = grouping
      xyz = id.split('-')[0:3] # xyz coord of multi-assigned reads
      # identify cells that reads are assigned to
      repeat_reads_cell_index = cell_center['cell_barcode'].isin(df['cell_barcode']) 
      repeat_reads_cell = cell_center.loc[repeat_reads_cell_index,:]
      # calculate closest cell (according to cell center)
      closest_index = closest_node(xyz,np.array(repeat_reads_cell.loc[:,['column', 'row', 'z_axis']]).tolist())[1] 
      selected_cell = repeat_reads_cell.iloc[closest_index,0] # barcode of closest cell
      # get indices of other reads to be filtered from farther cells
      filtered_read_idxs = df.index[np.logical_not(remain_reads.loc[df.index,'cell_barcode'] == selected_cell)].tolist() 
      return({id:filtered_read_idxs})

# Get figsize according to image size
def get_figsize(coords_df_tuned, scale=5):
      max_col_coord = coords_df_tuned['column_coord_obs'].max()
      max_row_coord = coords_df_tuned['row_coord_obs'].max()
      return([max_col_coord/100/scale * 2, max_row_coord/100/scale * 2])


def command_args():
    desc = "stitch reads"
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('-IXY', '--input_xy', type=str, required=True,help='XY')
    parser.add_argument('-ID', '--input_dir', type=str, required=True, help='the input_dir')
    parser.add_argument('-IO', '--input_orderlist', type=str, required=True, help='input_orderlist')
    parser.add_argument('-IS', '--input_segmentation', type=str, required=True, help='input_segmentation')
    parser.add_argument('-OC', '--output_cell_center', type=str, required=True, help='output_cell_center')
    parser.add_argument('-OD', '--output_dir', type=str, required=True, help='output_cell_center')
    parser.add_argument('-OR', '--output_remain_reads', type=str, required=True, help='output_remain_reads')
    parser.add_argument('-ITR', '--Tile_registered', type=str, required=True, help='Tile_registered')
    parser.add_argument('-IT', '--Tile', type=str, required=True, help='TileConfiguration.txt')
    parser.add_argument('-SM', '--seg_method', type=str, required=True, help='clustermap or watershed')
    args = parser.parse_args()

    return args

if __name__ == '__main__':
      args = command_args()
      alignment_thresh = 0.5
      img_c, img_r = [int(args.input_xy), int(args.input_xy)]
      data_dir = args.input_dir
      outputpath = args.output_dir
      os.makedirs(outputpath, exist_ok=True)
      orderlist_path = args.input_orderlist
      readspath = args.input_segmentation
      cell_center_path = args.output_cell_center
      remain_reads_path = args.output_remain_reads
      


      cell_barcode_min = 0
      middle_edge = 0
      remain_reads = pd.DataFrame({'gene_name':[],'spot_location_1':[],'spot_location_2':[],'spot_location_3':[],'gene':[],'is_noise':[],'cell_barcode':[],'raw_cell_barcode':[],'gridc_gridr_tilenum':[]})
      cell_center = pd.DataFrame({'cell_barcode':[],'column':[],'row':[],'z_axis':[],'raw_cell_barcode':[],'gridc_gridr_tilenum':[]})

      #### Read in tile coordinates and orderlist
      # Read coordinates
      obs_coords = get_coords(args.Tile_registered)
      exp_coords = get_coords(args.Tile)
      grid_order = get_coords(args.Tile, grid=True)

      # Format into dataframes
      coords_df = pd.DataFrame(obs_coords, columns=['tile','column_coord_obs','row_coord_obs'])
      coords_exp_df = pd.DataFrame(exp_coords, columns=['tile','column_coord_exp','row_coord_exp'])
      grid_df = pd.DataFrame(grid_order, columns=['tile', 'column_count', 'row_count'])

      # Convert tile numbers to integers
      coords_df['tile'] = coords_df['tile'].astype(int)
      coords_exp_df['tile'] = coords_exp_df['tile'].astype(int)
      grid_df['tile'] = grid_df['tile'].astype(int)

      # Merge coordinates data - keep the tile column for merging
      coords_df = coords_df.merge(
            coords_exp_df,
            on='tile'
      )
      coords_df = coords_df.merge(
            grid_df,
            on='tile'
      )
      
      # Save coordinates
      coords_df.to_csv(os.path.join(outputpath,'coords.csv'))

      # Zero-center (tune) registered coordinates
      print("Tuning coordinates...")
      coords_df_without_blank = coords_df.loc[coords_df['tile'] > 0,:]
      min_column, min_row = [np.min(coords_df_without_blank['column_coord_obs']), np.min(coords_df_without_blank['row_coord_obs'])]
      max_column, max_row = [np.max(coords_df_without_blank['column_coord_obs']), np.max(coords_df_without_blank['row_coord_obs'])]
      shape_column, shape_row = [max_column - min_column + img_c, max_row - min_row + img_r]
      
      coords_df_tuned = copy.deepcopy(coords_df)
      coords_df_tuned['column_coord_obs'] = coords_df['column_coord_obs'] - min_column
      coords_df_tuned['row_coord_obs'] = coords_df['row_coord_obs'] - min_row

      # Calculate grid dimensions based on actual coordinates
      grid_c = len(np.unique(coords_df_without_blank['column_coord_exp'] // (img_c * 0.9)))
      grid_r = len(np.unique(coords_df_without_blank['row_coord_exp'] // (img_r * 0.9)))

      # Save tuned coordinates
      coords_df_tuned.to_csv(os.path.join(outputpath,'tuned_coords.csv'))

      ### STITCH
      print("============STITCHING============")
      cell_barcode_min = 0
      remain_reads = pd.DataFrame({'gene_name':[],'spot_location_1':[],'spot_location_2':[],'spot_location_3':[],'gene':[],'is_noise':[],'cell_barcode':[],'raw_cell_barcode':[],'gridc_gridr_tilenum':[]})
      cell_center = pd.DataFrame({'cell_barcode':[],'column':[],'row':[],'z_axis':[],'raw_cell_barcode':[],'gridc_gridr_tilenum':[]})

      # Create mapping of tile numbers to grid positions
      tile_to_grid = {}
      for _, row in coords_df_tuned.iterrows():
            if row['tile'] > 0:  # Skip blank tiles
                  tile_num = int(row['tile'])
                  if tile_num <= 11:  # 第一列
                        grid_x = 0
                        grid_y = tile_num - 1
                  else:
                        grid_x = (tile_num - 1) // 11  # 计算列号
                        grid_y = (tile_num - 1) % 11   # 计算行号
                  tile_to_grid[tile_num] = (grid_x, grid_y)

      # 在主循环之前，先对tile进行排序
      sorted_tiles = sorted(coords_df_tuned['tile'].unique())
      # 移除0和负值
      sorted_tiles = [t for t in sorted_tiles if t > 0]

      # 在主循环之前添加调试信息
      print("\nAll available tiles:", sorted_tiles)
      print("\nGrid mapping:")
      for tile, (grid_x, grid_y) in tile_to_grid.items():
            print(f"Tile {tile}: grid position ({grid_x}, {grid_y})")

      # 修改主循环，添加更多调试信息
      processed_tiles = set()
      for tilenum in sorted_tiles:
            if tilenum <= 0:
                  continue
            
            if tilenum in processed_tiles:
                  print(f"Skipping already processed tile {tilenum}")
                  continue
            processed_tiles.add(tilenum)
            
            t_grid_c, t_grid_r = tile_to_grid[tilenum]
            print(f"\nProcessing tile {tilenum} at grid position ({t_grid_c}, {t_grid_r})")
            
            # Get median column coordinate for approx alignment
            median_col = coords_df_tuned[(coords_df_tuned.column_count == t_grid_c) & (coords_df_tuned.tile != 0)]['column_coord_obs']
            median_row = coords_df_tuned[(coords_df_tuned.row_count == t_grid_r) & (coords_df_tuned.tile != 0)]['row_coord_obs']
            
            if len(median_col) == 0 or len(median_row) == 0:
                  print(f"Warning: No median coordinates found for tile {tilenum}")
                  continue
            
            median_col_coord = np.median(median_col)
            median_row_coord = np.median(median_row)
            
            # Get tile coordinate and grid order information
            try:
                  order = coords_df_tuned.index[(coords_df_tuned['column_count']==t_grid_c) & (coords_df_tuned['row_count']==t_grid_r)][0]
            except IndexError:
                  print(f"Error: Could not find grid position for tile {tilenum}")
                  continue
            
            # Print alignment check information
            upper_left = coords_df_tuned.loc[order, ['column_coord_obs', 'row_coord_obs']]
            left_thresh = median_col_coord - (1+alignment_thresh)*img_c
            right_thresh = median_col_coord + (1+alignment_thresh)*img_c
            upper_thresh = median_row_coord - (1+alignment_thresh)*img_r
            lower_thresh = median_row_coord + (1+alignment_thresh)*img_r
            
            print(f"Alignment check for tile {tilenum}:")
            print(f"Position: {upper_left[0]:.2f}, {upper_left[1]:.2f}")
            print(f"Thresholds: {left_thresh:.2f} < x < {right_thresh:.2f}, {upper_thresh:.2f} < y < {lower_thresh:.2f}")
            
            tile_order = coords_df_tuned['tile'][order] # Tile number (blanks = 0)
            if pd.isna(tile_order) or tile_order == 0: # skip blanks
                  continue
            tile_order = int(tile_order)  # Convert to integer

            upper_left_new = copy.deepcopy(upper_left)

            # If either column or row alignment shifted more than 1.5x tile width/height away from median coordinate, throw out
            if upper_left[0] >= right_thresh or upper_left[0] <= left_thresh or upper_left[1] >= lower_thresh or upper_left[1] <= upper_thresh:
                  print(f"- Tile {tile_order} is aligned too far away from its expected position.")
                  print(f"\tTile coord: [{upper_left[0]}, {upper_left[1]}]. Median coord: [{median_col_coord}, {median_row_coord}]")
                  continue

            # Get tile read and cell center information
            dfpath = readspath + f'/Position{tile_order:03d}'
            print(f"\nProcessing tile {tile_order}:")
            print(f"Reading from path: {dfpath}")
            
            if not os.path.exists(os.path.join(dfpath, 'remain_reads.csv')):
                  print(f"- Tile {tile_order}: Reads file does not exist. [{t_grid_c},{t_grid_r}]")
                  continue
                  
            remain_reads_t = pd.read_csv(os.path.join(dfpath,'remain_reads_raw.csv'),index_col=0)
            cell_center_t = pd.read_csv(os.path.join(dfpath,'cell_center.csv'),index_col=0)
            
            print(f"Initial reads count: {remain_reads_t.shape[0]}")
            print(f"Initial cells count: {cell_center_t.shape[0]}")

            if args.seg_method == 'clustermap':
                  remain_reads_t.rename(columns = {'clustermap':'cell_barcode'}, inplace = True)
            elif args.seg_method == 'watershed':
                  remain_reads_t.rename(
                  columns = {
                    'Gene':'gene', 
                    'x':'spot_location_1',
                    'y':'spot_location_2',
                    'z':'spot_location_3'
                  }, 
                  inplace=True)
                  cell_center_t.rename(
                  columns = {
                    'x':'column',
                    'y':'row'
                  },
                  inplace=True)

            # Format reads data and add in grid/order information   
            remain_reads_t['gridc_gridr_tilenum'] = str(t_grid_c)+","+str(t_grid_r)+","+str(tile_order)
            cell_center_t['gridc_gridr_tilenum'] = str(t_grid_c)+","+str(t_grid_r)+","+str(tile_order)

            # Adjust read coordinates and cell center coordinates using observed upper left tile coordinate
            remain_reads_t['spot_location_1'] = remain_reads_t['spot_location_1'] + upper_left[0]# col
            cell_center_t['column'] = cell_center_t['column']  + upper_left[0]
            remain_reads_t['spot_location_2'] = remain_reads_t['spot_location_2'] + upper_left[1]# col
            cell_center_t['row'] = cell_center_t['row']  + upper_left[1]

            # Keep tile-by-tile barcodes as raw barcodes, cell_barcode is cumulative
            remain_reads_t['raw_cell_barcode'] = remain_reads_t['cell_barcode']
            cell_center_t['raw_cell_barcode'] = cell_center_t['cell_barcode']
            # Process reads (raw_cell_barcode == -1) should keep cell_barcode as 0, not cumulative
            process_mask = remain_reads_t['cell_barcode'] == -1
            remain_reads_t.loc[~process_mask, 'cell_barcode'] = remain_reads_t.loc[~process_mask, 'cell_barcode'] + cell_barcode_min + 1
            remain_reads_t.loc[process_mask, 'cell_barcode'] = 0  # Process reads keep cell_barcode as 0
            cell_center_t['cell_barcode'] = cell_center_t['cell_barcode'] + cell_barcode_min + 1

            # 计算当前tile的有效区域边界（去除overlap），类似create_tile_config.py的方法
            start_x_norm, end_x_norm, start_y_norm, end_y_norm = calculate_valid_region_bounds(
                  coords_df_tuned, t_grid_c, t_grid_r, upper_left, img_c, img_r
            )
            
            print(f"Valid region bounds for tile {tile_order}:")
            print(f"  X: [{start_x_norm}, {end_x_norm})")
            print(f"  Y: [{start_y_norm}, {end_y_norm})")
            
            # 使用有效区域边界过滤cells和reads（类似reads_assignment.py的方法）
            # 注意：start_x_norm等是相对于tile左上角的局部坐标
            # 但cell_center_t和remain_reads_t的坐标已经转换为全局坐标（加上了upper_left）
            # 所以需要将全局坐标转换回局部坐标来比较
            
            # 计算全局坐标下的有效区域边界
            start_x_global = upper_left[0] + start_x_norm
            end_x_global = upper_left[0] + end_x_norm
            start_y_global = upper_left[1] + start_y_norm
            end_y_global = upper_left[1] + end_y_norm
            
            # 过滤新tile的cells：只保留在有效区域内的cells（类似reads_assignment.py第130-131行）
            previous_cell_t_count = len(cell_center_t)
            cell_center_t = cell_center_t[
                  (cell_center_t['column'] >= start_x_global) & 
                  (cell_center_t['column'] < end_x_global) &
                  (cell_center_t['row'] >= start_y_global) & 
                  (cell_center_t['row'] < end_y_global)
            ]
            print(f"Cells filtered: {previous_cell_t_count} -> {len(cell_center_t)}")
            
            # 获取保留的cells的barcode列表
            valid_cell_barcodes = set(cell_center_t['cell_barcode'].values)
            
            # 过滤新tile的reads（类似reads_assignment.py第134-139行）
            # 保留：细胞内的（is_noise == 0 且 raw_cell_barcode != -1）、process的（raw_cell_barcode == -1）
            # 不保留：noise的（is_noise == -1）
            previous_reads_t_count = len(remain_reads_t)
            
            # 先过滤掉noise reads（is_noise == -1）
            remain_reads_t = remain_reads_t[remain_reads_t['is_noise'] != -1]
            
            # 分离细胞内的reads和process reads
            # process reads：raw_cell_barcode == -1（不管is_noise的值，因为process点不会在cellcenter里）
            reads_process = remain_reads_t[remain_reads_t['raw_cell_barcode'] == -1]
            
            # 细胞内的reads：is_noise == 0 且 raw_cell_barcode != -1
            reads_within_cells = remain_reads_t[
                  (remain_reads_t['is_noise'] == 0) & 
                  (remain_reads_t['raw_cell_barcode'] != -1) &
                  (remain_reads_t['cell_barcode'].isin(valid_cell_barcodes))  # 只保留cells在有效区域内的
            ]
            
            # 对process reads按坐标过滤（去除overlap区域的重复）
            reads_process_filtered = reads_process[
                  (reads_process['spot_location_1'] >= start_x_global) & 
                  (reads_process['spot_location_1'] < end_x_global) &
                  (reads_process['spot_location_2'] >= start_y_global) & 
                  (reads_process['spot_location_2'] < end_y_global)
            ]
            
            # 合并过滤后的reads：细胞内的reads + 过滤后的process reads
            remain_reads_t = pd.concat([reads_within_cells, reads_process_filtered])
            print(f"Reads filtered: {previous_reads_t_count} -> {len(remain_reads_t)}")
            print(f"  - Reads within cells (is_noise==0, raw_cell_barcode!=-1): {len(reads_within_cells)}")
            print(f"  - Process reads (raw_cell_barcode==-1): {len(reads_process)} -> {len(reads_process_filtered)}")
            print(f"  - Noise reads (is_noise==-1) removed")

            ## append
            cell_center = pd.concat([cell_center, cell_center_t], ignore_index=True)
            remain_reads = pd.concat([remain_reads, remain_reads_t], ignore_index=True)
            if cell_center_t.shape[0] > 0:
                  cell_barcode_min = np.max(cell_center_t['cell_barcode']) + 1

            # 在最终合并数据之前添加调试信息
            print(f"\nFinal merge for tile {tile_order}:")
            print(f"Current total reads: {remain_reads.shape[0]}")
            print(f"Current total cells: {cell_center.shape[0]}")
            print(f"Adding reads: {remain_reads_t.shape[0]}")
            print(f"Adding cells: {cell_center_t.shape[0]}")

      print(f"\tTotal Reads: {remain_reads.shape[0]} | Total Cells: {cell_center.shape[0]}")

      ################################ polish after stitch ################################
      print("============FILTERING============")
      print("Finding multi-assigned reads...")
      # filter the repeated reads
      remain_reads = remain_reads.drop_duplicates(subset = None, keep = 'first')
      cell_center.reset_index(inplace = True,drop = True)
      remain_reads.reset_index(inplace = True,drop = True)
      remain_reads.rename(columns = {'spot_location_1':'column', 'spot_location_2':'row','spot_location_3':'z'}, inplace = True)
      
      cell_center.rename(columns = {'z_axis':'z'}, inplace = True)

      remain_reads = remain_reads.astype(
      {'column':'int', 'row':'int', 'z':'int', 'cell_barcode':'int', 'raw_cell_barcode':'int'}
            )
      cell_center = cell_center.astype(
      {'cell_barcode':'int', 'column':'int', 'row':'int', 'z':'int', 'raw_cell_barcode':'int'}
            )
      #remain_reads = remain_reads.drop(['gene_name', 'is_noise'], axis=1)
      
      

      print("Read counts after filtering multi-assigned reads: " + str(remain_reads.shape[0]))
      cell_center.to_csv(cell_center_path)
      remain_reads.to_csv(remain_reads_path)

      plt.style.use('dark_background')

      plt.figure(figsize=get_figsize(coords_df_tuned, scale=5))
      plt.subplot(2,2,1)
      plt.title('Reads with cell centers')
      #plt.scatter(remain_reads.loc[:,'column'],shape_row - remain_reads.loc[:,'row'],s = 0.1,alpha = 0.2,color=remain_reads['cell_barcode'])
      plt.scatter(remain_reads.loc[:,'column'],shape_row - remain_reads.loc[:,'row'],s = 0.1,alpha = 0.8,c=pd.Categorical(np.array(remain_reads['raw_cell_barcode'])).codes, cmap= matplotlib.colors.ListedColormap ( np.random.rand ( 256,3)))
      plt.scatter(cell_center.loc[:,'column'],shape_row - cell_center.loc[:,'row'],s = 1,c='red',alpha = 1)
      plt.axis('off')

      plt.subplot(2,2,2)
      plt.title('Reads with cell centers and tile order')
      #plt.scatter(remain_reads.loc[:,'column'],shape_row - remain_reads.loc[:,'row'],s = 0.1,alpha = 0.2)
      plt.scatter(remain_reads.loc[:,'column'],shape_row - remain_reads.loc[:,'row'],s = 0.1,alpha = 0.8,c=pd.Categorical(np.array(remain_reads['raw_cell_barcode'])).codes, cmap= matplotlib.colors.ListedColormap ( np.random.rand ( 256,3)))
      plt.scatter(cell_center.loc[:,'column'],shape_row - cell_center.loc[:,'row'],s = 1,c='red',alpha = 1)
      plt.axis('off')
      y_reverse = True
      list_t = ['column_coord_obs','row_coord_obs','tile']
      coords_df = coords_df_tuned.copy()
      idx_t = coords_df[list_t[2]] != 0
      coords0 = np.array(coords_df.loc[idx_t,list_t])
      if y_reverse:
            coords0[:,1] = coords0[:,1].max() - coords0[:,1] 
      plt.scatter(x=coords0[:,0],y=coords0[:,1],c=coords0[:,2])
      for i in range(coords0.shape[0]):
            plt.text(x=coords0[i,0],y=coords0[i,1],s=coords0[i,2],fontdict=dict(fontsize=20))

      plt.subplot(2,2,3)
      plt.title('Cell centers')
      plt.scatter(cell_center.loc[:,'column'],shape_row - cell_center.loc[:,'row'],s = 10,c='red',alpha = 0.8)
      plt.axis('off')

      plt.subplot(2,2,4)
      plt.title('Cell centers and tile order')
      plt.scatter(cell_center.loc[:,'column'],shape_row - cell_center.loc[:,'row'],s = 10,c='red',alpha = 0.8)
      plt.scatter(x=coords0[:,0],y=coords0[:,1],c=coords0[:,2])
      for i in range(coords0.shape[0]):
            plt.text(x=coords0[i,0],y=coords0[i,1],s=coords0[i,2],fontdict=dict(fontsize=20))
      plt.axis('off')

      plt.tight_layout()

      plt.savefig(os.path.join(outputpath,'cell_reads_profile.png'))

# 修改重叠区域处理逻辑
def process_overlap_region(cell_center_old, cell_center_new, overlap_start, overlap_end, axis='column'):
    """
    处理重叠区域的细胞
    cell_center_old: 已存在的细胞数据
    cell_center_new: 新tile的细胞数据
    overlap_start, overlap_end: 重叠区域的起止位置
    axis: 'column'为水平重叠，'row'为垂直重叠
    """
    overlap_middle = (overlap_start + overlap_end) / 2
    cells_to_drop_old = []
    cells_to_drop_new = []
    
    # 找出重叠区域内的所有细胞
    old_cells = cell_center_old[(cell_center_old[axis] >= overlap_start) & 
                               (cell_center_old[axis] <= overlap_end)]
    new_cells = cell_center_new[(cell_center_new[axis] >= overlap_start) & 
                               (cell_center_new[axis] <= overlap_end)]
    
    # 对每个重叠区域的细胞，选择保留距离最近的
    for _, old_cell in old_cells.iterrows():
        for _, new_cell in new_cells.iterrows():
            # 计算两个细胞的距离
            dist = np.sqrt((old_cell['column'] - new_cell['column'])**2 + 
                         (old_cell['row'] - new_cell['row'])**2)
            
            if dist < img_c * 0.1:  # 如果细胞足够近（比如10%的tile大小）
                # 根据到重叠中线的距离决定保留哪个
                old_dist = abs(old_cell[axis] - overlap_middle)
                new_dist = abs(new_cell[axis] - overlap_middle)
                
                if old_dist > new_dist:
                    cells_to_drop_old.append(old_cell['cell_barcode'])
                else:
                    cells_to_drop_new.append(new_cell['cell_barcode'])
    
    return cells_to_drop_old, cells_to_drop_new

