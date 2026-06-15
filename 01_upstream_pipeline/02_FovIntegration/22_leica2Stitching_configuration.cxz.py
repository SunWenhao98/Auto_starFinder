import argparse
import logging
import pandas as pd
import numpy as np
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def extract_index(f, pattern):
    match = re.search(pattern, f.name if isinstance(f, Path) else Path(f).name)
    return int(match.group(1)) if match else float('inf')


def _match_tokens(match_string):
    return [token.strip().lower() for token in match_string.split(",") if token.strip()]


def _find_matching_tifs(input_dir: Path, match_string: str):
    all_files = sorted(
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {".tif", ".tiff"}
    )
    tokens = _match_tokens(match_string)
    files = [
        f for f in all_files
        if any(
            token == part.lower()
            for part in f.relative_to(input_dir).parts[:-1]
            for token in tokens
        )
    ]

    logging.info(f"Found {len(all_files)} tif/tiff files under input_dir: {input_dir}")
    logging.info(
        f"Matched {len(files)} files by relative parent folder using "
        f"match_string='{match_string}', folders={tokens}"
    )
    samples = files if files else all_files
    for sample in samples[:5]:
        sample_label = "matched" if files else "available"
        logging.info(f"Sample {sample_label} file: {sample.relative_to(input_dir).as_posix()}")
    return files


def _parse_maf_xml(maf_path: Path):
    positions = []
    tree = ET.parse(str(maf_path))
    root = tree.getroot()

    for elem in root.iter():
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag == 'XYZStagePointDefinition':
            sx = elem.attrib.get('StageXPos')
            sy = elem.attrib.get('StageYPos')
            if sx is not None and sy is not None:
                name = elem.attrib.get(
                    'PositionIdentifier',
                    elem.attrib.get('Name', f"Pos_{len(positions)}")
                )
                positions.append({
                    'name': name,
                    'phys_x': float(sx) * 1e6,  # m -> µm
                    'phys_y': float(sy) * 1e6,  # m -> µm
                })

    if positions:
        logging.info(f"XML parse (LAS X MAF): found {len(positions)} positions.")
        return positions

    # 深度搜索
    for elem in root.iter():
        attrs = elem.attrib
        phys_x = phys_y = None
        for key, val in attrs.items():
            key_lower = key.lower()
            if any(kw in key_lower for kw in ['posx', 'positionx', 'stagex', 'xpos']):
                try: phys_x = float(val)
                except: pass
            if any(kw in key_lower for kw in ['posy', 'positiony', 'stagey', 'ypos']):
                try: phys_y = float(val)
                except: pass
        if phys_x is not None and phys_y is not None:
            name = attrs.get('Name', attrs.get('name', f"Pos_{len(positions)}"))
            positions.append({'name': name, 'phys_x': phys_x, 'phys_y': phys_y})

    logging.info(f"XML deep search: found {len(positions)} positions.")
    return positions


def plot_tile_positions(df, tile_size_px, non_overlap_len, output_dir, show_labels=True):
    if len(df) == 0:
        logging.warning("No data to plot")
        return None, None
    
    df['center_x'] = df['pos_x_px'] + tile_size_px / 2
    df['center_y'] = df['pos_y_px'] + tile_size_px / 2
    
    min_x = df['pos_x_px'].min()
    max_x = df['pos_x_px'].max()
    min_y = df['pos_y_px'].min()
    max_y = df['pos_y_px'].max()
    
    x_range = max_x - min_x + tile_size_px
    y_range = max_y - min_y + tile_size_px
    padding = tile_size_px * 0.1
    
    # ========== 图1: Tile布局图 ==========
    fig1, ax1 = plt.subplots(figsize=(20, 16))
    plt.style.use('seaborn-v0_8-darkgrid')
    
    ax1.set_title('Tile Layout Visualization (Leica)', fontsize=16, fontweight='bold', pad=20)
    ax1.set_xlabel('X Position (pixels)', fontsize=12)
    ax1.set_ylabel('Y Position (pixels)', fontsize=12)
    ax1.set_aspect('equal')
    
    ax1.set_xlim(min_x - padding, max_x + tile_size_px + padding)
    max_y_value = df['pos_y_px'].max() + tile_size_px
    ax1.set_ylim(max_y_value + padding, min_y - padding)
    
    colors = plt.cm.tab20c(np.linspace(0, 1, min(len(df), 20)))
    
    for idx, row in df.iterrows():
        base_color = colors[idx % len(colors)]
        facecolor = list(base_color)
        facecolor[3] = 0.3 
        
        rect = Rectangle(
            (row['pos_x_px'], row['pos_y_px']),
            tile_size_px, tile_size_px,
            linewidth=1.5,
            edgecolor=base_color,
            facecolor=facecolor,
            label=f"Pos{int(row['real_id']):03d}"
        )
        ax1.add_patch(rect)
        
        if show_labels:
            center_x = row['pos_x_px'] + tile_size_px / 2
            center_y = row['pos_y_px'] + tile_size_px / 2
            ax1.text(
                center_x, center_y,
                f"{int(row['real_id'])}",
                ha='center', va='center',
                fontsize=9, fontweight='bold',
                color='black',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8, edgecolor='none', linewidth=0.5)
            )
    
    ax1.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
    
    stats_text = f'Total Tiles: {len(df)}\n'
    stats_text += f'X Range: {x_range:.1f} px\n'
    stats_text += f'Y Range: {y_range:.1f} px\n'
    stats_text += f'Tile Size: {tile_size_px} px\n'
    stats_text += f'Overlap: {tile_size_px - non_overlap_len:.1f} px\n'
    stats_text += f'Source: Leica MAF'
    
    ax1.text(0.02, 0.98, stats_text, transform=ax1.transAxes, fontsize=10, verticalalignment='top',
        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.85, edgecolor='brown', linewidth=1))
    
    plt.tight_layout()
    output_path1 = output_dir / "tile_layout_leica.png"
    fig1.savefig(output_path1, dpi=300, bbox_inches='tight', facecolor='white')
    logging.info(f"Tile layout saved to: {output_path1}")
    
    # ========== 图2: Tile中心分布散点图 ==========
    fig2, ax2 = plt.subplots(figsize=(20, 12))
    plt.style.use('seaborn-v0_8-darkgrid')
    
    ax2.set_title('Tile Center Distribution (Leica)', fontsize=16, fontweight='bold', pad=20)
    ax2.set_xlabel('X Center (pixels)', fontsize=12)
    ax2.set_ylabel('Y Center (pixels)', fontsize=12)
    ax2.invert_yaxis()
    
    scatter_size = 150 if len(df) < 20 else (120 if len(df) < 50 else (80 if len(df) < 100 else 50))
    
    scatter = ax2.scatter(
        df['center_x'], df['center_y'], c=df['real_id'],
        cmap='viridis', s=scatter_size, alpha=0.8, edgecolors='black', linewidth=1, zorder=3
    )
    
    cbar = plt.colorbar(scatter, ax=ax2, pad=0.02)
    cbar.set_label('Tile ID', fontsize=11)
    
    if show_labels:
        max_labels = 50
        label_indices = np.linspace(0, len(df)-1, min(max_labels, len(df)), dtype=int)
        for idx in label_indices:
            row = df.iloc[idx]
            ax2.text(
                row['center_x'], row['center_y'], f"{int(row['real_id'])}",
                ha='center', va='center', fontsize=8 if len(df) < 30 else 7, fontweight='bold', color='white',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.5, edgecolor='none'), zorder=4
            )
            
    ax2.grid(True, alpha=0.3, linestyle='--', linewidth=0.5, zorder=1)
    plt.tight_layout()
    
    output_path2 = output_dir / "tile_centers_distribution_leica.png"
    fig2.savefig(output_path2, dpi=300, bbox_inches='tight', facecolor='white')
    logging.info(f"Tile centers saved to: {output_path2}")
    
    plt.close(fig1)
    plt.close(fig2)


def main():
    parser = argparse.ArgumentParser(description="Leica MAF -> TileConfiguration.txt (with identical plot logic to VSI)")
    parser.add_argument('--input_dir', type=Path, required=True)
    parser.add_argument('--maf_file', type=Path, required=True)
    parser.add_argument('--output_dir', type=Path, required=True)
    parser.add_argument('--match_string', type=str, default='C1')
    parser.add_argument('--pixel_size_um', type=float, default=0.142)
    parser.add_argument('--image_xy', type=int, default=2048)
    parser.add_argument('--overlap_ratio', type=float, default=0.1)
    parser.add_argument('--invert_y', action='store_true', default=False)
    parser.add_argument('--position_offset', type=int, default=0, help='从MAF文件的第几个物理坐标开始匹配(主要用于一个MAF包含多个切片但输出分开的情况)')
    
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    t0 = time.time()
    raw_positions = _parse_maf_xml(args.maf_file)
    if not raw_positions:
        logging.error("No positions found.")
        return
        
    # 应用 offset (截断掉前 offset 个)
    if args.position_offset > 0:
        logging.info(f"Applying position offset: skipping first {args.position_offset} positions.")
        raw_positions = raw_positions[args.position_offset:]
    logging.info(f"Positions available after offset: {len(raw_positions)}")

    # Match TIF
    files = _find_matching_tifs(args.input_dir, args.match_string)
    
    # Sort by Position number so file order matches the MAF coordinate order.
    pattern = r'Position(\d+)'
    pattern = r'Position(\d+)'
    files = sorted(files, key=lambda f: extract_index(f, pattern))
    
    n_tiles = min(len(files), len(raw_positions))
    logging.info(
        f"Pairing {n_tiles} tiles: matched_files={len(files)}, "
        f"positions_after_offset={len(raw_positions)}"
    )
    tiles_data = []
    
    # 构建DataFrame
    for idx in range(n_tiles):
        f = files[idx]
        pos = raw_positions[idx]
        real_id = extract_index(f, pattern)
        if real_id == float('inf'):
            real_id = idx + 1
            
        rel_path = f.relative_to(args.input_dir).as_posix()
            
        tiles_data.append({
            'relative_path': rel_path,
            'real_id': int(real_id),
            'phys_x': pos['phys_x'],
            'phys_y': pos['phys_y']
        })

    if not tiles_data:
        logging.error(
            "No valid data constructed. Usually this means no tif files matched "
            "the selected relative parent folder, or the MAF offset removed all positions."
        )
        return

    df = pd.DataFrame(tiles_data)
    min_x = df['phys_x'].min()
    min_y = df['phys_y'].min()
    max_y = df['phys_y'].max()

    # 物理 -> 像素
    df['pos_x_px'] = (df['phys_x'] - min_x) / args.pixel_size_um
    if args.invert_y:
        df['pos_y_px'] = (max_y - df['phys_y']) / args.pixel_size_um
    else:
        df['pos_y_px'] = (df['phys_y'] - min_y) / args.pixel_size_um

    output_config_path = args.output_dir / "TileConfiguration.txt"
    with open(output_config_path, 'w') as f:
        f.write("# Define the number of dimensions we are working on\n")
        f.write("dim = 3\n\n")
        f.write("# Define the image coordinates\n")
        
        for _, row in df.iterrows():
            fname = row['relative_path']
            x = row['pos_x_px']
            y = row['pos_y_px']
            f.write(f"{fname}; ; ({x:.2f}, {y:.2f}, 0.0)\n")

    logging.info(f"Generation complete: {output_config_path}")
    
    # 绘制可视化
    if len(df) > 0:
        logging.info("Generating tile visualization...")
        plot_tile_positions(
            df=df,
            tile_size_px=args.image_xy,
            non_overlap_len=args.image_xy * (1 - args.overlap_ratio),
            output_dir=args.output_dir,
            show_labels=True
        )

if __name__ == "__main__":
    main()
