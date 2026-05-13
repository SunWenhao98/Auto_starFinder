#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, math, json, gc, argparse, re, time
import numpy as np
import pandas as pd
import tifffile as tif
from scipy import ndimage
import joblib
from typing import Optional, Any, Tuple

from ClusterMap.clustermap import ClusterMap
from ClusterMap.utils import get_img, split


# =========================================================
# speed patch: replace add_dapi_points() heavy voxel-scan
# =========================================================
def _cm_add_dapi_points_fast(dapi_binary, dapi_grid_interval, spots_denoised, ngc, num_dims):
    try:
        from sklearn.neighbors import NearestNeighbors
    except Exception as e:
        raise ImportError("scikit-learn is required for add_dapi_points_fast (NearestNeighbors)") from e

    g = int(dapi_grid_interval) if int(dapi_grid_interval) > 0 else 1

    if num_dims == 3:
        sampled = np.asarray(dapi_binary)[::g, ::g, ::g]
        dapi_coord = np.argwhere(sampled > 0).astype(np.int32)
        if dapi_coord.size == 0:
            spots_coord = spots_denoised.loc[:, ['spot_location_2', 'spot_location_1', 'spot_location_3']].to_numpy()
            return spots_coord, ngc
        dapi_coord *= g
        spots_coord = spots_denoised.loc[:, ['spot_location_2', 'spot_location_1', 'spot_location_3']].to_numpy()
    else:
        sampled = np.asarray(dapi_binary)[::g, ::g]
        dapi_coord = np.argwhere(sampled > 0).astype(np.int32)
        if dapi_coord.size == 0:
            spots_coord = spots_denoised.loc[:, ['spot_location_2', 'spot_location_1']].to_numpy()
            return spots_coord, ngc
        dapi_coord *= g
        spots_coord = spots_denoised.loc[:, ['spot_location_2', 'spot_location_1']].to_numpy()

    knn = NearestNeighbors(n_neighbors=1)
    knn.fit(spots_coord)
    neigh_ind = knn.kneighbors(dapi_coord, 1, return_distance=False)
    dapi_ngc = ngc[neigh_ind[:, 0]]

    all_ngc = np.concatenate((ngc, dapi_ngc), axis=0)
    all_coord = np.concatenate((spots_coord, dapi_coord), axis=0)
    return all_coord, all_ngc


# apply monkeypatch
try:
    import ClusterMap.clustermap as _cm_clustermap_mod
    _cm_clustermap_mod.add_dapi_points = _cm_add_dapi_points_fast
except Exception:
    pass
try:
    import ClusterMap.utils as _cm_utils_mod
    _cm_utils_mod.add_dapi_points = _cm_add_dapi_points_fast
except Exception:
    pass


# =========================================================
# helpers
# =========================================================
def _dbg_enabled() -> bool:
    return os.environ.get("CM_DEBUG", "0") not in ("0", "F", "False", "false", "")

def _dbg(msg: str):
    if _dbg_enabled():
        print(msg, flush=True)

def _parse_icr(icr_str: str) -> Tuple[int, int]:
    s = (icr_str or "").strip()
    if s == "":
        raise ValueError("-ICR is empty")
    if "," in s:
        a, b = s.split(",", 1)
    else:
        parts = re.split(r"[\s;:_/]+", s)
        parts = [p for p in parts if p != ""]
        if len(parts) < 2:
            raise ValueError(f"-ICR must be like 'xy,z' (e.g. 45,10); got: {icr_str!r}")
        a, b = parts[0], parts[1]
    return int(float(a)), int(float(b))

def _ensure_dir(pth: str):
    os.makedirs(pth, exist_ok=True)
    return pth

def _manifest_path(work_dir: str):
    return os.path.join(work_dir, "manifest.json")

def _tile_dir(work_dir: str):
    return os.path.join(work_dir, "tiles")

def _tile_results_dir(work_dir: str):
    return os.path.join(work_dir, "tile_results")

def _tile_npz_path(work_dir: str, tid: int):
    return os.path.join(_tile_dir(work_dir), f"tile_{tid:05d}.npz")

def _tile_spots_path(work_dir: str, tid: int):
    return os.path.join(_tile_dir(work_dir), f"tile_{tid:05d}_spots.csv")

def _tile_out_path(work_dir: str, tid: int):
    return os.path.join(_tile_results_dir(work_dir), f"tile_{tid:05d}.pkl")

def _out_pkl_path(work_dir: str):
    return os.path.join(work_dir, "out.pkl")

def _atomic_joblib_dump(obj, path: str, compress=3):
    tmp = path + ".tmp"
    joblib.dump(obj, tmp, compress=compress)
    os.replace(tmp, path)

def _write_manifest(work_dir: str, d: dict):
    with open(_manifest_path(work_dir), "w") as f:
        json.dump(d, f, indent=2)

def _read_manifest(work_dir: str):
    with open(_manifest_path(work_dir), "r") as f:
        return json.load(f)

def _global_spots_path(work_dir: str):
    return os.path.join(work_dir, "global_spots.pkl")

def _save_global_spots(work_dir: str, df: pd.DataFrame):
    _atomic_joblib_dump(df, _global_spots_path(work_dir), compress=3)

def _load_global_spots(work_dir: str) -> Optional[pd.DataFrame]:
    p = _global_spots_path(work_dir)
    if not os.path.exists(p):
        return None
    try:
        df = joblib.load(p)
        return df if isinstance(df, pd.DataFrame) else None
    except Exception:
        return None


# =========================================================
# GLOBAL SPOT ID RULE (IMPORTANT)
#   - We ONLY use column 'index' produced by utils.split(reset_index())
#   - We DO NOT create/use orig_idx anymore
#   - For .loc[...] in stitch to work:
#       self.spots.index must contain ALL global ids
#       and out[tile].spots['index'] are those ids
# =========================================================
def _ensure_global_id(df: pd.DataFrame, id_col: str = "index") -> pd.DataFrame:
    """
    Ensure:
      - df has column 'index' (global spot id)
      - df['index'] is int64
      - df.index equals df['index'] BUT index.name = None (avoid reset_index collisions)
      - within a df, duplicate index removed (keep first)
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.shape[0] == 0:
        return df

    df = df.copy()

    if id_col not in df.columns:
        # fall back: use current index values
        df[id_col] = pd.to_numeric(df.index, errors="coerce")
    df[id_col] = pd.to_numeric(df[id_col], errors="coerce").astype(np.int64)

    df.index = df[id_col].to_numpy(dtype=np.int64)
    df.index.name = None

    if not df.index.is_unique:
        df = df[~df.index.duplicated(keep="first")].copy()

    return df


def _save_tile_spots_csv(spots_tile: pd.DataFrame, csv_path: str):
    """
    Save tile spots as csv; must include column 'index' as global id.
    """
    if spots_tile is None or spots_tile.shape[0] == 0:
        pd.DataFrame().to_csv(csv_path, index=False)
        return
    if "index" not in spots_tile.columns:
        raise RuntimeError(f"[prep] tile spots missing required column 'index' -> cannot stitch later.")
    spots_tile.to_csv(csv_path, index=False)


def _read_tile_spots_csv(csv_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return pd.DataFrame()
    if df.shape[0] == 0:
        return df
    return _ensure_global_id(df, "index")


def _load_tile_inputs(work_dir: str, tid: int):
    npz = np.load(_tile_npz_path(work_dir, tid), allow_pickle=True)
    dapi_tile = npz["dapi"]
    # label_img may or may not exist depending on old prep; stitch prefers out.pkl anyway
    label_img_tile = npz["label_img"] if "label_img" in npz.files else None
    spots_tile = _read_tile_spots_csv(_tile_spots_path(work_dir, tid))
    return dapi_tile, label_img_tile, spots_tile


def _save_tile_result(work_dir: str, tid: int, model_tile):
    _ensure_dir(_tile_results_dir(work_dir))
    joblib.dump(model_tile, _tile_out_path(work_dir, tid), compress=3)


def _load_out_pkl(work_dir: str) -> Optional[pd.DataFrame]:
    p = _out_pkl_path(work_dir)
    if not os.path.exists(p):
        return None
    try:
        out = joblib.load(p)
        if isinstance(out, pd.DataFrame):
            return out
    except Exception:
        return None
    return None


def _reconstruct_out_minimal(work_dir: str, n_tiles: int) -> pd.DataFrame:
    """
    Minimal out builder when out.pkl is missing/broken.
    NOTE: label_img likely missing unless saved per tile npz.
    """
    rows = []
    for tid in range(n_tiles):
        npz_path = _tile_npz_path(work_dir, tid)
        sp_path = _tile_spots_path(work_dir, tid)
        if not (os.path.exists(npz_path) and os.path.exists(sp_path)):
            rows.append({"img": None, "spots": pd.DataFrame(), "label_img": None})
            continue
        npz = np.load(npz_path, allow_pickle=True)
        dapi_tile = npz["dapi"] if "dapi" in npz.files else None
        label_img_tile = npz["label_img"] if "label_img" in npz.files else None
        spots_tile = _read_tile_spots_csv(sp_path)
        rows.append({"img": dapi_tile, "spots": spots_tile, "label_img": label_img_tile})
    return pd.DataFrame(rows)


def _build_global_spots_from_out(out: pd.DataFrame, n_tiles: int) -> pd.DataFrame:
    """
    Union all tile spots into ONE global spots table:
      - concat all out[t].spots
      - drop duplicates by 'index'
      - ensure index aligned to 'index'
    NOTE: out[t].spots may be TILE-LOCAL coordinates; keep this function for fallback/diagnostics only.
    """
    all_list = []
    for tid in range(n_tiles):
        s = out.loc[tid, "spots"] if tid < out.shape[0] and "spots" in out.columns else None
        if isinstance(s, pd.DataFrame) and s.shape[0] > 0:
            if "index" not in s.columns:
                raise RuntimeError(f"[stitch] out[{tid}].spots missing column 'index' (global id).")
            all_list.append(s)

    if len(all_list) == 0:
        return pd.DataFrame()

    g = pd.concat(all_list, axis=0, ignore_index=True)
    g["index"] = pd.to_numeric(g["index"], errors="coerce").astype(np.int64)
    g = g.dropna(subset=["index"]).copy()
    g = g.drop_duplicates(subset=["index"], keep="first").copy()
    g = _ensure_global_id(g, "index")

    # columns used later by stitch writing
    if "clustermap" not in g.columns:
        g["clustermap"] = -1
    for cc in ("cell_center_0", "cell_center_1", "cell_center_2"):
        if cc not in g.columns:
            g[cc] = -1

    return g


def _init_global_cols(spots_df: pd.DataFrame) -> pd.DataFrame:
    """
    Initialize accumulator columns to avoid NaN oceans:
      - clustermap: int64, default -1
      - cell_center_0/1/2: int64, default -1
      - is_noise: keep if exists else 0
    """
    if spots_df is None or not isinstance(spots_df, pd.DataFrame) or spots_df.shape[0] == 0:
        return spots_df
    spots_df = spots_df.copy()
    if "clustermap" not in spots_df.columns:
        spots_df["clustermap"] = -1
    spots_df["clustermap"] = pd.to_numeric(spots_df["clustermap"], errors="coerce").fillna(-1).astype(np.int64)

    for cc in ("cell_center_0", "cell_center_1", "cell_center_2"):
        if cc not in spots_df.columns:
            spots_df[cc] = -1
        spots_df[cc] = pd.to_numeric(spots_df[cc], errors="coerce").fillna(-1).astype(np.int64)

    if "is_noise" in spots_df.columns:
        # keep original dtype if possible, but ensure no NaN
        spots_df["is_noise"] = pd.to_numeric(spots_df["is_noise"], errors="coerce").fillna(0).astype(np.int64)

    return spots_df


def _writeback_tile_to_acc(model_acc, tile_model, tid: int):
    """
    Force-write tile assignments into accumulator global spots via global id 'index'.
    This makes the pipeline robust to ClusterMap.stitch() implementations that
    don't persist clustermap/centers back into model_acc.spots.
    """
    acc_spots = getattr(model_acc, "spots", None)
    ts = getattr(tile_model, "spots", None)
    if not isinstance(acc_spots, pd.DataFrame):
        print(f"[stitch][WB][WARN] tid={tid}: accumulator has no spots df", flush=True)
        return
    if not isinstance(ts, pd.DataFrame) or ("index" not in ts.columns):
        print(f"[stitch][WB][WARN] tid={tid}: tile spots missing df/index, skip writeback", flush=True)
        return

    # ids must be int64
    ids = pd.to_numeric(ts["index"], errors="coerce")
    ids = ids[ids.notna()].astype(np.int64).to_numpy()
    if ids.size == 0:
        print(f"[stitch][WB][WARN] tid={tid}: no valid ids", flush=True)
        return

    # clustermap
    if "clustermap" in ts.columns:
        tcm = pd.to_numeric(ts["clustermap"], errors="coerce").fillna(-1).astype(np.int64).to_numpy()
        model_acc.spots.loc[ids, "clustermap"] = tcm

    # centers (optional)
    for cc in ("cell_center_0", "cell_center_1", "cell_center_2"):
        if cc in ts.columns:
            v = pd.to_numeric(ts[cc], errors="coerce").fillna(-1).astype(np.int64).to_numpy()
            model_acc.spots.loc[ids, cc] = v

    # is_noise (optional)
    if "is_noise" in ts.columns:
        v = pd.to_numeric(ts["is_noise"], errors="coerce").fillna(0).astype(np.int64).to_numpy()
        model_acc.spots.loc[ids, "is_noise"] = v

    # small progress stats
    acc_cm = pd.to_numeric(model_acc.spots["clustermap"], errors="coerce")
    acc_pos = int((acc_cm >= 0).sum())
    tile_pos = None
    if "clustermap" in ts.columns:
        tile_pos = int((pd.to_numeric(ts["clustermap"], errors="coerce").fillna(-1) >= 0).sum())
    print(f"[stitch][WB] tile{tid}: ids={ids.size} tile_cm>=0={tile_pos} acc_cm>=0={acc_pos}", flush=True)


# =========================================================
# CLI
# =========================================================
def command_args():
    p = argparse.ArgumentParser("clustermap distributed (prep/tile/stitch)")
    p.add_argument('-IP', '--input_position', type=str, required=True)
    p.add_argument('-IZ', '--input_imgZ', type=int, required=True)
    p.add_argument('-IC', '--input_cell_num_threshold', type=str, required=True)
    p.add_argument('-ID', '--input_dapi_grid_interval', type=int, required=True)
    p.add_argument('-ICR', '--input_cell_radius', type=str, required=True)
    p.add_argument('-IXY', '--input_XY', type=int, required=True)
    p.add_argument('-IDR', '--input_dapi_round', type=int, required=True)
    p.add_argument('-IPF', '--input_pct_filter', type=str, required=True)
    p.add_argument('-IEP', '--input_extra_preprocess', choices=['T', 'F'], required=True)
    p.add_argument('-IDir', '--input_dir', type=str)
    p.add_argument('-Igenecsv', '--input_gene_csv', type=str)
    p.add_argument('-IDapi_path', '--IDapi_path', type=str)
    p.add_argument('-IDN', '--input_dapi_num', type=int, required=True)
    p.add_argument('-Igood_points_max3d', '--Igood_points_max3d', type=str)

    # NEW: Added rotation and reads_filter controls
    p.add_argument('--rotation', type=int, default=270, help='Left rotation angle for DAPI and Spots')
    p.add_argument('--reads_filter', type=int, default=5, help='Minimum spots to form a cell')
    p.add_argument('-OP', '--output_path', type=str)

    p.add_argument('--stage', choices=['prep', 'tile', 'stitch'], required=True)
    p.add_argument('--work_dir', type=str, required=True)
    p.add_argument('--window_size', type=int, default=400)
    p.add_argument('--overlap_percent', type=float, default=0.2)
    p.add_argument('--tile_id', type=int, default=None)
    p.add_argument('--stitch_strict_fail', choices=['T', 'F'], default='T')

    # Compatibility: old bash might pass this
    p.add_argument('--stitch_load_full_dapi', choices=['T', 'F'], default='F')
    
    # NEW: Optional output features
    p.add_argument('--export_polygons', choices=['T', 'F'], default='F', help='Export cell polygons to JSON')
    p.add_argument('--export_qc_plots', choices=['T', 'F'], default='F', help='Export final segmentation QC plots')

    return p.parse_args()


# =========================================================
# stages
# =========================================================
def _stage_prep(args):
    work_dir = _ensure_dir(args.work_dir)
    _ensure_dir(_tile_dir(work_dir))
    _ensure_dir(_tile_results_dir(work_dir))
    _ensure_dir(args.output_path)

    req_img_z = int(args.input_imgZ)
    cell_num_threshold = float(args.input_cell_num_threshold)
    dapi_grid_interval = int(args.input_dapi_grid_interval)
    pct_filter = float(args.input_pct_filter)
    img_c = int(args.input_XY)
    img_r = int(args.input_XY)
    xy_radius, z_radius = _parse_icr(args.input_cell_radius)

    useown_dapi_bi = (args.input_extra_preprocess == 'T')

    left_rotation = int(args.rotation)
    reads_filter = int(args.reads_filter)
    overlap_percent = float(args.overlap_percent)
    window_size = int(args.window_size)

    # NEW: Flexible DAPI path handling
    if os.path.isfile(args.IDapi_path):
        dapi_path = args.IDapi_path
    elif os.path.isdir(args.IDapi_path):
        input_dapi_name = 'ch0' + str(args.input_dapi_num - 1) + '.tif'
        dapi_path = ''
        for fn in os.listdir(args.IDapi_path):
            if fn.endswith(input_dapi_name):
                dapi_path = os.path.join(args.IDapi_path, fn)
                break
        if not dapi_path or not os.path.exists(dapi_path):
            raise FileNotFoundError(f"Cannot find {input_dapi_name} under {args.IDapi_path}")
    else:
        raise FileNotFoundError(f"Invalid DAPI path: {args.IDapi_path}")

    print(f"[prep] DAPI file: {dapi_path}")
    dapi0 = tif.imread(dapi_path)
    img_z = min(req_img_z, dapi0.shape[0])
    dapi = dapi0[:img_z, :, :]
    print(f"[prep] DAPI shape(raw)={dapi0.shape}, use Z={img_z}")
    del dapi0
    gc.collect()

    rot_order = int(os.environ.get("CM_ROTATE_ORDER", "1"))
    dapi_rot = ndimage.rotate(dapi, left_rotation, axes=(1, 2), reshape=False, order=rot_order)
    if np.issubdtype(dapi.dtype, np.integer):
        dapi_rot = np.clip(dapi_rot, np.iinfo(dapi.dtype).min, np.iinfo(dapi.dtype).max).astype(dapi.dtype, copy=False)
    dapi_f2 = np.transpose(dapi_rot, (1, 2, 0))

    # =========================================================
    # NEW: write rotated DAPI max projection for later FIJI stitching
    # =========================================================
    try:
        # dapi_rot is (Z, Y, X) after rotation; max over Z gives (Y, X)
        dapi_rotate_max = np.max(dapi_rot, axis=0)

        # IMPORTANT: avoid int8/signed byte TIFF (can appear as 128-gray everywhere)
        # Keep same bit depth if already uint16/uint8; otherwise cast safely.
        if dapi_rotate_max.dtype == np.int8 or np.issubdtype(dapi_rotate_max.dtype, np.signedinteger):
            # If it is signed, cast to uint16 to be safe
            dapi_rotate_max_u = dapi_rotate_max.astype(np.int32)
            dapi_rotate_max_u = np.clip(dapi_rotate_max_u, 0, 65535).astype(np.uint16)
        elif dapi_rotate_max.dtype == np.uint8:
            dapi_rotate_max_u = dapi_rotate_max
        elif dapi_rotate_max.dtype == np.uint16:
            dapi_rotate_max_u = dapi_rotate_max
        else:
            # float etc -> scale/clip to uint16 conservatively
            dapi_rotate_max_u = np.clip(dapi_rotate_max, 0, np.nanmax(dapi_rotate_max)).astype(np.float32)
            dapi_rotate_max_u = np.clip(dapi_rotate_max_u, 0, 65535).astype(np.uint16)

        out_max_path = os.path.join(args.output_path, "max_rotated_dapi.tif")
        tif.imwrite(
            out_max_path,
            dapi_rotate_max_u,
            photometric="minisblack",
            bigtiff=False,
        )
        print(f"[prep] wrote max_rotated_dapi.tif: {out_max_path} "
              f"shape={dapi_rotate_max_u.shape} dtype={dapi_rotate_max_u.dtype} "
              f"min={int(dapi_rotate_max_u.min())} max={int(dapi_rotate_max_u.max())}")
    except Exception as e:
        print(f"[prep] WARN: failed to write max_rotated_dapi.tif: {e}", flush=True)

    del dapi, dapi_rot
    gc.collect()

    points_df_t = pd.read_csv(args.Igood_points_max3d)
    
    # 兼容原版的7列多属性CSV：只提取我们需要的空间坐标和基因名
    points_df_t = points_df_t[['x', 'y', 'z', 'Gene']]
    points_df_t.columns = ['column', 'row', 'z_axis', 'gene']

    # NEW: Preserve original gene tags (like _rbRNA, _ntRNA) and strip them for core engine
    points_df_t['original_gene'] = points_df_t['gene']
    points_df_t['gene'] = points_df_t['gene'].astype(str).str.replace(r'_(rb|nt)RNA$', '', regex=True)

    if left_rotation % 360 != 0:
        radians = math.radians(left_rotation)
        offset_x = int(img_c / 2 + 0.5)
        offset_y = int(img_r / 2 + 0.5)
        x = points_df_t['column'].to_numpy(dtype=np.float64)
        y = points_df_t['row'].to_numpy(dtype=np.float64)
        adjusted_x = x - offset_x
        adjusted_y = y - offset_y
        cos_rad = math.cos(radians)
        sin_rad = math.sin(radians)
        qx = offset_x + cos_rad * adjusted_x + sin_rad * adjusted_y
        qy = offset_y + -sin_rad * adjusted_x + cos_rad * adjusted_y
        points_df_t["column"] = (qx + 0.5).astype(np.int32)
        points_df_t["row"] = (qy + 0.5).astype(np.int32)

    points_df_t = points_df_t.loc[points_df_t['z_axis'] <= img_z, :].copy()
    points_df_t.reset_index(drop=True, inplace=True)

    spots = pd.DataFrame({
        'original_gene': points_df_t['original_gene'],
        'gene_name': points_df_t['gene'],
        'spot_location_1': points_df_t['column'],
        'spot_location_2': points_df_t['row'],
        'spot_location_3': points_df_t['z_axis']
    })

    genes = pd.DataFrame(spots['gene_name'].unique())
    at1 = list(genes[0])
    gene = list(map(lambda x: at1.index(x) + 1, spots['gene_name']))
    spots['gene'] = np.array(gene, dtype=int)

    num_gene = int(np.max(spots['gene'])) if spots.shape[0] > 0 else 0
    gene_list = np.arange(1, num_gene + 1) if num_gene > 0 else np.array([], dtype=int)
    num_dims = 3

    filter_value2 = 1
    if useown_dapi_bi:
        model = ClusterMap(spots=spots, dapi=None, gene_list=gene_list, num_dims=num_dims,
                           xy_radius=xy_radius, z_radius=z_radius,
                           fast_preprocess=True, gauss_blur=True)
        dapi_bi = dapi_f2 > filter_value2
        dapi_bi_max = dapi_bi.max(2)
        model.dapi, model.dapi_binary, model.dapi_stacked = [dapi_f2, dapi_bi, dapi_bi_max]
    else:
        model = ClusterMap(spots=spots, dapi=dapi_f2, gene_list=gene_list, num_dims=num_dims,
                           xy_radius=xy_radius, z_radius=z_radius,
                           fast_preprocess=False)

    model.preprocess(dapi_grid_interval=dapi_grid_interval, pct_filter=pct_filter)
    model.spots['is_noise'] = model.spots['is_noise'] + 1
    model.spots['is_noise'] = model.spots['is_noise'] - min(model.spots['is_noise']) - 1
    model.min_spot_per_cell = reads_filter

    # IMPORTANT: do NOT create orig_idx. Keep index.name None.
    model.spots = model.spots.copy()
    model.spots.index.name = None

    # Save FULL-image global spots (GLOBAL coords) before split
    model.spots.index = np.arange(model.spots.shape[0], dtype=np.int64)
    model.spots.index.name = None
    global_spots_full = model.spots.copy()
    global_spots_full.insert(0, "index", global_spots_full.index.to_numpy(dtype=np.int64))
    global_spots_full = _ensure_global_id(global_spots_full, "index")
    _save_global_spots(work_dir, global_spots_full)
    print(f"[prep] wrote global_spots (FULL coords): {_global_spots_path(work_dir)}")

    margin = math.ceil(window_size * overlap_percent)
    label_img = get_img(dapi_f2, model.spots, window_size=window_size, margin=margin)
    out = split(dapi_f2, label_img, model.spots, window_size=window_size, margin=margin)
    n_tiles = int(out.shape[0])
    print(f"[prep] n_tiles={n_tiles} window_size={window_size} overlap={overlap_percent} margin={margin}")
    print(f"[prep] out.columns={list(out.columns)} (must include img/spots/label_img)")

    # Save per-tile inputs
    for tid in range(n_tiles):
        dapi_tile = out.loc[tid, 'img']
        label_img_tile = out.loc[tid, 'label_img']
        spots_tile = out.loc[tid, 'spots']

        if not isinstance(spots_tile, pd.DataFrame) or spots_tile.shape[0] == 0:
            np.savez_compressed(_tile_npz_path(work_dir, tid), dapi=dapi_tile, label_img=label_img_tile)
            _save_tile_spots_csv(pd.DataFrame(), _tile_spots_path(work_dir, tid))
            continue

        if "index" not in spots_tile.columns:
            raise RuntimeError(f"[prep] tile {tid} spots missing 'index'. split() must reset_index().")

        spots_tile = _ensure_global_id(spots_tile, "index")

        if _dbg_enabled() and tid < 3:
            _dbg(f"[DBG] [prep] tile{tid}.spots(saved): shape={spots_tile.shape} cols={list(spots_tile.columns)}")
            _dbg(f"[DBG] [prep] tile{tid}.spots(saved): index(min,max)=({spots_tile.index.min()},{spots_tile.index.max()}) unique={spots_tile.index.is_unique}")
            _dbg(f"[DBG] [prep] tile{tid}.spots(saved): col[index](min,max)=({spots_tile['index'].min()},{spots_tile['index'].max()})")
            _dbg(str(spots_tile.head(3)))

        np.savez_compressed(_tile_npz_path(work_dir, tid), dapi=dapi_tile, label_img=label_img_tile)
        _save_tile_spots_csv(spots_tile, _tile_spots_path(work_dir, tid))

    # Save out.pkl (contains label_img; img might be large but you can blank it to save space)
    try:
        out_light = out.copy()
        if "img" in out_light.columns:
            out_light["img"] = None
        _atomic_joblib_dump(out_light, _out_pkl_path(work_dir), compress=3)
        print(f"[prep] wrote light out.pkl: {_out_pkl_path(work_dir)}")
    except Exception as e:
        print(f"[prep] WARN: failed writing out.pkl: {e}")

    manifest = {
        "n_tiles": n_tiles,
        "window_size": window_size,
        "overlap_percent": overlap_percent,
        "margin": int(margin),
        "img_z": img_z,
        "left_rotation": left_rotation,
        "reads_filter": reads_filter,
        "useown_dapi_bi": bool(useown_dapi_bi),
        "filter_value2": int(filter_value2),
        "xy_radius": int(xy_radius),
        "z_radius": int(z_radius),
        "cell_num_threshold": float(cell_num_threshold),
        "dapi_grid_interval": int(dapi_grid_interval),
        "pct_filter": float(pct_filter),
        "global_id_col": "index",
    }
    _write_manifest(work_dir, manifest)
    print(f"[prep] wrote manifest: {_manifest_path(work_dir)}")

    del label_img, out, dapi_f2, spots, model
    gc.collect()
    print("[prep] done")


def _stage_tile(args):
    work_dir = args.work_dir
    manifest = _read_manifest(work_dir)

    tid = int(args.tile_id)
    n_tiles = int(manifest["n_tiles"])
    if tid >= n_tiles:
        print(f"[tile] tid={tid} >= n_tiles={n_tiles}, exit")
        return

    cell_num_threshold = float(args.input_cell_num_threshold)
    dapi_grid_interval = int(args.input_dapi_grid_interval)
    xy_radius, z_radius = _parse_icr(args.input_cell_radius)
    useown_dapi_bi = (args.input_extra_preprocess == 'T')
    filter_value2 = int(manifest.get("filter_value2", 1))
    num_dims = 3

    dapi_tile, _label_img_tile, spots_tile = _load_tile_inputs(work_dir, tid)

    reads_filter = int(manifest.get("reads_filter", 5))
    if spots_tile is None or spots_tile.shape[0] < reads_filter:
        _save_tile_result(work_dir, tid, None)
        print(f"[tile] tid={tid}: spots<{reads_filter}, save None")
        return

    # Must carry 'index' column
    if "index" not in spots_tile.columns:
        _save_tile_result(work_dir, tid, None)
        print(f"[tile] tid={tid}: FAILED (tile spots missing column 'index'), saved None")
        return

    # Gene list
    num_gene = int(np.max(spots_tile['gene'])) if 'gene' in spots_tile.columns and spots_tile.shape[0] > 0 else 0
    gene_list = np.arange(1, num_gene + 1) if num_gene > 0 else np.array([], dtype=int)

    # CRITICAL FIX: Reset the pandas index to 0..N-1 so ClusterMap internal matrix indexing doesn't crash!
    # (The global IDs remain safely encoded inside the 'index' column for stitching later)
    spots_tile = spots_tile.reset_index(drop=True)

    try:
        if useown_dapi_bi:
            model_tile = ClusterMap(spots=spots_tile, dapi=None, gene_list=gene_list, num_dims=num_dims,
                                    xy_radius=xy_radius, z_radius=z_radius,
                                    fast_preprocess=True, gauss_blur=True)
            dapi_bi_tile = dapi_tile > filter_value2
            dapi_bi_max_tile = dapi_bi_tile.max(2)
            model_tile.dapi = dapi_tile
            model_tile.dapi_binary = dapi_bi_tile
            model_tile.dapi_stacked = dapi_bi_max_tile
        else:
            model_tile = ClusterMap(spots=spots_tile, dapi=dapi_tile, gene_list=gene_list, num_dims=num_dims,
                                    xy_radius=xy_radius, z_radius=z_radius,
                                    fast_preprocess=False)
            # NEW: Restore the local thresholding missing from the distributed rewrite
            model_tile.preprocess(dapi_grid_interval=dapi_grid_interval, pct_filter=float(args.input_pct_filter))

        model_tile.min_spot_per_cell = reads_filter
        model_tile.segmentation(
            cell_num_threshold=cell_num_threshold,
            dapi_grid_interval=dapi_grid_interval,
            add_dapi=True,
            use_genedis=True
        )

        # Ensure model_tile.spots still has global id 'index'
        if hasattr(model_tile, "spots") and isinstance(model_tile.spots, pd.DataFrame):
            if "index" not in model_tile.spots.columns:
                model_tile.spots["index"] = pd.to_numeric(model_tile.spots.index, errors="coerce").astype(np.int64)
            model_tile.spots = _ensure_global_id(model_tile.spots, "index")

        _save_tile_result(work_dir, tid, model_tile)
        print(f"[tile] tid={tid}: done + saved")
    except Exception as e:
        _save_tile_result(work_dir, tid, None)
        print(f"[tile] tid={tid}: FAILED ({e}), saved None")
    finally:
        del dapi_tile, spots_tile
        gc.collect()


def _stage_stitch(args):
    work_dir = args.work_dir
    manifest = _read_manifest(work_dir)
    n_tiles = int(manifest["n_tiles"])
    print(f"[stitch] n_tiles={n_tiles}")

    # -------- 0) load out (need label_img) --------
    out = _load_out_pkl(work_dir)
    if out is None:
        print("[stitch] WARN: out.pkl missing/unreadable -> reconstruct minimal out from tiles.")
        out = _reconstruct_out_minimal(work_dir, n_tiles)

    if not isinstance(out, pd.DataFrame) or ("label_img" not in out.columns):
        raise RuntimeError("[stitch] out missing 'label_img'. Need out.pkl from prep OR tile npz with label_img.")
    if "spots" not in out.columns:
        raise RuntimeError("[stitch] out missing 'spots' column.")

    # normalize out[t].spots global id dtype (for stitch internal locating)
    for tid in range(min(n_tiles, out.shape[0])):
        s = out.loc[tid, "spots"]
        if isinstance(s, pd.DataFrame) and s.shape[0] > 0:
            out.at[tid, "spots"] = _ensure_global_id(s, "index")

    # -------- 1) load FULL global spots (GLOBAL coords) --------
    global_spots = _load_global_spots(work_dir)
    if global_spots is None or global_spots.shape[0] == 0:
        raise RuntimeError("[stitch] global_spots.pkl missing/empty. Please re-run stage=prep to generate it.")

    global_spots = _ensure_global_id(global_spots, "index")
    global_spots = _init_global_cols(global_spots)

    print(f"[stitch] global_spots: n={global_spots.shape[0]} "
          f"id(min,max)=({global_spots.index.min()},{global_spots.index.max()}) "
          f"unique={global_spots.index.is_unique}")

    # -------- 2) pick a template tile model to copy essential params --------
    template_model = None
    template_tid = None
    missing_files = 0
    ok_tiles = 0

    for tid in range(n_tiles):
        pkl = _tile_out_path(work_dir, tid)
        if not os.path.exists(pkl):
            missing_files += 1
            continue
        m = joblib.load(pkl)
        if m is None:
            continue
        template_model = m
        template_tid = tid
        break

    if template_model is None:
        print(f"[stitch] no successful tiles (missing files: {missing_files}).")
        sys.exit(2)

    # -------- 3) build a CLEAN accumulator model (FULL image space) --------
    # Use template params if present; fallback to manifest.
    try:
        gene_list = getattr(template_model, "gene_list", np.array([], dtype=int))
    except Exception:
        gene_list = np.array([], dtype=int)

    num_dims = int(getattr(template_model, "num_dims", 3))
    xy_radius = int(getattr(template_model, "xy_radius", int(manifest.get("xy_radius", 45))))
    z_radius  = int(getattr(template_model, "z_radius",  int(manifest.get("z_radius", 10))))
    fast_preprocess = bool(getattr(template_model, "fast_preprocess", False))
    gauss_blur = bool(getattr(template_model, "gauss_blur", False))

    model_acc = ClusterMap(
        spots=global_spots,
        dapi=None,                    # stitch should not need full dapi; only out.label_img + ids
        gene_list=gene_list,
        num_dims=num_dims,
        xy_radius=xy_radius,
        z_radius=z_radius,
        fast_preprocess=fast_preprocess,
        gauss_blur=gauss_blur
    )
    model_acc.min_spot_per_cell = int(manifest.get("reads_filter", 5))

    # IMPORTANT: start from empty assignment (do NOT seed with any tile local labels)
    model_acc.spots["clustermap"] = -1
    for cc in ("cell_center_0", "cell_center_1", "cell_center_2"):
        if cc in model_acc.spots.columns:
            model_acc.spots[cc] = -1

    # -------- 4) stitch tiles one-by-one (fresh load each time; NO writeback) --------
    failed = []
    for tid in range(n_tiles):
        pkl = _tile_out_path(work_dir, tid)
        if not os.path.exists(pkl):
            continue

        m = joblib.load(pkl)
        if m is None:
            continue

        try:
            # make sure tile model keeps its own spot ids column/index
            if hasattr(m, "spots") and isinstance(m.spots, pd.DataFrame) and m.spots.shape[0] > 0:
                if "index" not in m.spots.columns:
                    # if some older run lost it, fall back to index
                    m.spots["index"] = pd.to_numeric(m.spots.index, errors="coerce").astype(np.int64)
                m.spots = _ensure_global_id(m.spots, "index")

            # label_img must exist
            if tid >= out.shape[0] or out.loc[tid, "label_img"] is None:
                raise RuntimeError("label_img is None/missing for this tile")

            # the ONLY source of truth for global id merge/relabel is ClusterMap.stitch()
            _ = model_acc.stitch(m, out, tid)

            ok_tiles += 1
            if tid % 5 == 0 or _dbg_enabled():
                acc_pos = int((pd.to_numeric(model_acc.spots["clustermap"], errors="coerce").fillna(-1) >= 0).sum())
                print(f"[stitch] tile{tid}: ok, acc_cm>=0={acc_pos}", flush=True)

        except Exception as e:
            failed.append(tid)
            print(f"[stitch] tile{tid} FAILED: {e}", flush=True)

        finally:
            del m
            gc.collect()

    print(f"[stitch] tiles ok: {ok_tiles} / {n_tiles} (missing files: {missing_files})")

    # -------- 5) write outputs --------
    os.makedirs(args.output_path, exist_ok=True)

    remain_reads = model_acc.spots.copy()
    if "index" not in remain_reads.columns:
        remain_reads["index"] = pd.to_numeric(remain_reads.index, errors="coerce").astype(np.int64)
    remain_reads.to_csv(os.path.join(args.output_path, "remain_reads_raw.csv"), index=False)

    rr_cm = pd.to_numeric(remain_reads["clustermap"], errors="coerce").fillna(-1).astype(np.int64)
    remain_reads2 = remain_reads.loc[rr_cm >= 0, :].copy()
    remain_reads2.to_csv(os.path.join(args.output_path, "remain_reads.csv"), index=False)

    # cell_center: prefer model_acc.* if stitch filled them; else fall back to spot-level centers if present
    if hasattr(model_acc, 'cellcenter_unique') and hasattr(model_acc, 'cellid_unique'):
        cid = np.asarray(model_acc.cellid_unique)
        cc  = np.asarray(model_acc.cellcenter_unique)
        good = np.isfinite(cid)
        cid2 = cid[good].astype(np.int64)
        cc2  = cc[good]
        if cc2.ndim == 2 and cc2.shape[1] >= 3:
            cell_center_df = pd.DataFrame({
                'cell_barcode': cid2,
                'column': cc2[:, 1],
                'row': cc2[:, 0],
                'z_axis': cc2[:, 2]
            })
            cell_center_df.to_csv(os.path.join(args.output_path, "cell_center.csv"), index=False)
    else:
        # optional fallback: write whatever spot-level cell_center_* exists
        if all(c in remain_reads.columns for c in ("cell_center_0", "cell_center_1", "cell_center_2")):
            cc = remain_reads.loc[rr_cm >= 0, ["clustermap", "cell_center_0", "cell_center_1", "cell_center_2"]].copy()
            cc.to_csv(os.path.join(args.output_path, "cell_center_from_spots.csv"), index=False)

    # ---------------------------------------------------------
    # NEW: Optional Polygons and QC Plots computation
    # ---------------------------------------------------------
    cell_polygons = {}
    if args.export_polygons == 'T':
        print("[stitch] Calculating convex hulls for export...")
        try:
            from scipy.spatial import ConvexHull
            unique_cell_ids = remain_reads2['clustermap'].unique()
            for cell_id in unique_cell_ids:
                if cell_id < 0: continue
                cell_spots = remain_reads2[remain_reads2['clustermap'] == cell_id]
                points = cell_spots[['spot_location_1', 'spot_location_2']].values
                if len(points) >= 3:
                    try:
                        hull = ConvexHull(points)
                        hull_path = points[hull.vertices]
                        hull_path = np.append(hull_path, [hull_path[0]], axis=0)
                        cell_polygons[str(int(cell_id))] = hull_path.tolist()
                    except Exception:
                        pass
            json_output_path = os.path.join(args.output_path, 'cell_polygons.json')
            print(f"[stitch] Saving polygons to {json_output_path}...")
            with open(json_output_path, 'w') as f:
                json.dump(cell_polygons, f, indent=None)
        except Exception as e:
            print(f"[stitch] Warning: Could not save polygons: {e}")

    if args.export_qc_plots == 'T':
        print("[stitch] Generating QC plots...")
        try:
            import matplotlib.pyplot as plt
            if remain_reads2.shape[0] > 0:
                cmap = np.random.rand(int(max(remain_reads2['clustermap']) + 1), 3)
                
                # Fetch DAPI max projection correctly from _shared_prep
                dapi_max_path = os.path.join(os.path.dirname(args.work_dir), "_shared_prep", "max_rotated_dapi.tif")
                if os.path.exists(dapi_max_path):
                    import tifffile as tif
                    dapi_rotate_max = tif.imread(dapi_max_path)
                else:
                    # fallback to empty black if not found, sizing it roughly matching coordinate space to avoid tiny corner bug
                    dapi_rotate_max = np.zeros((int(remain_reads2['spot_location_2'].max() + 500), 
                                                int(remain_reads2['spot_location_1'].max() + 500)))

                s = 2
                plt.figure(figsize=[24, 24], facecolor='white')
                
                # --- Panel 1: DAPI Max Proj Only ---
                plt.subplot(2, 2, 1)
                plt.imshow(dapi_rotate_max, cmap='gray')
                plt.title('1. DAPI (Max Projection)', fontsize=18)
                plt.axis('off')
                
                # --- Panel 2: Clean Spots + Black Hulls (No DAPI) ---
                plt.subplot(2, 2, 2)
                plt.scatter(remain_reads2['spot_location_1'], remain_reads2['spot_location_2'], 
                            c=cmap[[int(x) for x in remain_reads2['clustermap']]], s=s, alpha=0.6)
                if hasattr(model_acc, 'cellcenter_unique') and len(model_acc.cellcenter_unique) > 0:
                    plt.scatter(model_acc.cellcenter_unique[:, 1], model_acc.cellcenter_unique[:, 0], c='red', s=20, marker='*')
                if cell_polygons:
                    for cell_id, coords in cell_polygons.items():
                        coords = np.array(coords)
                        plt.plot(coords[:, 0], coords[:, 1], 'k-', linewidth=0.8, alpha=0.7)
                # Invert Y axis to strictly match image coordinates visually
                plt.gca().invert_yaxis()
                plt.title(f'2. ClusterMap Hulls | {len(remain_reads2["clustermap"].unique())} Cells', fontsize=18)
                plt.axis('off')
                
                # --- Panel 3: DAPI + Spots ---
                plt.subplot(2, 2, 3)
                plt.imshow(dapi_rotate_max, cmap='gray')
                plt.scatter(remain_reads2['spot_location_1'], remain_reads2['spot_location_2'], 
                            c=cmap[[int(x) for x in remain_reads2['clustermap']]], s=s, alpha=0.5)
                if hasattr(model_acc, 'cellcenter_unique') and len(model_acc.cellcenter_unique) > 0:
                    plt.scatter(model_acc.cellcenter_unique[:, 1], model_acc.cellcenter_unique[:, 0], c='red', s=20)
                plt.title('3. DAPI Overlay + RNA Spots', fontsize=18)
                plt.axis('off')
                
                # --- Panel 4: DAPI + Spots + White Hulls ---
                plt.subplot(2, 2, 4)
                plt.imshow(dapi_rotate_max, cmap='gray')
                plt.scatter(remain_reads2['spot_location_1'], remain_reads2['spot_location_2'], 
                            c=cmap[[int(x) for x in remain_reads2['clustermap']]], s=s, alpha=0.45)
                if hasattr(model_acc, 'cellcenter_unique') and len(model_acc.cellcenter_unique) > 0:
                    plt.scatter(model_acc.cellcenter_unique[:, 1], model_acc.cellcenter_unique[:, 0], c='red', s=20, marker='*')
                if cell_polygons:
                    for cell_id, coords in cell_polygons.items():
                        coords = np.array(coords)
                        plt.plot(coords[:, 0], coords[:, 1], 'w-', linewidth=0.8, alpha=0.9)
                plt.title('4. DAPI Overlay + Spots + Cell Boundaries', fontsize=18)
                plt.axis('off')
                
                plt.tight_layout()
                plt.savefig(os.path.join(args.output_path, 'final_segmentation_results.png'), bbox_inches='tight', pad_inches=0.1, dpi=150)
                plt.close()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[stitch] Warning: Could not save final_segmentation_results.png: {e}", flush=True)

    joblib.dump(model_acc, os.path.join(args.output_path, "model_final.pkl"), compress=3)

    if failed and args.stitch_strict_fail == 'T':
        print(f"[stitch] FAILED tiles: {failed} -> exit(3)")
        sys.exit(3)

    print("[stitch] done")
# =========================================================
# main
# =========================================================
def main():
    args = command_args()

    _ = int(args.input_imgZ)
    _ = float(args.input_cell_num_threshold)
    _ = int(args.input_dapi_grid_interval)
    _ = float(args.input_pct_filter)
    _parse_icr(args.input_cell_radius)

    if args.stage == "prep":
        _stage_prep(args)
    elif args.stage == "tile":
        if args.tile_id is None: 
            raise ValueError("--tile_id is required for stage=tile")
        _stage_tile(args)
    elif args.stage == "stitch":
        _stage_stitch(args)
    else:
        raise ValueError(f"Unknown stage: {args.stage}")


if __name__ == "__main__":
    main()