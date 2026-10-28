#!/usr/bin/env python3
"""Joint ashlar stitching of the reference round and the IF round in one frame.

All ref and IF FOVs are treated as tiles of a single mosaic. After a coarse
global offset puts every IF FOV on top of the ref FOVs it images, the neighbor
graph contains ref-ref, IF-IF and cross-round (ref-IF) edges, and the
MSTEdgeAligner of p30_ashlar_stitch_mst.py (edge registration, consistency
check, loop rescue, global LSQ) solves all positions at once. The two output
TileConfigurations share one coordinate frame, so ref and IF coordinates
correspond exactly: the IF->ref offset of FOV k is pos_IF[k] - pos_ref[k]
(written per FOV to <prefix>_if_fov_shifts.csv).

Inputs are the raw rounds (01_data/<round>/PositionXXX/*_<channel>.tif, read in
place) and the MAF stage positions. Positions imaged in both rounds are used;
their nominal TileConfiguration (+ tile_summary.csv) is written from the MAF
with p12_leica2Stitching_configuration.py, as step 12 does. The coarse offset
comes from low-resolution mosaics at nominal positions; it is only used to find
cross-round neighbors.

The IF round's global rotation/scale relative to the ref round is fitted from
the cross-round edges of a first pass, against single-round positions solved
from that pass's own ref-ref and IF-IF edges. If the rotation exceeds
--rotation_threshold_mdeg, IF FOVs are resampled about their centres by that
similarity transform and the joint solve is repeated until the estimate is
stable. Translation-only tile placement cannot represent a rotation: a small one
is spread over every seam, a large one (e.g. a remounted slide, >1 deg) makes
cross-round matching fail altogether.
"""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.ndimage
import skimage.registration
from ashlar import reg

_spec = importlib.util.spec_from_file_location(
    "ashlar_stitch_mst",
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "p30_ashlar_stitch_mst.py"
    ),
)
st = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(st)
_spec = importlib.util.spec_from_file_location(
    "prepare_noRef_layout",
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "p21_prepare_noRef_layout.py"
    ),
)
layout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(layout)
P12 = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "p12_leica2Stitching_configuration.py"
)

COARSE_SCALE = 16


def tile_transform_matrix(a):
    """(y, x) matrix of the similarity z -> a*z (z = x + i*y) and its inverse."""
    fwd = np.array([[a.real, a.imag], [-a.imag, a.real]])  # rows: y', x' from (y, x)
    return fwd, np.linalg.inv(fwd)


def resample_tile(img, a):
    """Resample a tile so that its content is mapped by z -> a*z about the tile centre.

    Pixels with no source data are set to 0: ashlar's mosaic blending keeps the
    existing mosaic wherever a tile is 0, which is how it supports rotated tiles.
    """
    _, inv = tile_transform_matrix(a)
    centre = (np.array(img.shape) - 1) / 2.0
    out = scipy.ndimage.affine_transform(
        img.astype(np.float32),
        inv,
        offset=centre - inv @ centre,
        order=1,
        mode="constant",
        cval=0.0,
    )
    return out.astype(img.dtype)


class JointReader(reg.PlateReader):
    """Ref tiles 0..N-1 followed by IF tiles N..2N-1 (IF placed at nominal + offset).

    IF tiles are optionally resampled by the similarity `if_transform` (complex
    a, z -> a*z about the tile centre). Raw tiles are cached across passes.
    """

    def __init__(self, ref_reader, if_reader, if_offset, if_transform=None, cache=None):
        self.ref, self.moving = ref_reader, if_reader
        self.if_transform = if_transform
        self._raw = {} if cache is None else cache
        self.n = ref_reader.metadata.num_images
        if if_reader.metadata.num_images != self.n:
            raise ValueError("ref and IF configs must list the same FOVs")

        class Meta:
            pass

        m = Meta()
        rm, im = ref_reader.metadata, if_reader.metadata
        m.num_images = 2 * self.n
        m.num_channels = 1
        m.pixel_size = rm.pixel_size
        m.positions = np.vstack([rm.positions, im.positions + if_offset])
        m.size = rm.size
        m.filename = [f"ref/{f}" for f in rm.filename] + [
            f"IF/{f}" for f in im.filename
        ]
        m.origin = m.positions.min(axis=0)
        m.pixel_dtype = rm.pixel_dtype
        self._meta = m

    @property
    def metadata(self):
        return self._meta

    def read(self, series, c):
        if series not in self._raw:
            src = (
                self.ref.read(series, c)
                if series < self.n
                else self.moving.read(series - self.n, c)
            )
            self._raw[series] = src
        img = self._raw[series]
        if series >= self.n and self.if_transform is not None:
            img = resample_tile(img, self.if_transform)
        return img


def raw_tile_files(round_dir, channel):
    """{'PositionXXX.tif': raw stack} of one channel of a raw round (round_dir/PositionXXX/*<channel>*.tif)."""
    return {
        f"{layout.position_name(d)}.tif": str(layout.find_channel_file(d, channel))
        for d in layout.sorted_position_dirs(Path(round_dir))
    }


def write_nominal_config(
    output_dir,
    names,
    config_name,
    maf_file,
    position_offset,
    project_name,
    pixel_size_um,
    image_xy,
    overlap_ratio,
    invert_y,
):
    """Nominal TileConfiguration (+ tile_summary.csv) of `names` from the MAF, as step 12 writes it.

    p12 pairs the i-th file (sorted by Position number) with the i-th MAF point, which
    is wrong when positions are missing; it is run on empty placeholders
    Position001..PositionM and its outputs are then restricted to `names`.
    """
    keep = set(names)
    last = max(int(layout.POSITION_RE.search(n).group(1)) for n in names)
    raw_cfg = os.path.join(output_dir, "TileConfiguration.txt")
    if os.path.exists(
        raw_cfg
    ):  # p12 writes nothing for an unusable MAF; never read an older run's file
        os.remove(raw_cfg)
    with tempfile.TemporaryDirectory() as tmp:
        for k in range(1, last + 1):
            open(os.path.join(tmp, f"Position{k:03d}.tif"), "w").close()
        cmd = [
            sys.executable,
            "-u",
            P12,
            "--input_dir",
            tmp,
            "--output_dir",
            output_dir,
            "--maf_file",
            maf_file,
            "--position_offset",
            str(position_offset),
            "--project_name",
            project_name,
            "--match_string",
            "Position",
            "--pixel_size_um",
            str(pixel_size_um),
            "--image_xy",
            str(image_xy),
            "--overlap_ratio",
            str(overlap_ratio),
        ]
        subprocess.run(cmd + (["--invert_y"] if invert_y else []), check=True)
    with open(raw_cfg) as f:
        lines = f.readlines()
    kept = [
        line for line in lines if ";" not in line or line.split(";")[0].strip() in keep
    ]
    if sum(";" in line for line in kept) != len(keep):
        raise ValueError(
            f"MAF gives {sum(';' in line for line in kept)} of {len(keep)} positions "
            f"(MAF too short for position offset {position_offset}?)"
        )
    for path in (raw_cfg, os.path.join(output_dir, config_name)):
        with open(path, "w") as f:
            f.writelines(kept)
    summary = os.path.join(
        output_dir, "tile_summary.csv"
    )  # first column: relative_path
    with open(summary) as f:
        header, *rows = f.readlines()
    with open(summary, "w") as f:
        f.writelines([header] + [r for r in rows if r.split(",", 1)[0] in keep])
    print(
        f"[Joint] nominal config: {len(keep)} of {last} MAF positions -> {os.path.join(output_dir, config_name)}"
    )
    return os.path.join(output_dir, config_name)


def coarse_nominal_offset(reader, positions, scale=COARSE_SCALE):
    """Translation D (full-res px, y/x) of the IF round relative to the ref round.

    Both rounds are laid out at the same nominal positions in low-resolution
    mosaics; ref_mosaic(u + D) ~ if_mosaic(u).
    """
    n = reader.n
    size = (np.array(reader.metadata.size) // scale).astype(int)
    pos = np.round((positions - positions.min(axis=0)) / scale).astype(int)
    shape = pos.max(axis=0) + size
    mosaics = []
    for first in (0, n):
        m = np.zeros(shape, np.float32)
        for k in range(n):
            img = reader.read(first + k, 0).astype(np.float32)
            small = (
                img[: size[0] * scale, : size[1] * scale]
                .reshape(size[0], scale, size[1], scale)
                .mean(axis=(1, 3))
            )
            y, x = pos[k]
            m[y : y + size[0], x : x + size[1]] = small
        mosaics.append(scipy.ndimage.gaussian_filter(m, 1.5))
    pad = 2 * shape  # pad so the FFT does not wrap
    pa, pb = np.zeros(pad, np.float32), np.zeros(pad, np.float32)
    pa[: shape[0], : shape[1]], pb[: shape[0], : shape[1]] = mosaics
    shift, _, _ = skimage.registration.phase_cross_correlation(
        pa, pb, normalization=None
    )
    shift = np.where(shift > pad / 2, shift - pad, shift)
    return shift * scale


def single_round_positions(aligner, n):
    """Ref and IF positions solved separately from the within-round edges of a pass."""
    e = aligner.edge_table
    use = (e.inlier | (e.edge_source == "fallback")).to_numpy() & (
        e.group != "ref|IF"
    ).to_numpy()
    pos, _, _, _ = aligner.solve_lsq_positions(use)
    return pos[:n], pos[n:]


def fit_if_similarity(edge_table, n, p_ref, q_if):
    """Fit IF->ref similarity a, b (z_ref = a*z_if + b) from inlier cross-round edges.

    Each cross edge (ref k, IF j) observes IF tile j in the ref frame at
    p_ref[k] + measured relative position. p_ref / q_if must be single-round
    positions of unrotated FOVs: joint positions are already pulled toward each
    other and would underestimate the rotation.
    """
    e = edge_table
    x = e[(e.group == "ref|IF") & e.inlier]
    if len(x) < 3:
        raise ValueError(
            f"{len(x)} inlier ref|IF edges: the IF FOVs did not match the ref round "
            "(check the IF round, the channel and the coarse offset)"
        )
    obs = (
        p_ref[x.tile1.to_numpy()]
        + x[["nominal_delta_y_px", "nominal_delta_x_px"]].to_numpy()
        + x[["shift_y_px", "shift_x_px"]].to_numpy()
    )
    q = q_if[x.tile2.to_numpy() - n]
    zq, zo = q[:, 1] + 1j * q[:, 0], obs[:, 1] + 1j * obs[:, 0]
    keep = np.ones(len(zq), dtype=bool)
    for _ in range(3):
        A = np.c_[zq[keep], np.ones(keep.sum())]
        (a, b), *_ = np.linalg.lstsq(A, zo[keep], rcond=None)
        r = np.abs(a * zq + b - zo)
        mad = 1.4826 * np.median(np.abs(r[keep] - np.median(r[keep])))
        keep = r <= np.median(r[keep]) + 4 * max(mad, 0.1)
    return a, dict(
        rotation_mdeg=float(np.degrees(np.angle(a)) * 1000),
        scale_ppm=float((abs(a) - 1) * 1e6),
        edges_used=int(keep.sum()),
        residual_median_px=float(np.median(r[keep])),
    )


def write_tile_config(path, filenames, positions):
    with open(path, "w") as f:
        f.write("# Define the number of dimensions we are working on\n")
        f.write("dim = 3\n\n")
        f.write("# Define the image coordinates\n")
        for fname, (y, x) in zip(filenames, positions):
            f.write(f"{st.tileconfig_name(fname)}; ; ({x:.2f}, {y:.2f}, 0.0)\n")


def main():
    parser = argparse.ArgumentParser(
        description="Joint ashlar stitching of the ref round and the IF round"
    )
    parser.add_argument(
        "--ref_round_dir", required=True, help="Raw ref round, e.g. 01_data/round001"
    )
    parser.add_argument(
        "--if_round_dir", required=True, help="Raw IF round, e.g. 01_data/IF"
    )
    parser.add_argument(
        "--ref_channel", default="ch03", help="File token of the ref-round DAPI channel"
    )
    parser.add_argument(
        "--if_channel", default="ch03", help="File token of the IF-round DAPI channel"
    )
    parser.add_argument(
        "--maf_file", required=True, help="Leica MAF with the stage positions"
    )
    parser.add_argument(
        "--position_offset", type=int, default=0, help="First MAF point of this sample"
    )
    parser.add_argument("--project_name", default="")
    parser.add_argument(
        "--pixel_size_um", type=float, default=0.142, help="MAF microns -> pixels"
    )
    parser.add_argument("--image_xy", type=int, default=2048)
    parser.add_argument("--overlap_ratio", type=float, default=0.1)
    parser.add_argument("--invert_y", action="store_true", default=False)
    parser.add_argument(
        "--config_name",
        default="TileConfiguration.initial.txt",
        help="Nominal config written here",
    )
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--prefix", default="joint_ref-IF")
    parser.add_argument("--ref_config_name", default="TileConfiguration.joint_ref.txt")
    parser.add_argument("--if_config_name", default="TileConfiguration.joint_IF.txt")
    parser.add_argument("--max_shift_frac", type=float, default=0.05)
    parser.add_argument("--filter_sigma", type=float, default=3.0)
    parser.add_argument("--shift_outlier_sigma", type=float, default=5.0)
    parser.add_argument("--lsq_max_residual_px", type=float, default=3.0)
    parser.add_argument("--rotate90", action="store_true", default=False)
    parser.add_argument(
        "--rotation_threshold_mdeg",
        type=float,
        default=10.0,
        help="Resample IF FOVs and re-solve when the fitted IF->ref rotation exceeds this (millidegrees).",
    )
    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    out = os.path.join(args.output_dir, args.prefix)

    ref_files = raw_tile_files(args.ref_round_dir, args.ref_channel)
    if_files = raw_tile_files(args.if_round_dir, args.if_channel)
    names = sorted(set(ref_files) & set(if_files))
    if not names:
        raise ValueError("The ref and IF rounds share no positions")
    for rnd, a, b in (("ref", ref_files, if_files), ("IF", if_files, ref_files)):
        only = sorted(set(a) - set(b))
        if only:
            print(
                f"[WARN] {len(only)} positions only in the {rnd} round, not stitched: "
                + " ".join(os.path.splitext(f)[0] for f in only)
            )
    config_file = write_nominal_config(
        args.output_dir,
        names,
        args.config_name,
        args.maf_file,
        args.position_offset,
        args.project_name,
        args.pixel_size_um,
        args.image_xy,
        args.overlap_ratio,
        args.invert_y,
    )

    ref_reader = st.TiffTxtReader(
        args.ref_round_dir,
        config_file,
        mode="mip",
        rotate90=args.rotate90,
        files=ref_files,
    )
    if_reader = st.TiffTxtReader(
        args.if_round_dir,
        config_file,
        mode="mip",
        rotate90=args.rotate90,
        files=if_files,
    )
    n = ref_reader.metadata.num_images
    cache = {}

    D = coarse_nominal_offset(
        JointReader(ref_reader, if_reader, 0, cache=cache),
        ref_reader.metadata.positions,
    )
    print(
        f"[Joint] coarse IF offset vs ref (y, x) = ({D[0]:.1f}, {D[1]:.1f}) px (1/{COARSE_SCALE} nominal mosaics)"
    )

    max_shift_px = args.max_shift_frac * ref_reader.tile_size_val.astype(float)

    def solve(if_transform):
        reader = JointReader(
            ref_reader, if_reader, D, if_transform=if_transform, cache=cache
        )
        aligner = st.MSTEdgeAligner(
            reader,
            outlier_sigma=args.shift_outlier_sigma,
            position_solver="lsq",
            lsq_max_residual_px=args.lsq_max_residual_px,
            tile_group=["ref"] * n + ["IF"] * n,
            channel=0,
            max_shift=max_shift_px * reader.metadata.pixel_size,
            filter_sigma=args.filter_sigma,
            do_make_thumbnail=False,
            verbose=True,
        )
        aligner.run()
        return aligner

    aligner = solve(None)
    # Single-round positions of the unrotated FOVs, reused for every later fit.
    P, Q = single_round_positions(aligner, n)
    if_transform = None
    a_new, rotation = fit_if_similarity(aligner.edge_table, n, P, Q)
    print(
        f"[Joint] IF->ref similarity: rotation {rotation['rotation_mdeg']:+.1f} mdeg, "
        f"scale {rotation['scale_ppm']:+.0f} ppm ({rotation['edges_used']} cross edges, "
        f"fit residual median {rotation['residual_median_px']:.2f} px)"
    )
    if abs(rotation["rotation_mdeg"]) > args.rotation_threshold_mdeg:
        st.write_mst_edge_diagnostics(aligner, f"{out}_pass1_edge_alignment.csv")
        # Cross matches improve once IF FOVs are rotated, which sharpens the
        # estimate; iterate until the fitted rotation stops changing.
        for _ in range(3):
            if_transform = a_new
            print("[Joint] re-solving with resampled IF FOVs")
            aligner = solve(if_transform)
            a_new, rotation = fit_if_similarity(aligner.edge_table, n, P, Q)
            print(
                f"[Joint] IF->ref similarity: rotation {rotation['rotation_mdeg']:+.1f} mdeg, "
                f"scale {rotation['scale_ppm']:+.0f} ppm ({rotation['edges_used']} cross edges, "
                f"fit residual median {rotation['residual_median_px']:.2f} px)"
            )
            if abs(np.angle(a_new / if_transform)) < np.radians(1e-3):
                break
    else:
        print(
            f"[Joint] rotation below {args.rotation_threshold_mdeg:g} mdeg: IF FOVs used as is"
        )
    st.write_mst_edge_diagnostics(aligner, f"{out}_edge_alignment.csv")

    pos = aligner.positions
    names = ref_reader.metadata.filename
    pd.DataFrame(
        {
            "round": ["ref"] * n + ["IF"] * n,
            "filename": list(names) * 2,
            "global_y": pos[:, 0],
            "global_x": pos[:, 1],
        }
    ).to_csv(f"{out}_coordinates.csv", index=False)
    cfg_ref = os.path.join(args.output_dir, args.ref_config_name)
    cfg_if = os.path.join(args.output_dir, args.if_config_name)
    write_tile_config(cfg_ref, names, pos[:n])
    write_tile_config(cfg_if, names, pos[n:])

    # Per-FOV IF->ref registration in the shared frame (replaces the per-tile
    # IF registration shifts of the old pipeline).
    shift = pos[n:] - pos[:n]
    pd.DataFrame(
        {
            "position": [os.path.splitext(st.tileconfig_name(f))[0] for f in names],
            "ref_y": pos[:n, 0],
            "ref_x": pos[:n, 1],
            "if_y": pos[n:, 0],
            "if_x": pos[n:, 1],
            "shift_y": shift[:, 0],
            "shift_x": shift[:, 1],
            "if_rotation_mdeg": rotation["rotation_mdeg"],
            "if_tile_transform_applied": if_transform is not None,
        }
    ).to_csv(f"{out}_if_fov_shifts.csv", index=False)

    # Direct stitching re-origins each config to its own minimum; record how the
    # two resulting canvases map onto each other.
    e = aligner.edge_table
    groups = {}
    for g, sub in e.groupby("group"):
        r = sub.loc[sub.lsq_active & sub.inlier, "lsq_residual_px"]
        groups[g] = dict(
            edges=int(len(sub)),
            inlier=int(sub.inlier.sum()),
            rescued=int(sub.rescued_by_loop.sum()),
            lsq_removed=int(sub.lsq_removed.sum()),
            residual_median=float(r.median()) if len(r) else None,
            residual_p90=float(r.quantile(0.9)) if len(r) else None,
            residual_max=float(r.max()) if len(r) else None,
        )
    origin_ref, origin_if = pos[:n].min(axis=0), pos[n:].min(axis=0)
    summary = dict(
        coarse_if_offset_yx=D.tolist(),
        edge_groups=groups,
        canvas_origin_ref_yx=origin_ref.tolist(),
        canvas_origin_if_yx=origin_if.tolist(),
        if_canvas_to_ref_canvas_yx=(origin_if - origin_ref).tolist(),
        estimated_if_to_ref_similarity=rotation,
        if_tile_transform=(
            None
            if if_transform is None
            else dict(
                complex_a=[float(if_transform.real), float(if_transform.imag)],
                matrix_yx=tile_transform_matrix(if_transform)[0].tolist(),
                note="each IF FOV is resampled about its centre by z -> a*z (z = x + i*y) before placement; "
                "direct stitching of IF channels must apply the same transform (--tile_transform_json)",
            )
        ),
        note="ref_canvas_px = if_canvas_px + if_canvas_to_ref_canvas_yx (canvases from direct stitching each config)",
        tile_config_ref=cfg_ref,
        tile_config_if=cfg_if,
        if_fov_shifts=f"{out}_if_fov_shifts.csv",
    )
    with open(f"{out}_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    for g, v in groups.items():
        res = "/".join(
            "n/a" if v[k] is None else f"{v[k]:.2f}"
            for k in ("residual_median", "residual_p90", "residual_max")
        )
        print(
            f"[Joint] {g:7s} edges={v['edges']:4d} inlier={v['inlier']:4d} rescued={v['rescued']:3d} "
            f"residual median/p90/max = {res} px"
        )
    d = summary["if_canvas_to_ref_canvas_yx"]
    print(f"[Joint] ref_canvas = IF_canvas + ({d[0]:.2f}, {d[1]:.2f}) px")
    print(
        f"[Joint] wrote {cfg_ref}, {cfg_if}, {out}_if_fov_shifts.csv, {out}_summary.json"
    )


if __name__ == "__main__":
    main()
