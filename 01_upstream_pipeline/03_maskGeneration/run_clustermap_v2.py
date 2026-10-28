import sys
import os
import math
import argparse
import functools
import shutil
from types import SimpleNamespace
import numpy as np
import pandas as pd
import tifffile as tiff
import matplotlib.pyplot as plt
from scipy import ndimage
from scipy.spatial import cKDTree
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm

from ClusterMap.clustermap import *
from skimage.morphology import disk
# ==========================================
# Helper Functions
# ==========================================

def nuclei_binary(labels_zyx, rotation_deg, erode, zgap=0):
    """3D nucleus labels (Z, Y, X, raw DAPI orientation) -> (Y, X, Z) binary aligned with dapi_processed.

    Each label is eroded by `erode` px within every layer: a pixel is kept only if every pixel of
    the disk around it carries the same label, so touching nuclei end up 2*erode px apart.
    Nuclei touching in z are kept `zgap` layers apart.
    """
    if rotation_deg % 90 != 0:
        raise ValueError("--binary_source cellpose supports rotations by multiples of 90 only")
    labels = np.rot90(labels_zyx, k=-(rotation_deg // 90), axes=(1, 2))
    if zgap > 0:
        labels = labels.copy()
        for _ in range(zgap):
            other = (labels[:-1] > 0) & (labels[1:] > 0) & (labels[:-1] != labels[1:])
            clash = np.zeros(labels.shape, dtype=bool)
            clash[:-1] |= other
            clash[1:] |= other
            labels[clash] = 0
    if erode > 0:
        footprint = disk(erode)
        binary = np.zeros(labels.shape, dtype=bool)
        for z in range(labels.shape[0]):
            low = ndimage.grey_erosion(labels[z], footprint=footprint)
            high = ndimage.grey_dilation(labels[z], footprint=footprint)
            binary[z] = (labels[z] > 0) & (low == high)
    else:
        binary = labels > 0
    return np.transpose(binary, (1, 2, 0))

def nuclei_footprints(labels_zyx, rotation_deg, anisotropy):
    """(row, col, radius, spacing) of each nucleus in the dapi_processed frame, radius from its xy footprint area,
    spacing = distance to the nearest other nucleus centre with z scaled by `anisotropy`."""
    labels = np.rot90(labels_zyx, k=-(rotation_deg // 90), axes=(1, 2))
    rows = []
    for o, sl in enumerate(ndimage.find_objects(labels), start=1):
        if sl is not None:
            m = labels[sl] == o
            r, c = np.nonzero(m.any(axis=0))
            rows.append((r.mean() + sl[1].start, c.mean() + sl[2].start, np.sqrt(len(r) / np.pi),
                         np.nonzero(m)[0].mean() + sl[0].start))
    rows = np.array(rows).reshape(-1, 4)
    centres = np.c_[rows[:, :2], rows[:, 3] * anisotropy]
    spacing = cKDTree(centres).query(centres, k=2)[0][:, 1] if len(rows) else np.empty(0)
    return np.c_[rows[:, :3], spacing]

def rotate_points(xy, radians, origin=(0, 0)):
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

TILE_RESULT_KEYS = ('spots', 'all_points', 'all_points_cellid', 'cellcenter', 'cellcenter_unique', 'cellid_unique')

def tile_path(work_dir, tile_idx, kind):
    return os.path.join(work_dir, f"tile_{tile_idx:03d}_{kind}.pkl")

PICKLE_GZIP = {'method': 'gzip', 'compresslevel': 1}

def write_pickle(obj, path):
    """Write next to the target and rename, so a reader never sees a partial file."""
    pd.to_pickle(obj, path + ".part", compression=PICKLE_GZIP)
    os.replace(path + ".part", path)

def run_tile_stage(args):
    """--stage tile: one subtile from the prepare stage's input; keeps only what model.stitch() reads."""
    src = tile_path(args.work_dir, args.tile_index, "in")
    if not os.path.exists(src):
        print(f"No input for tile {args.tile_index} (prepare wrote fewer tiles or none): {src}")
        return
    tile = pd.read_pickle(src, compression='gzip')
    global pct_filter  # process_tile reads it as a module global, set in __main__ for the other stages
    pct_filter = tile['pct_filter']
    out = pd.DataFrame([tile['row']], index=[args.tile_index])
    model_tile = process_tile(args.tile_index, out=out, model_params=tile['params'])
    keep = None if model_tile is None else {k: getattr(model_tile, k) for k in TILE_RESULT_KEYS if hasattr(model_tile, k)}
    write_pickle(keep, tile_path(args.work_dir, args.tile_index, "out"))
    print(f"Tile {args.tile_index}: {'no cells' if keep is None else 'done'}")

def load_tile_result(work_dir, tile_idx):
    path = tile_path(work_dir, tile_idx, "out")
    if not os.path.exists(path):
        raise FileNotFoundError(f"tile result missing: {path}")
    keep = pd.read_pickle(path, compression='gzip')
    return None if keep is None else SimpleNamespace(**keep)

def process_tile(tile_split, out, model_params):
    """
    Worker function for parallel processing of image tiles.
    """
    try:
        # Unpack parameters
        reads_filter = model_params['reads_filter']
        cell_num_threshold = model_params['cell_num_threshold']
        dapi_grid_interval = model_params['dapi_grid_interval']
        use_own_dapi = model_params['use_own_dapi']
        gene_list = model_params['gene_list']
        num_dims = model_params['num_dims']
        xy_radius = int(out.loc[tile_split, 'xy_radius']) if 'xy_radius' in out.columns else model_params['xy_radius']
        z_radius = model_params['z_radius']
        filter_val = model_params['filter_value']

        spots_tile = out.loc[tile_split, 'spots']
        dapi_tile = out.loc[tile_split, 'img']

        if spots_tile.shape[0] < reads_filter:
            return None

        if use_own_dapi:
            model_tile = ClusterMap(
                spots=spots_tile, dapi=None, gene_list=gene_list,
                num_dims=num_dims, xy_radius=xy_radius, z_radius=z_radius,
                fast_preprocess=True, gauss_blur=True
            )
            dapi_bi_tile = dapi_tile > filter_val
            dapi_bi_max_tile = dapi_bi_tile.max(2)
            
            model_tile.dapi = dapi_tile
            model_tile.dapi_binary = dapi_bi_tile
            model_tile.dapi_stacked = dapi_bi_max_tile
        elif model_params['binary_source'] == 'cellpose':
            nuclei_tile = out.loc[tile_split, 'binary'] > 0
            if not nuclei_tile[::dapi_grid_interval, ::dapi_grid_interval, ::dapi_grid_interval].any():
                # add_dapi_points fails on a window without nucleus voxels
                print(f"Tile {tile_split}: no nucleus voxel on the DAPI sampling grid, skipped")
                return None
            model_tile = ClusterMap(
                spots=spots_tile, dapi=None, gene_list=gene_list,
                num_dims=num_dims, xy_radius=xy_radius, z_radius=z_radius,
                fast_preprocess=False
            )
            model_tile.dapi = dapi_tile
            model_tile.dapi_binary = nuclei_tile
            model_tile.dapi_stacked = nuclei_tile.max(2)
            model_tile.preprocess(dapi_grid_interval=dapi_grid_interval, pct_filter=pct_filter)
        else:
            model_tile = ClusterMap(
                spots=spots_tile, dapi=dapi_tile, gene_list=gene_list,
                num_dims=num_dims, xy_radius=xy_radius, z_radius=z_radius,
                fast_preprocess=False
            )
            model_tile.preprocess(dapi_grid_interval=dapi_grid_interval, pct_filter=pct_filter)

        model_tile.min_spot_per_cell = reads_filter
        
        model_tile.segmentation(
            cell_num_threshold=cell_num_threshold,
            dapi_grid_interval=dapi_grid_interval,
            add_dapi=True, 
            use_genedis=True
        )
        
        if 'clustermap' in model_tile.spots.columns:
            model_tile.dapi = None  # Free memory
            model_tile.dapi_binary = None
            model_tile.dapi_stacked = None
            return model_tile
        
        return None

    except Exception as e:
        print(f"Error processing tile {tile_split}: {str(e)}")
        return None


def get_args():
    desc = "ClusterMap Parallel Processing Pipeline"
    parser = argparse.ArgumentParser(description=desc)
    
    # --- Input & Output ---
    parser.add_argument('--dapi_path', type=str, required=True, help='Absolute path to the DAPI .tiff file')
    parser.add_argument('--transcripts_file', type=str, required=True, help='Absolute path to the goodPoints/spots CSV file')
    parser.add_argument('--output_path', type=str, required=True, help='Absolute path to output directory')
    
    # --- Segmentation Core Parameters ---
    parser.add_argument('--cell_num_threshold', type=str, required=True, help='Threshold for cell number determination (float)')
    parser.add_argument('--dapi_grid_interval', type=int, required=True, help='Sampling interval for DAPI')
    parser.add_argument('--cell_radius', type=str, required=True, help='Cell radius "XY,Z" (e.g., "15,5")')
    parser.add_argument('--pct_filter', type=str, required=True, help='Percentile filter (float)')
    
    # --- Preprocessing & Tiling ---
    parser.add_argument('--ref_round', type=int, default=1, help='Reference round (metadata only)')
    parser.add_argument('--extra_preprocess', choices=['T', 'F'], required=True, help='Use fast/external DAPI preprocessing? (T/F)')
    parser.add_argument('--rotation', type=int, default=270, help='Degrees to rotate clockwise (default: 270)')
    parser.add_argument('--sub_span', type=int, default=800, help='Size of the tiling window (default: 800)')

    # expected_processes
    parser.add_argument('--expected_workers', type=int, default=4, help='Number of expected processes (default: 4)')
    parser.add_argument('--reads_filter', type=int, default=5, help='Minimum number of reads per spot')
    parser.add_argument('--overlap_percent', type=float, default=0.2, help='Percent overlap between tiles')

    parser.add_argument('--sqrt_pieces', type=int, default=2, help='parts of the tiling window (default: 4)')

    parser.add_argument('--binary_source', choices=['otsu', 'cellpose'], default='otsu', help='DAPI binary: ClusterMap Otsu or --nuclei_labels')
    parser.add_argument('--nuclei_labels', type=str, default=None, help='3D nucleus label tif (Z, Y, X)')
    parser.add_argument('--nuclei_erode', type=int, default=3, help='xy erosion of each nucleus in px')
    parser.add_argument('--nuclei_zgap', type=int, default=1, help='layers between nuclei touching in z')
    parser.add_argument('--sub_num', type=int, default=0, help='subtiles per side, replaces --sub_span when > 0')
    parser.add_argument('--radius_factor', type=float, default=0, help='xy radius per subtile = factor x mean (see --radius_stat) nucleus radius (or spacing) + intercept when > 0')
    parser.add_argument('--radius_intercept', type=float, default=0, help='added to factor x nucleus radius (or spacing), for --radius_factor')
    parser.add_argument('--radius_stat', choices=['mean', 'median'], default='mean', help='statistic of the subtile nuclei, for --radius_factor')
    parser.add_argument('--radius_from', choices=['size', 'spacing'], default='size', help='nucleus radius or distance to the nearest nucleus')
    parser.add_argument('--anisotropy', type=float, default=1.0, help='z step / xy pixel size, for --radius_from spacing')
    parser.add_argument('--stage', choices=['all', 'prepare', 'tile', 'merge'], default='all',
                        help='all: one job; prepare: write subtile inputs; tile: run --tile_index; merge: stitch tile results')
    parser.add_argument('--tile_index', type=int, default=-1, help='subtile for --stage tile (0-based)')

    
    args = parser.parse_args()
    if args.stage == 'tile' and args.tile_index < 0:
        parser.error('--stage tile needs --tile_index')
    args.work_dir = os.path.join(args.output_path, 'tiles')  # subtile inputs and results of a staged run
    return args

# ==========================================
# Main Execution
# ==========================================

if __name__ == '__main__':

    args = get_args()
    print(f"PYTHON_EXECUTABLE={sys.executable}", flush=True)
    print(f"PYTHON_VERSION={sys.version.split()[0]}", flush=True)
    for module_name in ("ClusterMap.clustermap", "ClusterMap.preprocessing", "ClusterMap.utils", "ClusterMap.runtime"):
        module = sys.modules.get(module_name)
        if module is not None:
            print(f"PACKAGE_ORIGIN {module_name}={module.__file__}", flush=True)
    if args.stage == 'tile':
        run_tile_stage(args)
        sys.exit()
    
    # 1. Setup Parameters
    cell_num_threshold = float(args.cell_num_threshold)
    dapi_grid_interval = args.dapi_grid_interval
    pct_filter = float(args.pct_filter)
    ref_round = args.ref_round
    use_own_dapi = True if args.extra_preprocess == 'T' else False
    sub_span = args.sub_span
    
    try:
        xy_radius = int(args.cell_radius.split(',')[0])
        z_radius = int(args.cell_radius.split(',')[1])
    except IndexError:
        print("Error: --cell_radius must be 'XY,Z'")
        sys.exit(1)
    
    # 逆时针
    ROTATION_DEG = args.rotation
    READS_FILTER = args.reads_filter
    OVERLAP_PERCENT = args.overlap_percent
    WINDOW_SIZE = sub_span
    
    os.makedirs(args.output_path, exist_ok=True)
    
    # 2. Load DAPI & Detect Dimensions
    if not os.path.exists(args.dapi_path):
        print(f"Error: DAPI file not found at {args.dapi_path}")
        sys.exit(1)

    print(f"Loading DAPI from: {args.dapi_path}")
    dapi = tiff.imread(args.dapi_path) # Load to memory
    
    # Auto-detect dimensions (Z, Y, X)
    img_z, img_r, img_c = dapi.shape
    print(f"Detected Dimensions: Z={img_z}, Y={img_r}, X={img_c}")
    
# 3. Rotate DAPI
    print(f"Rotating DAPI by {ROTATION_DEG} degrees (Clockwise)...")
    dapi_rotated = dapi.copy()
    
    if ROTATION_DEG % 90 == 0:
        k_rot = ROTATION_DEG // 90
        # k=-k_rot 是顺时针，保持不变
        dapi_rotated = np.rot90(dapi, k=-k_rot, axes=(1, 2))
    else:
        for i in tqdm(range(img_z), desc="Rotating slices"):
            # 【修改这里】：加上负号，强制 ndimage 顺时针旋转
            dapi_rotated[i, :, :] = ndimage.rotate(dapi[i, :, :], -ROTATION_DEG, reshape=False)

    # Save Max Projection
    dapi_rotate_max = dapi_rotated.max(axis=0)
    tiff.imwrite(os.path.join(args.output_path, 'max_rotated_dapi.tiff'), dapi_rotate_max)
    
    # ClusterMap usually expects (X, Y, Z) or matches spot coords
    # Assuming standard (Z, Y, X) -> Transpose to (Y, X, Z) for ClusterMap logic often used
    dapi_processed = np.transpose(dapi_rotated, (1, 2, 0))
    
    # Save Filtered DAPI Visualization
    try:
        mid_z = img_z // 2
        plt.figure(figsize=[20, 20])
        
        # plt.subplot(2, 2, 1)
        # raw_mid_rot = ndimage.rotate(dapi[mid_z, :, :], ROTATION_DEG, reshape=False)
        # plt.imshow(raw_mid_rot, cmap='gray')
        # plt.title(f"Original Rotated (Layer {mid_z})")

        # 可视化部分
        plt.subplot(2, 2, 1)
        # 【修改这里】：加上负号，使其与实际处理的数据方向一致
        raw_mid_rot = ndimage.rotate(dapi[mid_z, :, :], -ROTATION_DEG, reshape=False)
        plt.imshow(raw_mid_rot, cmap='gray')
        plt.title(f"Original Rotated (Layer {mid_z})")

        plt.subplot(2, 2, 2)
        plt.imshow(dapi_processed[:, :, mid_z], cmap='gray')
        plt.title(f"Processed DAPI (Layer {mid_z})")

        plt.subplot(2, 2, 3)
        plt.imshow(dapi_rotate_max, cmap='gray')
        plt.title("Original Max Projection")

        plt.subplot(2, 2, 4)
        plt.imshow(dapi_processed.max(axis=2), cmap='gray')
        plt.title("Processed Max Projection")
        
        plt.savefig(os.path.join(args.output_path, "filtered_dapi.png"))
        plt.close()

    except Exception as e:
        print(f"Warning: Could not save filtered_dapi.png: {e}")

    # 4. Process Transcripts (Spots)
    print(f"Loading transcripts from: {args.transcripts_file}")
    points_df = pd.read_csv(args.transcripts_file)
    print(f"Raw CSV columns: {list(points_df.columns)}")

    points_df = points_df[['x', 'y', 'z', 'Gene']]
    points_df.columns = ['column', 'row', 'z_axis', 'gene']
    
    # Rotate Spot Coordinates
    origin = [int(img_c / 2 + 0.5), int(img_r / 2 + 0.5)]
    
    if ROTATION_DEG % 360 != 0:
        xy_coords = np.array([points_df['column'], points_df['row']], dtype=int)
        rotate_cor = rotate_points(xy_coords, math.radians(ROTATION_DEG), origin)
        points_df['column'] = rotate_cor['column']
        points_df['row'] = rotate_cor['row']
    
    points_df = points_df[points_df['z_axis'] <= img_z].reset_index(drop=True)
    
    spots = pd.DataFrame({
        'gene_name': points_df['gene'],
        'spot_location_1': points_df['column'],
        'spot_location_2': points_df['row'],
        'spot_location_3': points_df['z_axis']
    })
    
    if spots.shape[0] < READS_FILTER:
        print("Not enough reads found. Exiting.")
        # Write empty
        pd.DataFrame(columns=['gene_name','spot_location_1','spot_location_2','spot_location_3','gene','is_noise','clustermap']).to_csv(os.path.join(args.output_path,'remain_reads.csv'))
        pd.DataFrame(columns=['cell_barcode','column','row','z_axis']).to_csv(os.path.join(args.output_path,'cell_center.csv'))
        sys.exit()

    unique_genes = spots['gene_name'].unique()
    gene_map_dict = {name: i + 1 for i, name in enumerate(unique_genes)}
    spots['gene'] = spots['gene_name'].map(gene_map_dict).astype(int)

    # 5. Initialize Model
    num_gene = spots['gene'].max()
    gene_list = np.arange(1, num_gene + 1)
    num_dims = len(dapi_processed.shape)
    
    use_nuclei = args.binary_source == 'cellpose'
    if args.radius_factor > 0 and not use_nuclei:
        print("Error: --radius_factor needs --binary_source cellpose")
        sys.exit(1)
    if use_nuclei:
        if use_own_dapi:
            print("Error: --binary_source cellpose needs --extra_preprocess F")
            sys.exit(1)
        if not args.nuclei_labels or not os.path.exists(args.nuclei_labels):
            print(f"Error: nuclei labels not found at {args.nuclei_labels}")
            sys.exit(1)
        nuclei_zyx = tiff.imread(args.nuclei_labels)
        if nuclei_zyx.shape != dapi.shape:
            print(f"Error: nuclei labels {nuclei_zyx.shape} do not match DAPI {dapi.shape}")
            sys.exit(1)
        nuclei_bi = nuclei_binary(nuclei_zyx, ROTATION_DEG, args.nuclei_erode, args.nuclei_zgap)
        if args.radius_factor > 0:
            nuclei = nuclei_footprints(nuclei_zyx, ROTATION_DEG, args.anisotropy)
        del nuclei_zyx
        print(f"Nuclei binary from {args.nuclei_labels}: {nuclei_bi.mean():.2%} of voxels")

    model = ClusterMap(
        spots=spots, 
        dapi=dapi_processed if not (use_own_dapi or use_nuclei) else None, 
        gene_list=gene_list, 
        num_dims=num_dims,
        xy_radius=xy_radius, 
        z_radius=z_radius,
        fast_preprocess=use_own_dapi
    )

    if use_nuclei:
        model.dapi = dapi_processed
        model.dapi_binary = nuclei_bi
        model.dapi_stacked = nuclei_bi.max(2)

    if use_own_dapi:
        dapi_bi = dapi_processed > 1 
        dapi_bi_max = dapi_bi.max(2)
        model.dapi = dapi_processed
        model.dapi_binary = dapi_bi
        model.dapi_stacked = dapi_bi_max

    model.preprocess(dapi_grid_interval=dapi_grid_interval, pct_filter=pct_filter)
    model.min_spot_per_cell = READS_FILTER
    
    # Save noise check
    model.plot_segmentation(
        figsize=(5, 5), s=0.6, method='is_noise',
        cmap=np.array(((0, 1, 0), (1, 0, 0))),
        plot_dapi=True, save=True, 
        savepath=os.path.join(args.output_path, 'cellseg_noisecheck.png')
    )

    # 6. Tiling & Segmentation
    print("Starting Tiled Segmentation...")
    img_for_split = dapi_processed
    if args.sub_num > 0:
        # split() adds a row and a column when the size divides evenly
        WINDOW_SIZE = -(-(max(dapi_processed.shape[:2]) + 1) // args.sub_num)
    label_img = get_img(img_for_split, model.spots, window_size=WINDOW_SIZE, 
                        margin=math.ceil(WINDOW_SIZE * OVERLAP_PERCENT))
    out = split(img_for_split, label_img, model.spots, window_size=WINDOW_SIZE, 
                margin=math.ceil(WINDOW_SIZE * OVERLAP_PERCENT))
    if use_nuclei:
        out['binary'] = split(nuclei_bi, label_img, model.spots, window_size=WINDOW_SIZE,
                              margin=math.ceil(WINDOW_SIZE * OVERLAP_PERCENT))['img']
    if args.radius_factor > 0:
        margin = math.ceil(WINDOW_SIZE * OVERLAP_PERCENT)
        last_row, last_col = dapi_processed.shape[0] // WINDOW_SIZE, dapi_processed.shape[1] // WINDOW_SIZE
        col = 2 if args.radius_from == 'size' else 3
        stat = np.median if args.radius_stat == 'median' else np.mean
        tile_radius = []
        for i, j in zip(out['row'], out['col']):
            v0, h0 = i * WINDOW_SIZE - margin, j * WINDOW_SIZE - margin
            v1 = v0 + WINDOW_SIZE + 2 * margin if i < last_row else np.inf
            h1 = h0 + WINDOW_SIZE + 2 * margin if j < last_col else np.inf
            inside = (nuclei[:, 0] >= v0) & (nuclei[:, 0] < v1) & (nuclei[:, 1] >= h0) & (nuclei[:, 1] < h1)
            v = nuclei[inside, col]
            v = v[np.isfinite(v)]
            tile_radius.append(int(round(args.radius_factor * stat(v) + args.radius_intercept)) if len(v) else xy_radius)
        out['xy_radius'] = tile_radius
        print(f"Per-tile xy radius: {min(tile_radius)}-{max(tile_radius)}")

    model.spots['clustermap'] = -1
                
    model_params = {
        'reads_filter': READS_FILTER,
        'cell_num_threshold': cell_num_threshold,
        'dapi_grid_interval': dapi_grid_interval,
        'use_own_dapi': use_own_dapi,
        'gene_list': gene_list,
        'num_dims': num_dims,
        'xy_radius': xy_radius,
        'z_radius': z_radius,
        'filter_value': 1,
        'binary_source': args.binary_source
    }

    if args.stage == 'prepare':
        shutil.rmtree(args.work_dir, ignore_errors=True)  # never merge results of an earlier run
        os.makedirs(args.work_dir)
        for tile_idx in range(out.shape[0]):
            row = out.loc[tile_idx].copy()
            if use_nuclei:
                row['img'] = None  # the nuclei path segments on 'binary'; ClusterMap reads dapi only for hull plots
            write_pickle({'row': row, 'params': model_params, 'pct_filter': pct_filter},
                         tile_path(args.work_dir, tile_idx, "in"))
        print(f"Prepared {out.shape[0]} tiles in {args.work_dir}")
        sys.exit()

    if args.stage == 'merge':
        print(f"Stitching {out.shape[0]} tile results from {args.work_dir}...")
    else:
        # 单线程版本 - 使用 for 循环替代 ProcessPoolExecutor
        print(f"Processing {out.shape[0]} tiles sequentially...")

    for tile_idx in tqdm(range(out.shape[0]), desc="Processing Tiles"):
        try:
            # 直接调用 process_tile 函数；merge 读 tile 阶段的结果
            if args.stage == 'merge':
                result = load_tile_result(args.work_dir, tile_idx)
            else:
                result = process_tile(tile_idx, out=out, model_params=model_params)

            if result is not None:
                model.stitch(result, out, tile_idx)
            else:
                print(f"Warning: Tile {tile_idx} returned None result")

        except Exception as e:
            print(f"Failed tile {tile_idx}: {e}")
            sys.exit(1)

    # 7. Final Output
    if not hasattr(model, 'all_points_cellid') or len(model.cellid_unique) == 0:
        print("No cells found.")
        # Create empty files to prevent pipeline crashes
        pd.DataFrame().to_csv(os.path.join(args.output_path, 'remain_reads.csv'))
        pd.DataFrame().to_csv(os.path.join(args.output_path, 'cell_center.csv'))
        sys.exit()

    # Save Image
    plt.figure()
    model.plot_segmentation(figsize=(10, 10), s=3, plot_with_dapi=True, plot_dapi=True, show=False)
    if hasattr(model, 'cellcenter_unique') and len(model.cellcenter_unique) > 0:
        plt.scatter(model.cellcenter_unique[:, 1], model.cellcenter_unique[:, 0], c='r', s=5)
    plt.savefig(os.path.join(args.output_path, 'cellseg_result.png'))
    plt.close()

    # Save CSVs
    model.spots['clustermap'] = model.spots['clustermap'].astype(int)
    remain_reads = model.spots.loc[model.spots['clustermap'] >= 0, :].reset_index(drop=True)
    remain_reads_raw = model.spots.reset_index(drop=True)
    remain_reads_raw.to_csv(os.path.join(args.output_path, 'remain_reads_raw.csv'), index=False)

    cell_center_df = pd.DataFrame({
        'cell_barcode': model.cellid_unique.astype(int),
        'x': model.cellcenter_unique[:, 1],
        'y': model.cellcenter_unique[:, 0],
        'z': model.cellcenter_unique[:, 2]
    })
    
    remain_reads.to_csv(os.path.join(args.output_path, 'remain_reads.csv'))
    cell_center_df.to_csv(os.path.join(args.output_path, 'cell_center.csv'))
    
    # Save Final Segmentation Visualization
    try:
        if remain_reads.shape[0] > 0:
            cmap = np.random.rand(int(max(remain_reads['clustermap']) + 1), 3)

            if hasattr(model, 'dapi_binary') and model.dapi_binary is not None:
                binary_dapi = model.dapi_binary
            else:
                binary_dapi = dapi_processed > 1

            if len(binary_dapi.shape) == 3:
                binary_dapi_proj = binary_dapi.max(2)
            else:
                binary_dapi_proj = binary_dapi

            binary_dapi_proj = np.flipud(binary_dapi_proj)
            s = 5

            plt.figure(figsize=[20, 20])
            
            # Panel 1: DAPI Max Proj
            plt.subplot(2, 2, 1)
            plt.imshow(dapi_rotate_max, cmap='gray')
            plt.title('DAPI (Max Projection)', fontsize=15)
            
            # Panel 2: DAPI Mid Slice
            plt.subplot(2, 2, 2)
            plt.imshow(dapi_processed[:, :, img_z // 2], cmap='gray')
            plt.title(f'DAPI (Layer {img_z // 2})', fontsize=15)
            
            # Panel 3: DAPI + Colored Spots + Centers
            plt.subplot(2, 2, 3)
            plt.imshow(dapi_rotate_max, cmap='gray')
            plt.scatter(remain_reads['spot_location_1'], remain_reads['spot_location_2'], 
                        c=cmap[[int(x) for x in remain_reads['clustermap']]], s=s, alpha=0.1)
            plt.scatter(model.cellcenter_unique[:, 1], model.cellcenter_unique[:, 0], c='red', s=20)
            plt.title(f'DAPI + ClusterMap Result (Cells: {len(model.cellcenter_unique)})', fontsize=15)
            
            # Panel 4: Binary Mask + Spots
            plt.subplot(2, 2, 4)
            plt.imshow(binary_dapi_proj, origin='lower', cmap='gray')
            plt.scatter(remain_reads['spot_location_1'], binary_dapi_proj.shape[0] - remain_reads['spot_location_2'],
                        c=cmap[[int(x) for x in remain_reads['clustermap']]], s=s, alpha=0.1)
            plt.scatter(model.cellcenter_unique[:, 1], binary_dapi_proj.shape[0] - model.cellcenter_unique[:, 0],
                        c='red', s=20)
            plt.title('Binary DAPI + ClusterMap Result', fontsize=15)
            
            plt.savefig(os.path.join(args.output_path, 'final_segmentation_results.png'))
            plt.close()
    except Exception as e:
        print(f"Warning: Could not save final_segmentation_results.png: {e}")

    # Save Clustermap Segmentation
    try:
        model.plot_segmentation(figsize=(30, 15), s=0.05, plot_with_dapi=True, plot_dapi=True, show=False)
        plt.savefig(os.path.join(args.output_path, 'clustermap_segmentation.png'))
        plt.close()
    except Exception as e:
        print(f"Warning: Could not save clustermap_segmentation.png: {e}")

    print("ClusterMap Segmentation Complete.")
