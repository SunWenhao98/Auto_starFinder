import argparse
import copy
import subprocess
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# def get_coords(path):
#       f = open(path) 
#       line = f.readline()
#       list = []
#       while line:
#             if line.strip().startswith("Position"):
#                   a = np.array(line.replace('Position','').replace('.tif; ; (',',').replace(', ',',').replace(')\n','').split(','))
#                   a = [float(x) for x in a] # Remove rounding for raw coordinates
                  
#                   list.append(a)
#             line = f.readline()
#       coords_df = np.array(list)
#       f.close
#       return coords_df[:, 0:3]

def get_coords(path):
    coords = []

    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()

            if line.startswith("Position"):
                a = line.replace("Position", "") \
                        .replace(".tif; ; (", ",") \
                        .replace(", ", ",") \
                        .replace(")", "") \
                        .split(",")

                a = [float(x) for x in a]
                coords.append(a)

    if len(coords) == 0:
        raise ValueError(f"No Position lines found in file: {path}")

    coords_df = np.array(coords)

    # 第 0 列是 position index，第 1 列是 x，第 2 列是 y
    return coords_df[:, 0:3]

def get_grid_order(Tile_summary_file, tolerance=200):
    """
    将带有坐标偏离的Tile绝对像素坐标映射到逻辑网格坐标(第几行第几列)
    
    参数:
    Tile_summary_file: csv文件路径，第一列应为id，含有center_x_px, center_y_px列
    tolerance: 坐标判定为同一组的最大距离差值（默认300像素）
    """
    # 1. 读取数据
    df = pd.read_csv(Tile_summary_file)
    # 假设第一列是id，获取其列名
    id_col = 'real_id'
    
    def group_coordinates(coords, tol):
        """对坐标进行排序并分群"""
        # 对原始值进行去重和排序
        sorted_unique = sorted(coords.unique())
        groups = []
        if not sorted_unique:
            return groups
        
        # 初始群组
        current_group = [sorted_unique[0]]
        for i in range(1, len(sorted_unique)):
            if sorted_unique[i] - np.mean(current_group) <= tol:
                current_group.append(sorted_unique[i])
            else:
                groups.append(np.mean(current_group))
                current_group = [sorted_unique[i]]
        groups.append(np.mean(current_group))
        return sorted(groups)

    # 2. 分别提取X和Y的逻辑组（代表网格的中心线）
    # X决定了有多少列，Y决定了有多少行
    x_logical_centers = group_coordinates(df['center_x_px'], tolerance)
    y_logical_centers = group_coordinates(df['center_y_px'], tolerance)
    
    num_cols = len(x_logical_centers)
    num_rows = len(y_logical_centers)
    
    # 3. 映射每个Tile到逻辑网格
    def get_index(val, centers, tol):
        for i, center in enumerate(centers):
            if abs(val - center) <= tol:
                # return i + 1 # 1-based
                return i     # 0-based
        return None

    df['grid_col'] = df['center_x_px'].apply(lambda x: get_index(x, x_logical_centers, tolerance))
    df['grid_row'] = df['center_y_px'].apply(lambda y: get_index(y, y_logical_centers, tolerance))
    
    # 4. 整理结果
    # 提取 id, 物理坐标, 逻辑行列
    result_df = df[[id_col, 'grid_row', 'grid_col']].copy()

    grid_df = result_df.rename(columns={
    'real_id': 'tile',
    'grid_col': 'column_index',
    'grid_row': 'row_index'
    })
    
    print(f"Grid识别完成: 总共 {num_rows} 行, {num_cols} 列")

    return grid_df


def build_coordinate_frames(
    tile_initial_path,
    tile_registered_path,
    tile_summary_path,
    image_width,
):
    """Build merged and origin-tuned coordinate frames for integration."""
    exp_coords = get_coords(tile_initial_path)
    obs_coords = get_coords(tile_registered_path)
    grid_df = get_grid_order(tile_summary_path)

    coords_df = pd.DataFrame(
        obs_coords,
        columns=["tile", "column_coord_obs", "row_coord_obs"],
    )
    coords_exp_df = pd.DataFrame(
        exp_coords,
        columns=["tile", "column_coord_exp", "row_coord_exp"],
    )
    coords_df["tile"] = coords_df["tile"].astype(int)
    coords_exp_df["tile"] = coords_exp_df["tile"].astype(int)
    grid_df["tile"] = grid_df["tile"].astype(int)
    coords_df = coords_df.merge(coords_exp_df, on="tile")
    coords_df = coords_df.merge(grid_df, on="tile")

    coords_without_blank = coords_df.loc[coords_df["tile"] > 0, :]
    if coords_without_blank.empty:
        raise ValueError("No non-blank tiles found in coordinate inputs")

    min_column = np.min(coords_without_blank["column_coord_obs"])
    min_row = np.min(coords_without_blank["row_coord_obs"])
    max_column = np.max(coords_without_blank["column_coord_obs"])
    max_row = np.max(coords_without_blank["row_coord_obs"])
    shape = (
        max_column - min_column + image_width,
        max_row - min_row + image_width,
    )

    tuned_coords_df = copy.deepcopy(coords_df)
    tuned_coords_df["column_coord_obs"] = coords_df["column_coord_obs"] - min_column
    tuned_coords_df["row_coord_obs"] = coords_df["row_coord_obs"] - min_row

    grid_shape = (
        len(
            np.unique(
                coords_without_blank["column_coord_exp"] // (image_width * 0.9)
            )
        ),
        len(
            np.unique(coords_without_blank["row_coord_exp"] // (image_width * 0.9))
        ),
    )
    tile_to_grid = {
        int(row["tile"]): (int(row["column_index"]), int(row["row_index"]))
        for _, row in tuned_coords_df.iterrows()
        if row["tile"] > 0
    }
    return coords_df, tuned_coords_df, shape, grid_shape, tile_to_grid


def order_clustermap_candidates(seg_dir):
    """Return direct-child ClusterMap directories in GNU version-sort order."""
    seg_path = Path(seg_dir)
    candidates = [
        path
        for path in seg_path.iterdir()
        if path.is_dir() and path.name.startswith("clustermap")
    ]
    basenames = [path.name for path in candidates]
    result = subprocess.run(
        ["sort", "-Vr"],
        text=True,
        input="\n".join(basenames) + ("\n" if basenames else ""),
        capture_output=True,
        check=True,
    )
    by_name = {path.name: path for path in candidates}
    return [by_name[name] for name in result.stdout.splitlines()]


def select_clustermap_source(seg_dir, output_label, clean_gene_match_string):
    """Select an explicit or highest-version complete ClusterMap directory."""
    seg_path = Path(seg_dir)
    if output_label == "auto":
        candidates = order_clustermap_candidates(seg_path)
    else:
        candidates = [seg_path / f"clustermap_{output_label}"]

    required_names = (
        f"{clean_gene_match_string}_clean_genes.csv",
        "remain_reads_assigned.csv",
        "cell_center.csv",
    )
    for candidate in candidates:
        if candidate.is_dir() and all(
            (candidate / filename).is_file() for filename in required_names
        ):
            return candidate
    raise FileNotFoundError(
        f"No complete ClusterMap output found in {seg_path} for label {output_label}"
    )


def load_clustermap_source(source_dir):
    """Load reads and cell centers from a selected ClusterMap directory."""
    source_path = Path(source_dir)
    reads = pd.read_csv(source_path / "remain_reads_assigned.csv", index_col=0)
    centers = pd.read_csv(source_path / "cell_center.csv", index_col=0)
    return reads.reset_index(), centers

    
    # return {
    #     "num_rows": num_rows,
    #     "num_cols": num_cols,
    #     "grid_data": result_df
    # }

# 使用示例:
# res = get_grid_order("TileSummary.csv", 300)
# print(res["grid_data"].head())


def calculate_valid_region_bounds(coords_df_tuned, t_grid_c, t_grid_r, upper_left, img_c, img_r):
      """
      计算当前tile的有效区域边界（去除overlap），类似create_tile_config.py的逻辑
      返回: (start_x_norm, end_x_norm, start_y_norm, end_y_norm) - 相对于tile左上角的局部坐标
      """
      current_x = upper_left.iloc[0]  # 当前tile的左上角x坐标（全局）
      current_y = upper_left.iloc[1]  # 当前tile的左上角y坐标（全局）
      
      # 初始化边界为tile的完整范围
      start_x_global = current_x
      start_y_global = current_y
      end_x_global = current_x + img_c
      end_y_global = current_y + img_r
      
      # 检查左边的tile
      left_tile_col = t_grid_c - 1
      if left_tile_col >= 0:
            left_indices = coords_df_tuned.index[
                  (coords_df_tuned['column_index'] == left_tile_col) & 
                  (coords_df_tuned['row_index'] == t_grid_r)
            ]
            if len(left_indices) > 0:
                  order_left = left_indices[0]
                  if coords_df_tuned.loc[order_left, 'tile'] != 0:
                        left_tile_upper_left = coords_df_tuned.loc[order_left, ['column_coord_obs', 'row_coord_obs']]
                        left_tile_x = left_tile_upper_left.iloc[0]
                        # 计算overlap的中点，类似create_tile_config.py第88行
                        overlap_midpoint = int((left_tile_x + img_c - current_x) / 2 + 0.5) + current_x
                        start_x_global = overlap_midpoint
      
      # 检查右边的tile
      right_tile_col = t_grid_c + 1
      right_indices = coords_df_tuned.index[
            (coords_df_tuned['column_index'] == right_tile_col) & 
            (coords_df_tuned['row_index'] == t_grid_r)
      ]
      if len(right_indices) > 0:
            order_right = right_indices[0]
            if coords_df_tuned.loc[order_right, 'tile'] != 0:
                  right_tile_upper_left = coords_df_tuned.loc[order_right, ['column_coord_obs', 'row_coord_obs']]
                  right_tile_x = right_tile_upper_left.iloc[0]
                  # 计算overlap的中点，类似create_tile_config.py第100行
                  overlap_midpoint = int((current_x + img_c - right_tile_x) / 2 + 0.5) + right_tile_x
                  end_x_global = overlap_midpoint
      
      # 检查上边的tile
      top_tile_row = t_grid_r - 1
      if top_tile_row >= 0:
            top_indices = coords_df_tuned.index[
                  (coords_df_tuned['column_index'] == t_grid_c) & 
                  (coords_df_tuned['row_index'] == top_tile_row)
            ]
            if len(top_indices) > 0:
                  order_top = top_indices[0]
                  if coords_df_tuned.loc[order_top, 'tile'] != 0:
                        top_tile_upper_left = coords_df_tuned.loc[order_top, ['column_coord_obs', 'row_coord_obs']]
                        top_tile_y = top_tile_upper_left.iloc[1]
                        # 计算overlap的中点，类似create_tile_config.py第94行
                        overlap_midpoint = int((top_tile_y + img_r - current_y) / 2 + 0.5) + current_y
                        start_y_global = overlap_midpoint
      
      # 检查下边的tile
      bottom_tile_row = t_grid_r + 1
      bottom_indices = coords_df_tuned.index[
            (coords_df_tuned['column_index'] == t_grid_c) & 
            (coords_df_tuned['row_index'] == bottom_tile_row)
      ]
      if len(bottom_indices) > 0:
            order_bottom = bottom_indices[0]
            if coords_df_tuned.loc[order_bottom, 'tile'] != 0:
                  bottom_tile_upper_left = coords_df_tuned.loc[order_bottom, ['column_coord_obs', 'row_coord_obs']]
                  bottom_tile_y = bottom_tile_upper_left.iloc[1]
                  # 计算overlap的中点，类似create_tile_config.py第106行
                  overlap_midpoint = int((current_y + img_r - bottom_tile_y) / 2 + 0.5) + bottom_tile_y
                  end_y_global = overlap_midpoint
      
      start_x_norm = start_x_global - current_x
      start_y_norm = start_y_global - current_y
      end_x_norm = end_x_global - current_x
      end_y_norm = end_y_global - current_y
      
      return start_x_norm, end_x_norm, start_y_norm, end_y_norm


def integrate_tiles(
    coords_df_tuned,
    input_reg_dir,
    image_width,
    seg_method,
    clean_gene_match_string,
    clustermap_output_label,
    alignment_thresh=0.5,
):
    """Integrate per-tile reads and centers while preserving overlap ownership."""
    tile_to_grid = {
        int(row["tile"]): (int(row["column_index"]), int(row["row_index"]))
        for _, row in coords_df_tuned.iterrows()
        if row["tile"] > 0
    }
    read_frames = []
    center_frames = []
    cell_barcode_min = 0
    sorted_tiles = sorted(tile_to_grid)

    for tile_order in sorted_tiles:
        t_grid_c, t_grid_r = tile_to_grid[tile_order]
        median_col = coords_df_tuned[
            (coords_df_tuned.column_index == t_grid_c) & (coords_df_tuned.tile != 0)
        ]["column_coord_obs"]
        median_row = coords_df_tuned[
            (coords_df_tuned.row_index == t_grid_r) & (coords_df_tuned.tile != 0)
        ]["row_coord_obs"]
        if median_col.empty or median_row.empty:
            continue

        matching_indices = coords_df_tuned.index[
            (coords_df_tuned["column_index"] == t_grid_c)
            & (coords_df_tuned["row_index"] == t_grid_r)
        ]
        if matching_indices.empty:
            continue
        order = matching_indices[0]
        upper_left = coords_df_tuned.loc[
            order, ["column_coord_obs", "row_coord_obs"]
        ]
        median_col_coord = np.median(median_col)
        median_row_coord = np.median(median_row)
        left_thresh = median_col_coord - (1 + alignment_thresh) * image_width
        right_thresh = median_col_coord + (1 + alignment_thresh) * image_width
        upper_thresh = median_row_coord - (1 + alignment_thresh) * image_width
        lower_thresh = median_row_coord + (1 + alignment_thresh) * image_width
        if (
            upper_left.iloc[0] >= right_thresh
            or upper_left.iloc[0] <= left_thresh
            or upper_left.iloc[1] >= lower_thresh
            or upper_left.iloc[1] <= upper_thresh
        ):
            print(f"- Tile {tile_order} is aligned too far away from its expected position.")
            continue

        seg_dir = Path(input_reg_dir) / f"Position{tile_order:03d}" / "seg"
        source_dir = select_clustermap_source(
            seg_dir,
            clustermap_output_label,
            clean_gene_match_string,
        )
        remain_reads_t, cell_center_t = load_clustermap_source(source_dir)

        if seg_method == "clustermap":
            remain_reads_t.rename(columns={"clustermap": "cell_barcode"}, inplace=True)
            cell_center_t.rename(columns={"x": "column", "y": "row"}, inplace=True)
        elif seg_method == "watershed":
            remain_reads_t.rename(
                columns={
                    "Gene": "gene",
                    "x": "spot_location_1",
                    "y": "spot_location_2",
                    "z": "spot_location_3",
                },
                inplace=True,
            )
            cell_center_t.rename(columns={"x": "column", "y": "row"}, inplace=True)

        tile_label = f"{t_grid_c},{t_grid_r},{tile_order}"
        remain_reads_t["gridc_gridr_tilenum"] = tile_label
        cell_center_t["gridc_gridr_tilenum"] = tile_label
        remain_reads_t["spot_location_1"] += upper_left.iloc[0]
        remain_reads_t["spot_location_2"] += upper_left.iloc[1]
        cell_center_t["column"] += upper_left.iloc[0]
        cell_center_t["row"] += upper_left.iloc[1]

        remain_reads_t["raw_cell_barcode"] = remain_reads_t["cell_barcode"]
        cell_center_t["raw_cell_barcode"] = cell_center_t["cell_barcode"]
        process_mask = remain_reads_t["cell_barcode"] == -1
        remain_reads_t.loc[~process_mask, "cell_barcode"] = (
            remain_reads_t.loc[~process_mask, "cell_barcode"]
            + cell_barcode_min
            + 1
        )
        remain_reads_t.loc[process_mask, "cell_barcode"] = 0
        cell_center_t["cell_barcode"] += cell_barcode_min + 1

        start_x, end_x, start_y, end_y = calculate_valid_region_bounds(
            coords_df_tuned,
            t_grid_c,
            t_grid_r,
            upper_left,
            image_width,
            image_width,
        )
        start_x_global = upper_left.iloc[0] + start_x
        end_x_global = upper_left.iloc[0] + end_x
        start_y_global = upper_left.iloc[1] + start_y
        end_y_global = upper_left.iloc[1] + end_y

        cell_center_t = cell_center_t[
            (cell_center_t["column"] >= start_x_global)
            & (cell_center_t["column"] < end_x_global)
            & (cell_center_t["row"] >= start_y_global)
            & (cell_center_t["row"] < end_y_global)
        ]
        valid_cell_barcodes = set(cell_center_t["cell_barcode"].values)
        non_noise_reads = remain_reads_t[remain_reads_t["is_noise"] != -1]
        reads_process = non_noise_reads[non_noise_reads["raw_cell_barcode"] == -1]
        reads_within_cells = non_noise_reads[
            (non_noise_reads["is_noise"] == 0)
            & (non_noise_reads["raw_cell_barcode"] != -1)
            & (non_noise_reads["cell_barcode"].isin(valid_cell_barcodes))
        ]
        reads_process_filtered = reads_process[
            (reads_process["spot_location_1"] >= start_x_global)
            & (reads_process["spot_location_1"] < end_x_global)
            & (reads_process["spot_location_2"] >= start_y_global)
            & (reads_process["spot_location_2"] < end_y_global)
        ]
        if not reads_within_cells.empty:
            read_frames.append(reads_within_cells)
        if not reads_process_filtered.empty:
            read_frames.append(reads_process_filtered)
        if not cell_center_t.empty:
            center_frames.append(cell_center_t)
            cell_barcode_min = np.max(cell_center_t["cell_barcode"]) + 1

    remain_reads = pd.concat(read_frames, ignore_index=True)
    cell_center = pd.concat(center_frames, ignore_index=True)
    remain_reads = remain_reads.drop_duplicates(subset=None, keep="first")
    remain_reads.rename(
        columns={
            "spot_location_1": "column",
            "spot_location_2": "row",
            "spot_location_3": "z",
        },
        inplace=True,
    )
    cell_center.rename(columns={"z_axis": "z"}, inplace=True)
    remain_reads = remain_reads.astype(
        {
            "column": "int",
            "row": "int",
            "z": "int",
            "cell_barcode": "int",
            "raw_cell_barcode": "int",
        }
    )
    cell_center = cell_center.astype(
        {
            "cell_barcode": "int",
            "column": "int",
            "row": "int",
            "z": "int",
            "raw_cell_barcode": "int",
        }
    )
    return remain_reads, cell_center


def deterministic_cell_colormap(seed=260917, color_count=256):
    """Return the stable categorical colour map shared by all panels."""
    colors = np.random.default_rng(seed).random((color_count, 3)).tolist()
    return matplotlib.colors.ListedColormap(colors)


def bounded_figsize(width, height, min_edge=4.0, max_edge=16.0):
    """Scale an aspect ratio into bounded output dimensions in inches."""
    safe_width = max(float(width), 1.0)
    safe_height = max(float(height), 1.0)
    if safe_width >= safe_height:
        return max_edge, max(min_edge, max_edge * safe_height / safe_width)
    return max(min_edge, max_edge * safe_width / safe_height), max_edge


def _draw_integration_panel(
    axis,
    panel_name,
    remain_reads,
    cell_center,
    coords_df_tuned,
    shape_row,
    cell_colormap,
):
    show_reads = panel_name.startswith("reads_centers")
    show_tiles = panel_name.endswith("tile_order")
    if show_reads:
        axis.scatter(
            remain_reads["column"],
            shape_row - remain_reads["row"],
            s=0.1,
            alpha=0.8,
            c=pd.Categorical(remain_reads["raw_cell_barcode"]).codes,
            cmap=cell_colormap,
            rasterized=True,
        )
    axis.scatter(
        cell_center["column"],
        shape_row - cell_center["row"],
        s=1 if show_reads else 10,
        color="red",
        alpha=1 if show_reads else 0.8,
        rasterized=True,
    )
    if show_tiles:
        tile_coords = coords_df_tuned.loc[
            coords_df_tuned["tile"] != 0,
            ["column_coord_obs", "row_coord_obs", "tile"],
        ].to_numpy(copy=True)
        tile_coords[:, 1] = shape_row - tile_coords[:, 1]
        axis.scatter(
            tile_coords[:, 0],
            tile_coords[:, 1],
            c=tile_coords[:, 2],
            cmap="viridis",
            rasterized=True,
        )
        for column, row, tile in tile_coords:
            axis.text(column, row, str(int(tile)), fontsize=8)
    axis.set_title(panel_name.replace("_", " ").title())
    axis.axis("off")


def _save_figure(figure, output_stem, include_pdf):
    figure.savefig(output_stem.with_suffix(".png"), dpi=300)
    if include_pdf:
        figure.savefig(output_stem.with_suffix(".pdf"))
    plt.close(figure)


def render_integration_figures(
    remain_reads,
    cell_center,
    coords_df_tuned,
    shape_row,
    output_dir,
    project_name,
    seg_method,
    output_suffix,
):
    """Write the legacy composite and four standalone PNG/PDF panels."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    base = output_path / (
        f"cell_reads_profile_{project_name}_{seg_method}_{output_suffix}"
    )
    max_column = max(
        float(remain_reads["column"].max()),
        float(cell_center["column"].max()),
        float(coords_df_tuned["column_coord_obs"].max()),
    )
    panel_size = bounded_figsize(max_column, shape_row)
    cell_colormap = deterministic_cell_colormap()
    panel_names = (
        "reads_centers",
        "reads_centers_tile_order",
        "cell_centers",
        "cell_centers_tile_order",
    )

    with plt.style.context("dark_background"):
        legacy_figure, legacy_axes = plt.subplots(
            2,
            2,
            figsize=panel_size,
        )
        for axis, panel_name in zip(legacy_axes.flat, panel_names):
            _draw_integration_panel(
                axis,
                panel_name,
                remain_reads,
                cell_center,
                coords_df_tuned,
                shape_row,
                cell_colormap,
            )
        legacy_figure.tight_layout()
        _save_figure(legacy_figure, base, include_pdf=False)

        for panel_name in panel_names:
            figure, axis = plt.subplots(figsize=panel_size)
            _draw_integration_panel(
                axis,
                panel_name,
                remain_reads,
                cell_center,
                coords_df_tuned,
                shape_row,
                cell_colormap,
            )
            figure.tight_layout()
            _save_figure(
                figure,
                Path(f"{base}_{panel_name}"),
                include_pdf=True,
            )
    return cell_colormap

def command_args(argv=None):
    parser = argparse.ArgumentParser(description="Integrate per-tile reads and cells")
    parser.add_argument("--tile_initial", required=True)
    parser.add_argument("--tile_registered", required=True)
    parser.add_argument("--tile_grid", required=True)
    parser.add_argument("--input_reg_dir", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--coords_output", required=True)
    parser.add_argument("--tuned_coords_output", required=True)
    parser.add_argument("--cell_centers_output", required=True)
    parser.add_argument("--remain_reads_output", required=True)
    parser.add_argument("--figure_output_dir", required=True)
    parser.add_argument("--image_width", type=int, required=True)
    parser.add_argument("--seg_method", required=True)
    parser.add_argument("--project_name", required=True)
    parser.add_argument("--output_suffix", required=True)
    parser.add_argument("--clean_gene_match_string", required=True)
    parser.add_argument("--clustermap_output_label", required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = command_args(argv)
    input_paths = (
        Path(args.tile_initial),
        Path(args.tile_registered),
        Path(args.tile_grid),
        Path(args.input_reg_dir),
    )
    for input_path in input_paths:
        if not input_path.exists():
            raise FileNotFoundError(f"Required input not found: {input_path}")

    output_paths = (
        Path(args.output_dir),
        Path(args.coords_output).parent,
        Path(args.tuned_coords_output).parent,
        Path(args.cell_centers_output).parent,
        Path(args.remain_reads_output).parent,
        Path(args.figure_output_dir),
    )
    for output_path in output_paths:
        output_path.mkdir(parents=True, exist_ok=True)

    coords, tuned_coords, shape, grid_shape, _ = build_coordinate_frames(
        args.tile_initial,
        args.tile_registered,
        args.tile_grid,
        args.image_width,
    )
    print(f"Grid dimensions: {grid_shape[0]}-x-{grid_shape[1]}")
    coords.to_csv(args.coords_output)
    tuned_coords.to_csv(args.tuned_coords_output)
    remain_reads, cell_centers = integrate_tiles(
        tuned_coords,
        args.input_reg_dir,
        args.image_width,
        args.seg_method,
        args.clean_gene_match_string,
        args.clustermap_output_label,
    )
    cell_centers.to_csv(args.cell_centers_output)
    remain_reads.to_csv(args.remain_reads_output)
    render_integration_figures(
        remain_reads,
        cell_centers,
        tuned_coords,
        shape_row=shape[1],
        output_dir=args.figure_output_dir,
        project_name=args.project_name,
        seg_method=args.seg_method,
        output_suffix=args.output_suffix,
    )
    print(
        f"STATUS: SUCCESS | reads={len(remain_reads)} | cells={len(cell_centers)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
