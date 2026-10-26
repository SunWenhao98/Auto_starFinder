import argparse
import os
import sys

import networkx as nx
import numpy as np
import pandas as pd
import scipy.sparse
import scipy.sparse.linalg
import skimage.io
from ashlar import reg
from ashlar.reg import EdgeAligner, Mosaic, PyramidWriter


def tileconfig_name(fname):
    return os.path.basename(fname.replace("\\", "/"))


def parse_slice_indices(spec):
    if not spec:
        return []
    indices = []
    for item in str(spec).replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        value = int(item)
        if value < 1:
            raise ValueError("slice indices are 1-based and must be >= 1")
        indices.append(value)
    return indices


class TiffTxtReader(reg.PlateReader):
    """Reader for TileConfiguration-style coordinates and per-tile TIFF files."""

    def __init__(
        self,
        directory,
        config_file,
        mode="mip",
        rotate90=False,
        pixel_size_um=1.0,
        slice_index=None,
    ):
        self.path = directory
        self.mode = mode  # "mip", "stack", or "slice" for selected 1-based z-slice.
        self.rotate90 = rotate90
        self.pixel_size_um = pixel_size_um
        self.slice_index = slice_index
        self.coords_data = self._parse_config(config_file)

        if not self.coords_data:
            print("Error: No coordinates found in config file!")
            sys.exit(1)

        first_file = os.path.join(self.path, self.coords_data[0]["filename"])
        try:
            img = skimage.io.imread(first_file)
            print(f"[Init] Detecting info from: {os.path.basename(first_file)}")
            print(f"[Init] Raw Shape: {img.shape}")
            print(f"[Init] Dtype: {img.dtype}")

            self.raw_ndim = img.ndim
            self.raw_shape = img.shape
            self.pixel_dtype = img.dtype

            if self.raw_ndim == 3:
                self.z_depth = img.shape[0]
                self.tile_size_val = np.array(img.shape[-2:])  # Y, X
            else:
                self.z_depth = 1
                self.tile_size_val = np.array(img.shape)

            if self.rotate90:
                self.tile_size_val = np.array(
                    [self.tile_size_val[1], self.tile_size_val[0]]
                )
                print("[Init] Rotate90 enabled: tile dimensions swapped")

            if self.mode == "slice":
                if self.slice_index is None:
                    raise ValueError("slice mode requires slice_index")
                if self.slice_index < 1 or self.slice_index > self.z_depth:
                    raise ValueError(
                        f"slice_index {self.slice_index} out of range [1, {self.z_depth}]"
                    )

            print(f"[Init] Detected Z-depth: {self.z_depth}")
            print(f"[Init] Tile Size (Y, X): {self.tile_size_val}")
            print(f"[Init] Pixel size: {self.pixel_size_um} um/pixel")
        except Exception as e:
            print(f"Error reading first image {first_file}: {e}")
            sys.exit(1)

    def _parse_config(self, config_file):
        data = []
        with open(config_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("dim"):
                    continue
                if "(" not in line or ")" not in line:
                    continue

                parts = line.split(";")
                fname = parts[0].strip()
                coords_str = parts[-1].strip().replace("(", "").replace(")", "")
                try:
                    vals = list(map(float, coords_str.split(",")))
                    data.append({"filename": fname, "x": vals[0], "y": vals[1]})
                except Exception as e:
                    print(f"Warning: Skipping invalid line: {line} -> {e}")
        return data

    @property
    def metadata(self):
        class Meta:
            pass

        positions = np.array([[d["y"], d["x"]] for d in self.coords_data])

        m = Meta()
        m.num_images = len(self.coords_data)
        m.num_channels = self.z_depth if self.mode == "stack" else 1
        # Ashlar positions and tile sizes are in pixels. pixel_size is still
        # needed to convert max_shift from microns to pixels and for OME output.
        m.pixel_size = self.pixel_size_um
        m.positions = positions
        m.size = self.tile_size_val
        m.filename = [d["filename"] for d in self.coords_data]
        m.origin = m.positions.min(axis=0)
        m.pixel_dtype = self.pixel_dtype
        return m

    def _apply_rotate90(self, img_2d):
        if self.rotate90:
            return np.rot90(img_2d, k=3)  # clockwise 90 degrees
        return img_2d

    def read(self, series, c):
        fname = self.coords_data[series]["filename"]
        full_path = os.path.join(self.path, fname)
        img = skimage.io.imread(full_path)

        if self.mode == "mip":
            if img.ndim == 3:
                return self._apply_rotate90(np.max(img, axis=0))
            return self._apply_rotate90(img)

        if self.mode == "stack":
            if img.ndim == 3:
                z_index = min(c, self.z_depth - 1)
                return self._apply_rotate90(img[z_index, :, :])
            return self._apply_rotate90(img)

        if self.mode == "slice":
            if img.ndim == 3:
                return self._apply_rotate90(img[self.slice_index - 1, :, :])
            if self.slice_index != 1:
                raise ValueError(f"2D input only supports slice_index=1: {full_path}")
            return self._apply_rotate90(img)

        return self._apply_rotate90(img)


class MSTEdgeAligner(EdgeAligner):
    """EdgeAligner without a global max_error threshold.

    Every neighbor edge is registered, then Kruskal's minimum spanning tree over
    the alignment error picks the lowest-error edges until all tiles are
    connected. Edges whose shift exceeds max_shift, or disagrees with the robust
    shift distribution of same-direction edges, are suspected failures. A
    suspect is re-accepted if it closes its loops (robust LSQ over all edges
    within max_shift keeps it and it is not a bridge): real stage jumps are
    loop-consistent, failed registrations are not. Remaining suspects are only
    used as a last resort to connect a tile, with their shift replaced by the
    typical shift for that direction (i.e. trust the stage).

    With position_solver="lsq", the tree is only used to check connectivity;
    final positions come from a weighted least-squares fit over all
    shift-consistent edges (plus the tree's fallback edges), iteratively
    dropping the worst non-bridge edge while its residual > lsq_max_residual_px.
    """

    # MST: fallback edges sort after every measured edge.
    MST_FALLBACK_OFFSET = 1e6
    # LSQ: fallback edges only keep tiles connected, barely pull positions.
    LSQ_FALLBACK_WEIGHT = 1e-3

    def __init__(
        self,
        reader,
        outlier_sigma=5.0,
        outlier_floor_frac=0.005,
        position_solver="lsq",
        lsq_max_residual_px=3.0,
        tile_group=None,
        **kwargs,
    ):
        super().__init__(reader, max_error=np.inf, **kwargs)
        self.outlier_sigma = outlier_sigma
        self.outlier_floor_frac = outlier_floor_frac
        self.position_solver = position_solver
        self.lsq_max_residual_px = lsq_max_residual_px
        # Optional per-tile label (e.g. imaging round) for joint multi-round
        # stitching: edges are grouped by label pair for the consistency check.
        self.tile_group = None if tile_group is None else np.asarray(tile_group)

    def compute_threshold(self):
        if self.verbose:
            print("    MST mode: skipping global error threshold")

    def register_all(self):
        pos = self.metadata.positions
        n = self.neighbors_graph.size()
        rows = []
        for i, (t1, t2) in enumerate(self.neighbors_graph.edges, 1):
            if self.verbose:
                sys.stdout.write("\r    aligning edge %d/%d" % (i, n))
                sys.stdout.flush()
            a, b = sorted((t1, t2))
            shift, error = self.register_pair(a, b)
            delta = pos[b] - pos[a]
            axis = int(np.argmax(np.abs(delta)))
            direction = "V" if axis == 0 else "H"
            # Orient shifts so that tile2 is always "after" tile1 along the
            # main axis; systematic stage errors then share a sign.
            sign = 1.0 if delta[axis] >= 0 else -1.0
            group = direction
            if self.tile_group is not None:
                g1, g2 = self.tile_group[a], self.tile_group[b]
                if g1 == g2:
                    group = f"{g1}-{direction}"
                else:
                    # Cross-group edges mostly overlap fully; no orientation.
                    group, sign = f"{g1}|{g2}", 1.0
            rows.append(
                {
                    "tile1": a,
                    "tile2": b,
                    "direction": direction,
                    "group": group,
                    "sign": sign,
                    "nominal_delta_y_px": delta[0],
                    "nominal_delta_x_px": delta[1],
                    "nominal_overlap_y_px": self.metadata.size[0] - abs(delta[0]),
                    "nominal_overlap_x_px": self.metadata.size[1] - abs(delta[1]),
                    "shift_y_px": shift[0],
                    "shift_x_px": shift[1],
                    "raw_error": error,
                }
            )
        if self.verbose:
            print()
        self.classify_edges(pd.DataFrame(rows))

    def classify_edges(self, df):
        """Mark inlier edges and set the shift/weight each edge contributes."""
        if df.empty:
            self.edge_table = df
            return
        if "group" not in df:
            df["group"] = df["direction"]

        err = df["raw_error"].to_numpy()
        sign = df["sign"].to_numpy()[:, None]
        shifts = df[["shift_y_px", "shift_x_px"]].to_numpy()
        oriented = shifts * sign
        within_shift = np.isfinite(err) & np.all(
            np.abs(shifts) <= self.max_shift_pixels, axis=1
        )
        inlier = within_shift.copy()
        ref_oriented = np.zeros_like(oriented)
        floor = self.outlier_floor_frac * self.metadata.size

        for d in sorted(df["group"].unique()):
            in_dir = (df["group"] == d).to_numpy()
            m = in_dir & within_shift
            if not m.any():
                continue
            # Reference = lower-error half of this group's edges.
            best = m & (err <= np.median(err[m]))
            med = np.median(oriented[best], axis=0)
            ref_oriented[in_dir] = med
            if self.outlier_sigma > 0 and best.sum() >= 5:
                sigma = 1.4826 * np.median(np.abs(oriented[best] - med), axis=0)
                tol = np.maximum(self.outlier_sigma * sigma, floor)
                inlier[m] = np.all(np.abs(oriented[m] - med) <= tol, axis=1)
                if self.verbose:
                    print(
                        f"    [{d}] typical shift (y, x): ({med[0]:.1f}, {med[1]:.1f}) px, "
                        f"tolerance: ({tol[0]:.1f}, {tol[1]:.1f}) px"
                    )
        rescued = self._loop_consistent(df, shifts, err, within_shift) & ~inlier
        inlier |= rescued

        used = np.where(inlier[:, None], shifts, ref_oriented * sign)
        weight = np.where(
            inlier,
            err,
            self.MST_FALLBACK_OFFSET
            + np.where(np.isfinite(err), err, self.MST_FALLBACK_OFFSET),
        )

        df["within_max_shift"] = within_shift
        df["inlier"] = inlier
        df["rescued_by_loop"] = rescued
        df["used_shift_y_px"] = used[:, 0]
        df["used_shift_x_px"] = used[:, 1]
        df["mst_weight"] = weight
        self.edge_table = df
        self._cache = {
            (a, b): (used[i].copy(), weight[i])
            for i, (a, b) in enumerate(zip(df["tile1"], df["tile2"]))
        }

    def _loop_consistent(self, df, shifts, err, within_shift):
        """Edges kept by robust LSQ over all edges within max_shift, excluding bridges."""
        t1 = df["tile1"].to_numpy()
        t2 = df["tile2"].to_numpy()
        pos0 = self.metadata.positions
        target = pos0[t2] - pos0[t1] + shifts
        w = np.exp(-np.minimum(err, 50.0))
        _, _, active, _ = self._robust_lsq(t1, t2, target, w, within_shift, within_shift)
        bridges = self._bridges(t1[active], t2[active])
        not_bridge = np.array([frozenset((a, b)) not in bridges for a, b in zip(t1, t2)])
        return active & not_bridge

    def build_spanning_tree(self):
        g = nx.Graph()
        g.add_nodes_from(self.neighbors_graph)
        g.add_weighted_edges_from(
            (a, b, w) for (a, b), (_, w) in self._cache.items()
        )
        self.spanning_tree = nx.minimum_spanning_tree(g, algorithm="kruskal")

        df = self.edge_table
        if df.empty:
            return
        in_mst = np.array(
            [self.spanning_tree.has_edge(a, b) for a, b in zip(df["tile1"], df["tile2"])]
        )
        df["in_mst"] = in_mst
        df["edge_source"] = np.where(
            ~in_mst, "unused", np.where(df["inlier"], "measured", "fallback")
        )

        if not self.verbose:
            return
        measured = df["edge_source"] == "measured"
        n_components = nx.number_connected_components(self.spanning_tree)
        print(f"[MST] Edges registered: {len(df)}")
        print(f"[MST] Within max_shift: {int(df['within_max_shift'].sum())}")
        print(
            f"[MST] Shift-consistent (inlier): {int(df['inlier'].sum())} "
            f"(incl. {int(df['rescued_by_loop'].sum())} rescued by loop consistency)"
        )
        print(
            f"[MST] Tree edges: {int(in_mst.sum())} = "
            f"{int(measured.sum())} measured + "
            f"{int((df['edge_source'] == 'fallback').sum())} fallback (stage-predicted shift)"
        )
        if measured.any():
            print(
                "[MST] Largest error used in tree (equivalent max_error): "
                f"{df.loc[measured, 'raw_error'].max():.3f}"
            )
        print(f"[MST] Connected components: {n_components} (1 = all tiles linked)")

    def calculate_positions(self):
        if self.position_solver != "lsq" or self.edge_table.empty:
            return super().calculate_positions()
        df = self.edge_table
        use = df["inlier"].to_numpy() | (df["edge_source"] == "fallback").to_numpy()
        pos, resid, active, removed = self.solve_lsq_positions(use)
        self.positions = pos
        self.shifts = pos - self.metadata.positions
        df["lsq_active"] = active
        df["lsq_removed"] = removed
        df["lsq_residual_px"] = resid
        if not self.verbose:
            return
        r = resid[active & df["inlier"].to_numpy()]
        print(
            f"[LSQ] Edges used: {int(active.sum())}, removed as inconsistent: "
            f"{int(removed.sum())} (max_residual={self.lsq_max_residual_px:g} px)"
        )
        if len(r):
            print(
                "[LSQ] Residual on used edges median/p90/max: "
                f"{np.median(r):.2f}/{np.percentile(r, 90):.2f}/{r.max():.2f} px"
            )

    def solve_lsq_positions(self, use):
        """Weighted LSQ over edges in boolean mask `use` (rows of edge_table)."""
        df = self.edge_table
        pos0 = self.metadata.positions
        t1 = df["tile1"].to_numpy()
        t2 = df["tile2"].to_numpy()
        inlier = df["inlier"].to_numpy()
        used = df[["used_shift_y_px", "used_shift_x_px"]].to_numpy()
        target = pos0[t2] - pos0[t1] + used
        # exp(-error) is the normalized cross-correlation of the edge.
        w = np.where(
            inlier,
            np.exp(-np.minimum(df["raw_error"].to_numpy(), 50.0)),
            self.LSQ_FALLBACK_WEIGHT,
        )
        return self._robust_lsq(t1, t2, target, w, use, inlier)

    def _robust_lsq(self, t1, t2, target, w, use, removable):
        """LSQ over `use`, dropping the worst `removable` non-bridge edge while
        its residual exceeds lsq_max_residual_px."""
        active = use.copy()
        removed = np.zeros(len(t1), dtype=bool)
        while True:
            pos = self._solve_lsq(t1[active], t2[active], target[active], w[active])
            resid = np.linalg.norm(pos[t2] - pos[t1] - target, axis=1)
            cand = np.flatnonzero(active & removable & (resid > self.lsq_max_residual_px))
            if not len(cand):
                break
            bridges = self._bridges(t1[active], t2[active])
            cand = [i for i in cand if frozenset((t1[i], t2[i])) not in bridges]
            if not cand:
                break
            worst = max(cand, key=lambda i: resid[i])
            active[worst] = False
            removed[worst] = True
        return pos, resid, active, removed

    @staticmethod
    def _bridges(t1, t2):
        g = nx.Graph()
        g.add_edges_from(zip(t1, t2))
        return {frozenset(e) for e in nx.bridges(g)}

    def _solve_lsq(self, t1, t2, target, w):
        n = self.metadata.num_images
        g = nx.Graph()
        g.add_nodes_from(range(n))
        g.add_edges_from(zip(t1, t2))
        # One anchor per component (kept at its stage position) fixes the gauge.
        anchors = np.array([min(c) for c in nx.connected_components(g)])
        m, k = len(t1), len(anchors)
        sw = np.sqrt(w)
        mat = scipy.sparse.csr_matrix(
            (
                np.r_[sw, -sw, np.ones(k)],
                (np.r_[np.arange(m), np.arange(m), m + np.arange(k)], np.r_[t2, t1, anchors]),
            ),
            shape=(m + k, n),
        )
        normal = (mat.T @ mat).tocsc()
        pos = np.empty((n, 2))
        for ax in range(2):
            b = np.r_[sw * target[:, ax], self.metadata.positions[anchors, ax]]
            pos[:, ax] = scipy.sparse.linalg.spsolve(normal, mat.T @ b)
        return pos


def write_mst_edge_diagnostics(aligner, path):
    df = aligner.edge_table.drop(columns=["sign"], errors="ignore")
    if "lsq_active" in df:
        df["accepted"] = df["lsq_active"]
    elif "in_mst" in df:
        df["accepted"] = df["in_mst"]
    if "within_max_shift" in df:
        df["rejected_by_shift"] = ~df["within_max_shift"]
    df.to_csv(path, index=False)
    print(f"[Diagnostics] Edge alignment table saved to: {path}")


def write_edge_diagnostics(aligner, path):
    edges = list(aligner.neighbors_graph.edges)
    raw_errors = getattr(aligner, "all_errors", np.repeat(np.nan, len(edges)))
    rows = []

    for i, edge in enumerate(edges):
        t1, t2 = edge
        key = tuple(sorted((t1, t2)))
        shift, filtered_error = aligner._cache.get(key, (np.array([np.nan, np.nan]), np.inf))
        raw_error = raw_errors[i] if i < len(raw_errors) else np.nan
        nominal_delta = aligner.metadata.positions[t2] - aligner.metadata.positions[t1]
        nominal_overlap = aligner.metadata.size - np.abs(nominal_delta)
        rejected_by_shift = bool(np.any(np.abs(shift) > aligner.max_shift_pixels))
        max_error = getattr(aligner, "max_error", np.nan)
        rejected_by_error = bool(np.isfinite(raw_error) and np.isfinite(max_error) and raw_error > max_error)

        rows.append(
            {
                "tile1": t1,
                "tile2": t2,
                "nominal_delta_y_px": nominal_delta[0],
                "nominal_delta_x_px": nominal_delta[1],
                "nominal_overlap_y_px": nominal_overlap[0],
                "nominal_overlap_x_px": nominal_overlap[1],
                "shift_y_px": shift[0],
                "shift_x_px": shift[1],
                "raw_error": raw_error,
                "max_error": max_error,
                "filtered_error": filtered_error,
                "accepted": np.isfinite(filtered_error),
                "rejected_by_shift": rejected_by_shift,
                "rejected_by_error": rejected_by_error,
            }
        )

    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)

    if len(df):
        accepted = int(df["accepted"].sum())
        print(f"[Diagnostics] Accepted edges: {accepted}/{len(df)}")
        print(
            "[Diagnostics] Median nominal overlap (Y, X): "
            f"({df['nominal_overlap_y_px'].median():.1f}, "
            f"{df['nominal_overlap_x_px'].median():.1f}) px"
        )
        print(f"[Diagnostics] Rejected by shift: {int(df['rejected_by_shift'].sum())}")
        print(f"[Diagnostics] Rejected by error: {int(df['rejected_by_error'].sum())}")
        finite_raw = df["raw_error"].replace([np.inf, -np.inf], np.nan).dropna()
        finite_filtered = df["filtered_error"].replace([np.inf, -np.inf], np.nan).dropna()
        finite_max_error = df["max_error"].replace([np.inf, -np.inf], np.nan).dropna()
        if len(finite_max_error):
            print(f"[Diagnostics] max_error: {finite_max_error.iloc[0]:.3f}")
        if len(finite_raw):
            print(
                "[Diagnostics] Raw error median/q90: "
                f"{finite_raw.median():.3f}/{finite_raw.quantile(0.9):.3f}"
            )
        if len(finite_filtered):
            print(
                "[Diagnostics] Filtered error median/q90: "
                f"{finite_filtered.median():.3f}/{finite_filtered.quantile(0.9):.3f}"
            )
    print(f"[Diagnostics] Edge alignment table saved to: {path}")


def main():
    parser = argparse.ArgumentParser(description="Ashlar stitching from TileConfiguration.txt")
    parser.add_argument("--input_dir", required=True)
    parser.add_argument("--config_file", required=True)
    parser.add_argument(
        "--output_image_prefix",
        required=True,
        help="Prefix for output files, e.g. /path/to/stitched_ref-DAPI",
    )
    parser.add_argument(
        "--registered_config_file",
        default=None,
        help=(
            "Where to write TileConfiguration.registered.txt. Defaults to the "
            "directory containing --config_file so all backends can share it."
        ),
    )
    parser.add_argument("--make_3d", type=str, default="false", help="true/false string")
    parser.add_argument(
        "--rotate90",
        action="store_true",
        default=False,
        help=(
            "Rotate each FOV pixel array clockwise by 90 degrees before Ashlar "
            "alignment and before writing the output mosaic. Metadata positions "
            "are NOT rotated by default."
        ),
    )
    parser.add_argument(
        "--rotate_positions",
        action="store_true",
        default=False,
        help=(
            "Diagnostic only: also rotate metadata positions clockwise with "
            "(y, x)->(x, -y). Do not use for MAF coordinates that are already "
            "correct in the final/global mosaic frame."
        ),
    )
    parser.add_argument(
        "--pixel_size_um",
        type=float,
        default=1.0,
        help="Physical pixel size in um/pixel. TileConfiguration coordinates remain in pixels.",
    )
    parser.add_argument(
        "--max_shift_px",
        type=str,
        default="auto",
        help=(
            "Maximum allowed corrective shift in pixels, or 'auto' to use "
            "--max_shift_frac x FOV size per axis. Converted to microns for Ashlar."
        ),
    )
    parser.add_argument(
        "--max_shift_frac",
        type=float,
        default=0.05,
        help="Fraction of FOV size (per axis) used as max_shift when --max_shift_px auto.",
    )
    parser.add_argument(
        "--filter_sigma",
        type=float,
        default=3.0,
        help=(
            "Sigma (px) of the LoG whitening filter applied before correlation. "
            "Should roughly match the scale of image structures; 1.0 mostly keeps "
            "pixel noise on DAPI nuclei, 2-3 works much better."
        ),
    )
    parser.add_argument(
        "--stitch_alpha",
        type=float,
        default=0.01,
        help=(
            "Ashlar alpha used to estimate automatic max_error from false "
            "neighbor alignments. Higher values loosen the error QC threshold."
        ),
    )
    parser.add_argument(
        "--max_error",
        type=str,
        default="mst",
        help=(
            "'mst' (default): no threshold, pick lowest-error edges via a minimum "
            "spanning tree until all FOVs are linked; 'auto': Ashlar threshold "
            "from stitch_alpha; or an explicit numeric threshold."
        ),
    )
    parser.add_argument(
        "--shift_outlier_sigma",
        type=float,
        default=5.0,
        help=(
            "MST mode: edges whose shift deviates from the typical same-direction "
            "shift by more than this many robust sigmas are treated as failed "
            "registrations. 0 disables the check."
        ),
    )
    parser.add_argument(
        "--position_solver",
        choices=["lsq", "mst"],
        default="lsq",
        help=(
            "MST mode: 'lsq' = global weighted least squares over all "
            "shift-consistent edges; 'mst' = accumulate shifts along the tree."
        ),
    )
    parser.add_argument(
        "--lsq_max_residual_px",
        type=float,
        default=3.0,
        help="LSQ: iteratively drop non-bridge edges with residual above this (px).",
    )
    parser.add_argument(
        "--slice_indices",
        default="",
        help="Comma-separated 1-based z-slice indices to write as extra 2D mosaics, e.g. '1,10,20'.",
    )

    args = parser.parse_args()
    do_make_3d = args.make_3d.lower() == "true"
    slice_indices = parse_slice_indices(args.slice_indices)
    os.makedirs(os.path.dirname(args.output_image_prefix), exist_ok=True)

    diagnostics_dir = os.path.dirname(args.config_file)
    diagnostics_prefix = os.path.join(
        diagnostics_dir, os.path.basename(args.output_image_prefix)
    )
    os.makedirs(diagnostics_dir, exist_ok=True)

    csv_path = f"{diagnostics_prefix}_coordinates.csv"
    edge_csv_path = f"{diagnostics_prefix}_edge_alignment.csv"
    path_2d = f"{args.output_image_prefix}_2d.ome.tif"
    path_3d = f"{args.output_image_prefix}_3d.ome.tif"

    print(f"Output Prefix: {args.output_image_prefix}")
    print(f"Make 3D: {do_make_3d}")
    print(f"Rotate FOV pixels before alignment and output: {args.rotate90}")
    print("\n=== Phase 1: Calculating Alignment Coordinates (using 2D MIP) ===")

    reader_mip = TiffTxtReader(
        args.input_dir,
        args.config_file,
        mode="mip",
        rotate90=args.rotate90,
        pixel_size_um=args.pixel_size_um,
    )

    auto_max_shift = args.max_shift_px.strip().lower() == "auto"
    if auto_max_shift:
        max_shift_px = args.max_shift_frac * reader_mip.tile_size_val.astype(float)
    else:
        max_shift_px = np.repeat(float(args.max_shift_px), 2)
    # Per-axis (Y, X) array; Ashlar compares |shift| element-wise.
    effective_max_shift = max_shift_px * args.pixel_size_um

    error_mode = args.max_error.strip().lower()
    use_mst = error_mode == "mst"
    explicit_max_error = None
    if not use_mst and error_mode not in {"", "auto", "none", "nan"}:
        explicit_max_error = float(args.max_error)

    common_kwargs = dict(
        channel=0,
        max_shift=effective_max_shift,
        filter_sigma=args.filter_sigma,
        verbose=True,
    )
    if use_mst:
        aligner_instance = MSTEdgeAligner(
            reader_mip,
            outlier_sigma=args.shift_outlier_sigma,
            position_solver=args.position_solver,
            lsq_max_residual_px=args.lsq_max_residual_px,
            **common_kwargs,
        )
    else:
        aligner_instance = EdgeAligner(
            reader_mip,
            alpha=args.stitch_alpha,
            max_error=explicit_max_error,
            **common_kwargs,
        )
    print(
        f"[Ashlar] max_shift (Y, X): ({max_shift_px[0]:.1f}, {max_shift_px[1]:.1f}) px"
        + (f" = {args.max_shift_frac:g} x FOV" if auto_max_shift else "")
    )
    if use_mst:
        print(
            f"[Ashlar] max_error: mst (shift_outlier_sigma={args.shift_outlier_sigma}, "
            f"position_solver={args.position_solver})"
        )
    else:
        print(f"[Ashlar] stitch_alpha: {args.stitch_alpha}")
        print(
            "[Ashlar] explicit max_error: "
            f"{explicit_max_error if explicit_max_error is not None else 'auto'}"
        )

    def save_diagnostics():
        if use_mst:
            if hasattr(aligner_instance, "edge_table"):
                write_mst_edge_diagnostics(aligner_instance, edge_csv_path)
        elif hasattr(aligner_instance, "_cache"):
            write_edge_diagnostics(aligner_instance, edge_csv_path)

    try:
        aligner_instance.run()
    except Exception:
        save_diagnostics()
        raise
    save_diagnostics()

    positions = aligner_instance.positions
    filenames = reader_mip.metadata.filename
    raw_pos = reader_mip.metadata.positions
    df = pd.DataFrame(
        {
            "filename": filenames,
            "global_y": positions[:, 0],
            "global_x": positions[:, 1],
            "shift_y": positions[:, 0] - raw_pos[:, 0],
            "shift_x": positions[:, 1] - raw_pos[:, 1],
        }
    )
    df.to_csv(csv_path, index=False)
    print(f"Coordinates saved to: {csv_path}")

    registered_config_path = args.registered_config_file or os.path.join(
        os.path.dirname(args.config_file), "TileConfiguration.registered.txt"
    )
    with open(registered_config_path, "w") as f_reg:
        f_reg.write("# Define the number of dimensions we are working on\n")
        f_reg.write("dim = 3\n\n")
        f_reg.write("# Define the image coordinates\n")
        for i, fname in enumerate(filenames):
            gx = positions[i][1]  # Ashlar stores (y, x)
            gy = positions[i][0]
            f_reg.write(f"{tileconfig_name(fname)}; ; ({gx:.2f}, {gy:.2f}, 0.0)\n")
    print(f"TileConfiguration.registered.txt saved to: {registered_config_path}")

    print(f"\n=== Phase 2: Writing 2D MIP Mosaic to {path_2d} ===")
    reader_2d_out = TiffTxtReader(
        args.input_dir,
        args.config_file,
        mode="mip",
        rotate90=args.rotate90,
        pixel_size_um=args.pixel_size_um,
    )
    aligner_instance.reader = reader_2d_out
    mosaic_2d = Mosaic(aligner=aligner_instance, shape=aligner_instance.mosaic_shape, verbose=True)
    writer_2d = PyramidWriter(
        mosaics=[mosaic_2d], path=path_2d, scale=2, tile_size=1024, verbose=True
    )
    writer_2d.run()
    print("2D Image saved.")

    for slice_index in slice_indices:
        path_slice = f"{args.output_image_prefix}_z{slice_index:03d}_2d.ome.tif"
        print(f"\n=== Phase 3: Writing Z-slice {slice_index} Mosaic to {path_slice} ===")
        reader_slice = TiffTxtReader(
            args.input_dir,
            args.config_file,
            mode="slice",
            rotate90=args.rotate90,
            pixel_size_um=args.pixel_size_um,
            slice_index=slice_index,
        )
        aligner_instance.reader = reader_slice
        mosaic_slice = Mosaic(
            aligner=aligner_instance, shape=aligner_instance.mosaic_shape, verbose=True
        )
        writer_slice = PyramidWriter(
            mosaics=[mosaic_slice], path=path_slice, scale=2, tile_size=1024, verbose=True
        )
        writer_slice.run()
        print(f"Z-slice {slice_index} image saved: {path_slice}")

    if do_make_3d:
        print(f"\n=== Phase 4: Writing 3D Stack Mosaic to {path_3d} ===")
        reader_3d = TiffTxtReader(
            args.input_dir,
            args.config_file,
            mode="stack",
            rotate90=args.rotate90,
            pixel_size_um=args.pixel_size_um,
        )
        aligner_instance.reader = reader_3d

        mosaic_3d = Mosaic(
            aligner=aligner_instance, shape=aligner_instance.mosaic_shape, verbose=True
        )
        writer_3d = PyramidWriter(
            mosaics=[mosaic_3d], path=path_3d, scale=2, tile_size=1024, verbose=True
        )
        writer_3d.run()
        print("3D Image saved.")

    print("\nAll tasks complete.")


if __name__ == "__main__":
    main()
