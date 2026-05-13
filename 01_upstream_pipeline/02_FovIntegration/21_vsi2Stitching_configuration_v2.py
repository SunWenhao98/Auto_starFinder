from pathlib import Path
import logging
import bioformats as bf
import javabridge as jb
import argparse
import pandas as pd
import numpy as np
import re
import time
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Rectangle
import seaborn as sns

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ================= Configuration =================
# PIXEL_SIZE_UM = 0.1083333
# INVERT_Y = False 
# ===============================================

def extract_index(f, pattern):
    match = re.search(pattern, f.name)
    return int(match.group(1)) if match else float('inf')

def get_vsi_position(path: str):
    xml_data = bf.get_omexml_metadata(path)
    omexml = bf.OMEXML(xml_data)
    pixels = omexml.image(0).Pixels
    phys_x = pixels.plane(0).PositionX
    phys_y = pixels.plane(0).PositionY
    return phys_x, phys_y

# def plot_tile_positions(df, tile_size_px, non_overlap_len, output_dir, show_labels=True):
#     """
#     绘制tile位置图
    
#     Args:
#         df: 包含tile位置信息的DataFrame
#         tile_size_px: tile的边长（像素）
#         non_overlap_len: 非重叠区域长度
#         output_dir: 输出目录
#         show_labels: 是否显示标签
#     """
#     # 创建图形
#     fig, ax = plt.subplots(1, 2, figsize=(30, 8))
    
#     # 设置统一的样式
#     plt.style.use('seaborn-v0_8-darkgrid')
    
#     # 获取位置范围
#     min_x = df['pos_x_px'].min()
#     max_x = df['pos_x_px'].max()
#     min_y = df['pos_y_px'].min()
#     max_y = df['pos_y_px'].max()
    
#     # 计算绘图范围
#     padding = tile_size_px * 0.1
#     x_range = max_x - min_x + tile_size_px
#     y_range = max_y - min_y + tile_size_px
    
#     # ========== 子图1: Tile布局图 ==========
#     ax[0].set_title('Tile Layout Visualization', fontsize=14, fontweight='bold')
#     ax[0].set_xlabel('X Position (pixels)', fontsize=12)
#     ax[0].set_ylabel('Y Position (pixels)', fontsize=12)
#     ax[0].set_aspect('equal')
    
#     # 设置坐标轴范围
#     ax[0].set_xlim(min_x - padding, max_x + tile_size_px + padding)
#     # ax[0].set_ylim(min_y - padding, max_y + tile_size_px + padding)
#     max_y_value = df['pos_y_px'].max() + tile_size_px
#     ax[0].set_ylim(max_y_value + padding, min_y - padding)
    
#     # 绘制每个tile
#     colors = plt.cm.tab20c(np.linspace(0, 1, len(df)))
    
#     for idx, row in df.iterrows():

#         # 获取基础颜色
#         base_color = colors[idx % len(colors)]
        
#         # 创建半透明的浅色版本
#         facecolor = list(base_color)
#         facecolor[3] = 0.3  # 设置透明度为0.3

#         # 绘制tile矩形
#         rect = Rectangle(
#             (row['pos_x_px'], row['pos_y_px']),
#             tile_size_px, tile_size_px,
#             linewidth=1.5,
#             # edgecolor=colors[idx % len(colors)],
#             # facecolor=colors[idx % len(colors)] + np.array([1, 1, 1, 0]) * 0.7,  # 半透明
#             # alpha=0.6,
#             edgecolor=base_color,  # 边缘用原色
#             facecolor=facecolor,   # 填充用半透明色
#             label=f"Pos{int(row['real_id']):03d}"
#         )
#         ax[0].add_patch(rect)
        
#         # 在tile中心添加标签
#         if show_labels:
#             center_x = row['pos_x_px'] + tile_size_px / 2
#             center_y = row['pos_y_px'] + tile_size_px / 2
#             ax[0].text(
#                 center_x, center_y,
#                 f"{int(row['real_id'])}",
#                 ha='center', va='center',
#                 fontsize=8, fontweight='bold',
#                 color='black',
#                 bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7, edgecolor='none')
#             )
    
#     # 添加网格
#     ax[0].grid(True, alpha=0.3, linestyle='--')
    
#     # 添加图例（只显示前10个，避免过于拥挤）
#     if len(df) <= 20:
#         handles, labels = ax[0].get_legend_handles_labels()
#         ax[0].legend(handles[:min(10, len(handles))], labels[:min(10, len(labels))], 
#                      loc='upper right', fontsize=8, title='Tile IDs')
    
#     # 添加统计信息
#     stats_text = f'Total Tiles: {len(df)}\n'
#     stats_text += f'X Range: {x_range:.1f} px\n'
#     stats_text += f'Y Range: {y_range:.1f} px\n'
#     stats_text += f'Tile Size: {tile_size_px} px\n'
#     stats_text += f'Overlap: {tile_size_px - non_overlap_len:.1f} px'
    
#     ax[0].text(
#         0.02, 0.98, stats_text,
#         transform=ax[0].transAxes,
#         fontsize=9,
#         verticalalignment='top',
#         bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8)
#     )
    
#     # ========== 子图2: Tile分布散点图 ==========
#     ax[1].set_title('Tile Center Distribution', fontsize=14, fontweight='bold')
#     ax[1].set_xlabel('X Center (pixels)', fontsize=12)
#     ax[1].set_ylabel('Y Center (pixels)', fontsize=12)
    
#     # 计算tile中心点
#     df['center_x'] = df['pos_x_px'] + tile_size_px / 2
#     df['center_y'] = df['pos_y_px'] + tile_size_px / 2
    
#     # 绘制散点图
#     scatter = ax[1].scatter(
#         df['center_x'], df['center_y'],
#         c=df['real_id'], cmap='viridis',
#         s=100, alpha=0.8, edgecolors='black', linewidth=1
#     )
    
#     # 添加颜色条
#     cbar = plt.colorbar(scatter, ax=ax[1])
#     cbar.set_label('Tile ID', fontsize=10)
    
#     # 在点上添加ID标签
#     if show_labels and len(df) <= 50:  # 如果tile太多，标签会太密
#         for _, row in df.iterrows():
#             ax[1].text(
#                 row['center_x'], row['center_y'],
#                 f"{int(row['real_id'])}",
#                 ha='center', va='center',
#                 fontsize=7, fontweight='bold',
#                 color='white'
#             )
    
#     # 添加网格
#     ax[1].grid(True, alpha=0.3, linestyle='--')
    
#     # 添加密度等高线
#     if len(df) > 4:  # 需要足够的数据点
#         from scipy import stats
#         try:
#             x = df['center_x']
#             y = df['center_y']
#             xmin, xmax = x.min(), x.max()
#             ymin, ymax = y.min(), y.max()
#             X, Y = np.mgrid[xmin:xmax:100j, ymin:ymax:100j]
#             positions = np.vstack([X.ravel(), Y.ravel()])
#             values = np.vstack([x, y])
#             kernel = stats.gaussian_kde(values)
#             Z = np.reshape(kernel(positions).T, X.shape)
#             ax[1].contour(X, Y, Z, colors='black', alpha=0.3, linewidths=1)
#         except:
#             pass
    
#     # 添加统计信息
#     ax[1].text(
#         0.02, 0.98,
#         f'Mean Spacing: {non_overlap_len:.1f} px\n'
#         f'Std Dev X: {df["center_x"].std():.1f} px\n'
#         f'Std Dev Y: {df["center_y"].std():.1f} px',
#         transform=ax[1].transAxes,
#         fontsize=9,
#         verticalalignment='top',
#         bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8)
#     )
    
#     # 调整布局
#     plt.tight_layout()
    
#     # 保存图片
#     output_path = output_dir / "tile_layout_visualization.png"
#     plt.savefig(output_path, dpi=300, bbox_inches='tight')
#     logging.info(f"Tile visualization saved to: {output_path}")
    
#     # 另外保存一个高分辨率版本用于打印
#     output_path_highres = output_dir / "tile_layout_visualization_highres.png"
#     plt.savefig(output_path_highres, dpi=600, bbox_inches='tight')
    
#     # 显示图形
#     plt.show()
    
#     return fig

def plot_tile_positions(df, tile_size_px, non_overlap_len, output_dir, show_labels=True):
    """
    绘制tile位置图（拆分为两个独立的图形）
    
    Args:
        df: 包含tile位置信息的DataFrame
        tile_size_px: tile的边长（像素）
        non_overlap_len: 非重叠区域长度
        output_dir: 输出目录
        show_labels: 是否显示标签
    """
    if len(df) == 0:
        logging.warning("No data to plot")
        return None, None
    
    # 计算tile中心点
    df['center_x'] = df['pos_x_px'] + tile_size_px / 2
    df['center_y'] = df['pos_y_px'] + tile_size_px / 2
    
    # 获取位置范围
    min_x = df['pos_x_px'].min()
    max_x = df['pos_x_px'].max()
    min_y = df['pos_y_px'].min()
    max_y = df['pos_y_px'].max()
    
    # 计算范围
    x_range = max_x - min_x + tile_size_px
    y_range = max_y - min_y + tile_size_px
    padding = tile_size_px * 0.1
    
    # ========== 图1: Tile布局图 ==========
    fig1, ax1 = plt.subplots(figsize=(20, 16))
    plt.style.use('seaborn-v0_8-darkgrid')
    
    ax1.set_title('Tile Layout Visualization', fontsize=16, fontweight='bold', pad=20)
    ax1.set_xlabel('X Position (pixels)', fontsize=12)
    ax1.set_ylabel('Y Position (pixels)', fontsize=12)
    ax1.set_aspect('equal')
    
    # 设置坐标轴范围（图像坐标系：原点在左上角）
    ax1.set_xlim(min_x - padding, max_x + tile_size_px + padding)
    max_y_value = df['pos_y_px'].max() + tile_size_px
    ax1.set_ylim(max_y_value + padding, min_y - padding)
    
    # 生成颜色
    colors = plt.cm.tab20c(np.linspace(0, 1, min(len(df), 20)))
    
    # 绘制每个tile
    for idx, row in df.iterrows():
        base_color = colors[idx % len(colors)]
        
        # # 创建半透明填充色
        # facecolor = list(base_color)
        # facecolor[3] = 0.3
        
        # 创建半透明的浅色版本
        facecolor = list(base_color)
        facecolor[3] = 0.3  # 设置透明度为0.3
        
        # 绘制tile矩形
        rect = Rectangle(
            (row['pos_x_px'], row['pos_y_px']),
            tile_size_px, tile_size_px,
            linewidth=1.5,
            edgecolor=base_color,
            facecolor=facecolor,
            label=f"Pos{int(row['real_id']):03d}"
        )
        ax1.add_patch(rect)
        
        # 在tile中心添加标签
        if show_labels:
            center_x = row['pos_x_px'] + tile_size_px / 2
            center_y = row['pos_y_px'] + tile_size_px / 2
            
            # 根据背景色调整文字颜色
            text_color = 'black'
            
            ax1.text(
                center_x, center_y,
                f"{int(row['real_id'])}",
                ha='center', va='center',
                fontsize=9, fontweight='bold',
                color=text_color,
                bbox=dict(
                    boxstyle='round,pad=0.3',
                    facecolor='white',
                    alpha=0.8,
                    edgecolor='none',
                    linewidth=0.5
                )
            )
    
    # 添加网格
    ax1.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
    
    # 添加图例（优化显示）
    if len(df) <= 30:
        handles, labels = ax1.get_legend_handles_labels()
        # 去重
        unique_dict = {}
        for h, l in zip(handles, labels):
            if l not in unique_dict:
                unique_dict[l] = h
        
        if unique_dict:
            unique_labels = list(unique_dict.keys())
            unique_handles = list(unique_dict.values())
            
            # 分列显示图例
            n_cols = 3 if len(unique_labels) > 15 else 2
            ax1.legend(
                unique_handles[:min(20, len(unique_handles))],
                unique_labels[:min(20, len(unique_labels))],
                loc='upper right',
                fontsize=8,
                title='Tile IDs',
                ncol=n_cols,
                title_fontsize=9,
                framealpha=0.9
            )
    
    # 添加统计信息框
    stats_text = f'Total Tiles: {len(df)}\n'
    stats_text += f'X Range: {x_range:.1f} px\n'
    stats_text += f'Y Range: {y_range:.1f} px\n'
    stats_text += f'Tile Size: {tile_size_px} px\n'
    stats_text += f'Overlap: {tile_size_px - non_overlap_len:.1f} px\n'
    stats_text += f'Coordinate: Image (top-left)'
    
    ax1.text(
        0.02, 0.98, stats_text,
        transform=ax1.transAxes,
        fontsize=10,
        verticalalignment='top',
        bbox=dict(
            boxstyle='round',
            facecolor='wheat',
            alpha=0.85,
            edgecolor='brown',
            linewidth=1
        )
    )
    
    # 调整布局
    plt.tight_layout()
    
    # 保存图1
    output_path1 = output_dir / "tile_layout.png"
    fig1.savefig(output_path1, dpi=300, bbox_inches='tight', facecolor='white')
    logging.info(f"Tile layout saved to: {output_path1}")
    
    # ========== 图2: Tile中心分布散点图 ==========
    fig2, ax2 = plt.subplots(figsize=(20, 12))
    plt.style.use('seaborn-v0_8-darkgrid')
    
    ax2.set_title('Tile Center Distribution', fontsize=16, fontweight='bold', pad=20)
    ax2.set_xlabel('X Center (pixels)', fontsize=12)
    ax2.set_ylabel('Y Center (pixels)', fontsize=12)
    
    # 图像坐标系：反转y轴
    ax2.invert_yaxis()
    
    # 计算散点大小（根据tile数量自适应）
    if len(df) < 20:
        scatter_size = 150
    elif len(df) < 50:
        scatter_size = 120
    elif len(df) < 100:
        scatter_size = 80
    else:
        scatter_size = 50
    
    # 绘制散点图
    scatter = ax2.scatter(
        df['center_x'], df['center_y'],
        c=df['real_id'],
        cmap='viridis',
        s=scatter_size,
        alpha=0.8,
        edgecolors='black',
        linewidth=1,
        zorder=3
    )
    
    # 添加颜色条
    cbar = plt.colorbar(scatter, ax=ax2, pad=0.02)
    cbar.set_label('Tile ID', fontsize=11)
    cbar.ax.tick_params(labelsize=9)
    
    # 在点上添加ID标签
    if show_labels:
        max_labels = 50  # 最多显示50个标签
        label_indices = np.linspace(0, len(df)-1, min(max_labels, len(df)), dtype=int)
        
        for idx in label_indices:
            row = df.iloc[idx]
            ax2.text(
                row['center_x'], row['center_y'],
                f"{int(row['real_id'])}",
                ha='center', va='center',
                fontsize=8 if len(df) < 30 else 7,
                fontweight='bold',
                color='white',
                bbox=dict(
                    boxstyle='round,pad=0.2',
                    facecolor='black',
                    alpha=0.5,
                    edgecolor='none'
                ),
                zorder=4
            )
    
    # 添加网格
    ax2.grid(True, alpha=0.3, linestyle='--', linewidth=0.5, zorder=1)
    
    # 添加密度等高线
    if len(df) > 4:
        from scipy import stats
        try:
            x = df['center_x'].values
            y = df['center_y'].values
            
            if len(np.unique(x)) > 1 and len(np.unique(y)) > 1:
                xmin, xmax = x.min(), x.max()
                ymin, ymax = y.min(), y.max()
                
                # 扩展边界
                x_padding = (xmax - xmin) * 0.1
                y_padding = (ymax - ymin) * 0.1
                
                X, Y = np.mgrid[
                    xmin-x_padding:xmax+x_padding:100j,
                    ymin-y_padding:ymax+y_padding:100j
                ]
                
                positions = np.vstack([X.ravel(), Y.ravel()])
                values = np.vstack([x, y])
                kernel = stats.gaussian_kde(values)
                Z = np.reshape(kernel(positions).T, X.shape)
                
                # 绘制等高线
                contour = ax2.contour(
                    X, Y, Z,
                    colors='darkred',
                    alpha=0.4,
                    linewidths=1.5,
                    linestyles='-',
                    zorder=2
                )
                
                # 添加等高线标签
                ax2.clabel(contour, inline=True, fontsize=8, fmt='%.2f')
                
        except Exception as e:
            logging.debug(f"Could not generate density contour: {e}")
    
    # 添加统计信息框
    stats_text2 = f'Total Tiles: {len(df)}\n'
    stats_text2 += f'Mean X: {df["center_x"].mean():.1f} px\n'
    stats_text2 += f'Mean Y: {df["center_y"].mean():.1f} px\n'
    stats_text2 += f'Std X: {df["center_x"].std():.1f} px\n'
    stats_text2 += f'Std Y: {df["center_y"].std():.1f} px\n'
    stats_text2 += f'Expected Spacing: {non_overlap_len:.1f} px'
    
    ax2.text(
        0.02, 0.98, stats_text2,
        transform=ax2.transAxes,
        fontsize=10,
        verticalalignment='top',
        bbox=dict(
            boxstyle='round',
            facecolor='lightblue',
            alpha=0.85,
            edgecolor='navy',
            linewidth=1
        )
    )
    
    # 调整布局
    plt.tight_layout()
    
    # 保存图2
    output_path2 = output_dir / "tile_centers_distribution.png"
    fig2.savefig(output_path2, dpi=300, bbox_inches='tight', facecolor='white')
    logging.info(f"Tile centers distribution saved to: {output_path2}")
    
    # 保存高分辨率版本
    output_path1_high = output_dir / "tile_layout_highres.png"
    output_path2_high = output_dir / "tile_centers_distribution_highres.png"
    
    fig1.savefig(output_path1_high, dpi=600, bbox_inches='tight', facecolor='white')
    fig2.savefig(output_path2_high, dpi=600, bbox_inches='tight', facecolor='white')
    
    # 显示图形
    plt.show()
    
    # 关闭图形以释放内存
    plt.close(fig1)
    plt.close(fig2)
    
    return output_path1, output_path2

def generate_tile_summary_csv(df, tile_size_px, output_dir):
    """
    生成tile信息的CSV总结文件
    """
    # 计算额外信息
    df['center_x_px'] = df['pos_x_px'] + tile_size_px / 2
    df['center_y_px'] = df['pos_y_px'] + tile_size_px / 2
    df['width_px'] = tile_size_px
    df['height_px'] = tile_size_px
    
    # 排序
    df = df.sort_values('real_id')
    
    # 保存CSV
    csv_path = output_dir / "tile_summary.csv"
    df.to_csv(csv_path, index=False)
    logging.info(f"Tile summary saved to: {csv_path}")
    
    return df

def main():
    parser = argparse.ArgumentParser(description="VSI to TileConfiguration (ID from filename)")
    parser.add_argument('--input_dir', '-i', type=Path, required=False, 
                        default=Path("/mnt/swh_c2/ZXM_DATA_1_disk/250615-MB-seqF4-2"),
                        help='The path to the input file.')
    parser.add_argument('--output_dir','-o', type=Path, required=False, 
                        default=Path("/media/zenglab/result/swh/07_Olympus_TEST/01_OlympusTest/01_data/round002"),
                        help='The path to the output directory.')
    parser.add_argument('--match_string', '-m', type=str, required=False, 
                        default="C1", 
                        help='The string to match the input file.')
    
    parser.add_argument('--pixel_size_um', '-p', type=float, required=False, default=0.1083333,
                        help='The pixel size in microns.')
    parser.add_argument('--image_xy', '-xy', type=int, required=False, default=2304,
                        help='The image size in pixels in x and y direction.')
    parser.add_argument('--overlap_ratio', '-r', type=float, required=False, default=0.1,
                        help='The overlap ratio between adjacent tiles.')
    parser.add_argument('--invert_y', '-iy', action='store_true', required=False, default=False,
                        help='Whether to invert the y-axis.')
    
    args = parser.parse_args()

    input_dir = args.input_dir
    output_dir = args.output_dir
    match_string = args.match_string

    PIXEL_SIZE_UM = args.pixel_size_um
    image_xy = args.image_xy
    non_overlap_len = image_xy * (1 - args.overlap_ratio)
    INVERT_Y = args.invert_y 
    
    output_dir.mkdir(parents=True, exist_ok=True)

    files = list(input_dir.glob(f"*{match_string}*.vsi"))
    pattern = fr'{re.escape(match_string)}-(\d+)'
    files = sorted(files, key=lambda f: extract_index(f, pattern))
    logging.info(f"File scan complete. Found {len(files)} files.")

    jb.start_vm(class_path=bf.JARS, run_headless=True, args=['-Dlog4j2.simplelogStatusLogger.level=off'])
    jb.static_call("loci/common/DebugTools", "enableLogging", "(Ljava/lang/String;)Z", "ERROR")
    print("Java VM started successfully")
    try:
        t0 = time.time()
        tiles_data = []
        for idx, f in enumerate(files):
            print(f"\rProcessing: [{idx+1}/{len(files)}] {f.name}", end='', flush=True)
            
            try:
                real_id = extract_index(f, pattern)
                phys_x, phys_y = get_vsi_position(str(f))
                tiles_data.append({
                    'original_name': f.name,
                    'real_id': int(real_id),
                    'phys_x': phys_x,
                    'phys_y': phys_y
                })
                
            except Exception as e:
                logging.error(f"\nFailed to read file {f.name}: {e}")

        print("")

        if not tiles_data:
            logging.error("No valid data extracted.")
            return

        df = pd.DataFrame(tiles_data)
        
        min_x = df['phys_x'].min()
        min_y = df['phys_y'].min()
        max_y = df['phys_y'].max()

        df['pos_x_px'] = (df['phys_x'] - min_x) / PIXEL_SIZE_UM
        if INVERT_Y:
            df['pos_y_px'] = (max_y - df['phys_y']) / PIXEL_SIZE_UM
        else:
            df['pos_y_px'] = (df['phys_y'] - min_y) / PIXEL_SIZE_UM

        # 生成TileConfiguration.txt
        output_config_path = output_dir / "TileConfiguration.txt"
        with open(output_config_path, 'w') as f:
            f.write("# Define the number of dimensions we are working on\n")
            f.write("dim = 3\n\n")
            f.write("# Define the image coordinates\n")
            
            for _, row in df.iterrows():
                fname = f"Position{int(row['real_id']):03d}.tif"
                x = row['pos_x_px']
                y = row['pos_y_px']
                f.write(f"{fname}; ; ({x:.2f}, {y:.2f}, 0.0)\n")

        logging.info(f"Generation complete: {output_config_path}")
        
        # ========== TODO部分：绘制tile位置图 ==========
        if len(df) > 0:
            logging.info("Generating tile visualization...")
            
            # 生成tile布局图
            fig = plot_tile_positions(
                df=df,
                tile_size_px=image_xy,
                non_overlap_len=non_overlap_len,
                output_dir=output_dir,
                show_labels=True
            )
            
            # 生成CSV总结文件
            df_summary = generate_tile_summary_csv(
                df=df,
                tile_size_px=image_xy,
                output_dir=output_dir
            )
            
            # 打印统计信息
            logging.info("\n" + "="*50)
            logging.info("TILE POSITION ANALYSIS SUMMARY")
            logging.info("="*50)
            logging.info(f"Total tiles processed: {len(df)}")
            logging.info(f"X position range: {df['pos_x_px'].min():.1f} to {df['pos_x_px'].max():.1f} px")
            logging.info(f"Y position range: {df['pos_y_px'].min():.1f} to {df['pos_y_px'].max():.1f} px")
            logging.info(f"Tile size: {image_xy} px")
            logging.info(f"Non-overlap length: {non_overlap_len:.1f} px")
            logging.info(f"Overlap length: {image_xy - non_overlap_len:.1f} px")
            logging.info(f"Overlap ratio: {args.overlap_ratio*100:.1f}%")
            
            # 计算tile之间的间距
            if len(df) > 1:
                # 按X坐标排序
                df_sorted_x = df.sort_values('pos_x_px')
                x_spacings = np.diff(df_sorted_x['pos_x_px'].values)
                
                # 按Y坐标排序
                df_sorted_y = df.sort_values('pos_y_px')
                y_spacings = np.diff(df_sorted_y['pos_y_px'].values)
                
                logging.info(f"Average X spacing: {np.mean(x_spacings):.1f} px")
                logging.info(f"Average Y spacing: {np.mean(y_spacings):.1f} px")
                logging.info(f"Expected spacing (non-overlap): {non_overlap_len:.1f} px")
            
            logging.info("="*50)

    except Exception as e:
        logging.error(f"Global error occurred: {e}", exc_info=True)
    finally:
        jb.kill_vm()
        logging.info("Java VM stopped")

if __name__ == "__main__":
    main()