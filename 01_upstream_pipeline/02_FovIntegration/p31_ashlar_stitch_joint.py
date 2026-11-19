#!/usr/bin/env python3
"""Joint ref/IF/optional seqE stitching with independent FOV lists.

Each round keeps its own nominal coordinates and filenames. Overlapping FOVs
from all rounds enter one MST/LSQ problem; no intersection of FOV lists is taken.
The moving rounds' similarities to ref are estimated independently from measured
cross-round edges and unrotated within-round positions. A round whose rotation
exceeds the threshold is resampled about each tile centre before all rounds are
solved together again. Tile configurations and the summary describe one shared
canvas, including moving FOVs without a same-name reference FOV.
"""

import argparse
import importlib.util
import json
import os

import networkx as nx
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
    """Concatenate ref, IF and optional seqE without changing their FOV lists."""

    def __init__(self, readers, offsets=None, transforms=None, cache=None):
        self.readers = readers
        self.rounds = [name for name in ("ref", "IF", "seqE") if name in readers]
        self.transforms = {} if transforms is None else transforms
        self._raw = {} if cache is None else cache
        offsets = {} if offsets is None else offsets
        self.slices = {}
        first = 0
        for name in self.rounds:
            count = readers[name].metadata.num_images
            self.slices[name] = slice(first, first + count)
            first += count
        self.node_round = np.concatenate(
            [np.repeat(name, readers[name].metadata.num_images) for name in self.rounds]
        )
        self.node_index = np.concatenate(
            [np.arange(readers[name].metadata.num_images) for name in self.rounds]
        )

        class Meta:
            pass

        m = Meta()
        rm = readers["ref"].metadata
        m.num_images = first
        m.num_channels = 1
        m.pixel_size = rm.pixel_size
        m.positions = np.vstack(
            [readers[name].metadata.positions + offsets.get(name, 0) for name in self.rounds]
        )
        m.size = rm.size
        m.filename = [
            f"{name}/{filename}"
            for name in self.rounds
            for filename in readers[name].metadata.filename
        ]
        m.origin = m.positions.min(axis=0)
        m.pixel_dtype = rm.pixel_dtype
        self._meta = m

    @property
    def metadata(self):
        return self._meta

    def read(self, series, c):
        name = self.node_round[series]
        if series not in self._raw:
            self._raw[series] = self.readers[name].read(self.node_index[series], c)
        img = self._raw[series]
        transform = self.transforms.get(name)
        if transform is not None:
            img = resample_tile(img, transform)
        return img


class JointEdgeAligner(st.MSTEdgeAligner):
    """Use rectangle overlap, including coincident FOVs from different rounds."""

    @property
    def neighbors_graph(self):
        if not hasattr(self, "_neighbors_graph"):
            positions = self.metadata.positions
            graph = nx.Graph()
            graph.add_nodes_from(range(self.metadata.num_images))
            for i in range(len(positions)):
                overlap = self.metadata.size - np.abs(positions[i + 1 :] - positions[i])
                neighbors = np.flatnonzero(np.all(overlap > 0, axis=1)) + i + 1
                graph.add_edges_from((i, int(j)) for j in neighbors)
            self._neighbors_graph = graph
        return self._neighbors_graph


def coarse_nominal_offset(reader, scale=COARSE_SCALE):
    """Moving-to-ref translations from independent layouts on a common coarse canvas."""
    size = (np.array(reader.metadata.size) // scale).astype(int)
    positions = reader.metadata.positions
    pos = np.round((positions - positions.min(axis=0)) / scale).astype(int)
    shape = pos.max(axis=0) + size
    mosaics = {}
    masks = {}
    for name, section in reader.slices.items():
        m = np.zeros(shape, np.float32)
        valid = np.zeros(shape, bool)
        for k in range(section.start, section.stop):
            img = reader.read(k, 0).astype(np.float32)
            small = (
                img[: size[0] * scale, : size[1] * scale]
                .reshape(size[0], scale, size[1], scale)
                .mean(axis=(1, 3))
            )
            y, x = pos[k]
            m[y : y + size[0], x : x + size[1]] = small
            valid[y : y + size[0], x : x + size[1]] = True
        # Missing FOVs are unobserved pixels, not dark signal. Normalize the
        # smoothing at coverage boundaries and correlate only measured areas;
        # otherwise differing bright footprints can dominate the coarse shift.
        smoothed = scipy.ndimage.gaussian_filter(m, 1.5)
        weight = scipy.ndimage.gaussian_filter(valid.astype(np.float32), 1.5)
        np.divide(smoothed, weight, out=m, where=valid)
        mosaics[name] = m
        masks[name] = valid
    offsets = {}
    for name in reader.rounds[1:]:
        shift, _, _ = skimage.registration.phase_cross_correlation(
            mosaics["ref"], mosaics[name],
            reference_mask=masks["ref"], moving_mask=masks[name],
        )
        offsets[name] = shift * scale
    return offsets


def single_round_positions(aligner, sections):
    """Solve each unrotated round using only its own edges from the first pass."""
    e = aligner.edge_table
    use = (e.inlier | (e.edge_source == "fallback")).to_numpy() & (
        ~e.group.str.contains("|", regex=False)
    ).to_numpy()
    pos, _, _, _ = aligner.solve_lsq_positions(use)
    return {name: pos[section] for name, section in sections.items()}


def fit_round_similarity(edge_table, name, sections, unrotated_positions):
    """Fit moving-to-ref similarity from measured edges and fixed unrotated layouts."""
    e = edge_table
    x = e[(e.group == f"ref|{name}") & e.inlier]
    # A translation-only joint fit can reject correct edges before rotation is
    # corrected. Refit their image measurements under the similarity model here.
    if x.empty:
        raise ValueError(f"{name}: no measured cross-round edges support a transform to ref")
    obs = (
        unrotated_positions["ref"][x.tile1.to_numpy() - sections["ref"].start]
        + x[["nominal_delta_y_px", "nominal_delta_x_px"]].to_numpy()
        + x[["shift_y_px", "shift_x_px"]].to_numpy()
    )
    q = unrotated_positions[name][x.tile2.to_numpy() - sections[name].start]
    zq, zo = q[:, 1] + 1j * q[:, 0], obs[:, 1] + 1j * obs[:, 0]
    keep = np.ones(len(zq), dtype=bool)
    for iteration in range(4):
        # Empty or repeated-location matches otherwise give a zero/rank-deficient
        # least-squares transform without raising a native NumPy error.
        centre_q, centre_o = np.mean(zq[keep]), np.mean(zo[keep])
        A = np.c_[zq[keep] - centre_q, np.ones(keep.sum())]
        (a, intercept), _, rank, _ = np.linalg.lstsq(A, zo[keep] - centre_o, rcond=None)
        if rank != 2 or not np.isfinite(a) or abs(a) == 0:
            raise ValueError(f"{name}: cross-round measurements do not identify a finite similarity")
        b = centre_o + intercept - a * centre_q
        r = np.abs(a * zq + b - zo)
        if iteration == 3:
            break
        mad = 1.4826 * np.median(np.abs(r[keep] - np.median(r[keep])))
        next_keep = r <= np.median(r[keep]) + 4 * max(mad, 0.1)
        if np.array_equal(next_keep, keep):
            break
        keep = next_keep
    return a, dict(
        complex_a=[float(a.real), float(a.imag)],
        rotation_mdeg=float(np.degrees(np.angle(a)) * 1000),
        scale_ppm=float((abs(a) - 1) * 1e6),
        edges_used=int(keep.sum()),
        residual_median_px=float(np.median(r[keep])),
    )


def check_round_support(aligner, node_round):
    """Every moving component must reach ref without a guessed cross-round edge."""
    e = aligner.edge_table
    if e.empty:
        raise ValueError("No overlapping measurements connect the imaging rounds")
    active = e[e.lsq_active]
    # Within-round fallback still keeps low-texture FOVs in their native layout;
    # a fallback between rounds cannot establish their relative coordinate frame.
    support = active[active.inlier | ~active.group.str.contains("|", regex=False)]
    graph = nx.Graph()
    graph.add_nodes_from(range(len(node_round)))
    graph.add_edges_from(zip(support.tile1, support.tile2))
    for component in nx.connected_components(graph):
        rounds = set(node_round[list(component)])
        if "ref" not in rounds:
            raise ValueError(
                f"{','.join(sorted(rounds))}: {len(component)} FOVs have no measured connection to ref"
            )


def write_tile_config(path, filenames, positions):
    with open(path, "x") as f:
        f.write("# Define the number of dimensions we are working on\n")
        f.write("dim = 3\n\n")
        f.write("# Define the image coordinates\n")
        for fname, (y, x) in zip(filenames, positions):
            f.write(f"{fname}; ; ({x:.2f}, {y:.2f}, 0.0)\n")


def main():
    parser = argparse.ArgumentParser(
        description="Joint ashlar stitching of ref, IF and optional seqE in one canvas"
    )
    parser.add_argument(
        "--ref_dir",
        required=True,
        help="Per-FOV ref-round DAPI images (e.g. raw-refDAPI)",
    )
    parser.add_argument(
        "--if_dir", required=True, help="Per-FOV IF-round DAPI images (e.g. raw-DAPI)"
    )
    parser.add_argument(
        "--config_file",
        required=True,
        help="Nominal TileConfiguration of the ref round",
    )
    parser.add_argument(
        "--if_config_file", default=None,
        help="IF nominal coordinates/FOV list; defaults to --config_file for two-round compatibility",
    )
    parser.add_argument("--seqe_dir", default=None, help="Optional seqE DAPI tile directory")
    parser.add_argument("--seqe_config_file", default=None, help="Independent seqE nominal coordinates/FOV list")
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--prefix", default="joint_ref-IF")
    parser.add_argument("--ref_config_name", default="TileConfiguration.joint_ref.txt")
    parser.add_argument("--if_config_name", default="TileConfiguration.joint_IF.txt")
    parser.add_argument("--seqe_config_name", default="TileConfiguration.joint_seqE.txt")
    parser.add_argument("--max_shift_frac", type=float, default=0.05)
    parser.add_argument("--filter_sigma", type=float, default=3.0)
    parser.add_argument("--shift_outlier_sigma", type=float, default=5.0)
    parser.add_argument("--lsq_max_residual_px", type=float, default=3.0)
    parser.add_argument("--rotate90", action="store_true", default=False)
    parser.add_argument(
        "--rotation_threshold_mdeg",
        type=float,
        default=10.0,
        help="Resample each moving round when its fitted rotation to ref exceeds this (millidegrees).",
    )
    args = parser.parse_args()
    if args.seqe_dir is not None and args.seqe_config_file is None:
        parser.error("--seqe_dir requires --seqe_config_file")
    output_dir = os.path.abspath(args.output_dir)
    out = os.path.join(output_dir, args.prefix)
    inputs = {
        "ref": (args.ref_dir, args.config_file),
        "IF": (args.if_dir, args.if_config_file or args.config_file),
    }
    config_paths = {
        "ref": os.path.join(output_dir, args.ref_config_name),
        "IF": os.path.join(output_dir, args.if_config_name),
    }
    if args.seqe_dir is not None:
        inputs["seqE"] = (args.seqe_dir, args.seqe_config_file)
        config_paths["seqE"] = os.path.join(output_dir, args.seqe_config_name)
    coordinate_paths = {name: f"{out}_{name.lower()}_coordinates.csv" for name in inputs}
    shift_paths = {name: f"{out}_{name.lower()}_fov_shifts.csv" for name in inputs if name != "ref"}
    outputs = list(config_paths.values()) + list(coordinate_paths.values()) + list(shift_paths.values()) + [
        f"{out}_coordinates.csv", f"{out}_edge_alignment.csv",
        f"{out}_pass1_edge_alignment.csv", f"{out}_summary.json",
    ]
    # Inputs and outputs may share a workdir, so protect these exact output paths.
    destinations = [os.path.realpath(path) for path in outputs]
    if len(set(destinations)) != len(destinations):
        raise ValueError("Joint output paths collide")
    for path in outputs:
        if os.path.lexists(path):
            raise FileExistsError(f"Refusing to overwrite joint output: {path}")

    readers = {
        name: st.TiffTxtReader(directory, config, mode="mip", rotate90=args.rotate90)
        for name, (directory, config) in inputs.items()
    }
    for name, reader in readers.items():
        filenames = reader.metadata.filename
        if len(set(filenames)) != len(filenames):
            raise ValueError(f"{name}: repeated FOV filenames cannot identify output tiles uniquely")
        # Ashlar's pair registration uses one shared metadata.size for all tiles.
        # A different round shape would otherwise silently use incorrect crops.
        if not np.array_equal(reader.metadata.size, readers["ref"].metadata.size):
            raise ValueError(f"{name}: tile XY dimensions differ from ref; joint Ashlar needs one tile size")

    os.makedirs(output_dir, exist_ok=True)
    cache = {}
    layout = JointReader(readers, cache=cache)
    offsets = coarse_nominal_offset(layout)
    moving_rounds = layout.rounds[1:]
    for name in moving_rounds:
        offset = offsets[name]
        print(
            f"[Joint] {name}: {readers[name].metadata.num_images} FOVs, "
            f"coarse offset vs ref (y, x) = ({offset[0]:.1f}, {offset[1]:.1f}) px"
        )

    max_shift_px = args.max_shift_frac * readers["ref"].tile_size_val.astype(float)

    def solve(transforms):
        reader = JointReader(readers, offsets, transforms, cache)
        aligner = JointEdgeAligner(
            reader,
            outlier_sigma=args.shift_outlier_sigma,
            position_solver="lsq",
            lsq_max_residual_px=args.lsq_max_residual_px,
            tile_group=reader.node_round,
            channel=0,
            max_shift=max_shift_px * reader.metadata.pixel_size,
            filter_sigma=args.filter_sigma,
            do_make_thumbnail=False,
            verbose=True,
        )
        aligner.run()
        if aligner.edge_table.empty:
            raise ValueError("No overlapping measurements connect the imaging rounds")
        return aligner

    transforms = {name: None for name in moving_rounds}
    aligner = solve(transforms)
    # Keep these unrotated within-round layouts fixed through all joint passes.
    unrotated_positions = single_round_positions(aligner, layout.slices)
    refinement_passes = 0
    for iteration in range(4):
        estimates = {}
        updates = {}
        for name in moving_rounds:
            a, estimate = fit_round_similarity(
                aligner.edge_table, name, layout.slices, unrotated_positions
            )
            estimates[name] = estimate
            print(
                f"[Joint] {name}->ref similarity: rotation {estimate['rotation_mdeg']:+.1f} mdeg, "
                f"scale {estimate['scale_ppm']:+.0f} ppm ({estimate['edges_used']} cross edges, "
                f"fit residual median {estimate['residual_median_px']:.2f} px)"
            )
            applied = transforms[name]
            needs_update = (
                abs(estimate["rotation_mdeg"]) > args.rotation_threshold_mdeg
                if applied is None
                else abs(np.angle(a / applied)) >= np.radians(1e-3)
            )
            estimate["rotation_converged"] = not needs_update
            if needs_update:
                updates[name] = a
        if not updates or iteration == 3:
            break
        if iteration == 0:
            st.write_mst_edge_diagnostics(aligner, f"{out}_pass1_edge_alignment.csv")
        transforms.update(updates)
        print(f"[Joint] joint re-solve after resampling: {', '.join(updates)}")
        aligner = solve(transforms)
        refinement_passes += 1

    check_round_support(aligner, layout.node_round)
    st.write_mst_edge_diagnostics(aligner, f"{out}_edge_alignment.csv")

    # Keep the existing 0.01-pixel configuration precision and derive the canvas
    # from those exact exported coordinates, so every channel uses one geometry.
    pos = np.round(aligner.positions, 2)
    coordinate_tables = {}
    round_summary = {}
    for name in layout.rounds:
        section = layout.slices[name]
        names = readers[name].metadata.filename
        coordinates = pd.DataFrame({
            "round": name, "filename": names,
            "global_y": pos[section, 0], "global_x": pos[section, 1],
        })
        coordinate_tables[name] = coordinates
        coordinates.to_csv(coordinate_paths[name], index=False, mode="x")
        write_tile_config(config_paths[name], names, pos[section])
        transform = transforms.get(name)
        round_summary[name] = dict(
            tile_config=config_paths[name],
            tile_count=len(names),
            tile_size_yx=readers[name].metadata.size.tolist(),
            input_dir=os.path.abspath(inputs[name][0]),
            input_config=os.path.abspath(inputs[name][1]),
            coordinates=coordinate_paths[name],
            tile_transform=(
                None if transform is None else dict(
                    complex_a=[float(transform.real), float(transform.imag)],
                    matrix_yx=tile_transform_matrix(transform)[0].tolist(),
                    note="Resample each tile about its centre by z -> a*z before placement.",
                )
            ),
        )
        if name != "ref":
            round_summary[name]["estimated_similarity"] = estimates[name]
            round_summary[name]["fov_shifts"] = shift_paths[name]
    pd.concat(coordinate_tables.values(), ignore_index=True).to_csv(
        f"{out}_coordinates.csv", index=False, mode="x"
    )

    ref_coordinates = coordinate_tables["ref"].set_index("filename")[["global_y", "global_x"]]
    for name in moving_rounds:
        coordinates = coordinate_tables[name]
        # Exact filename keys join diagnostics only; unmatched native FOVs remain
        # in all outputs and receive no invented same-FOV reference coordinates.
        matched = ref_coordinates.reindex(coordinates.filename).to_numpy()
        moving = coordinates[["global_y", "global_x"]].to_numpy()
        nominal = readers[name].metadata.positions
        field_prefix = name.lower()
        pd.DataFrame({
            "position": [os.path.splitext(st.tileconfig_name(f))[0] for f in coordinates.filename],
            "filename": coordinates.filename.to_numpy(),
            "has_matching_ref": coordinates.filename.isin(ref_coordinates.index).to_numpy(),
            "ref_y": matched[:, 0], "ref_x": matched[:, 1],
            f"{field_prefix}_y": moving[:, 0], f"{field_prefix}_x": moving[:, 1],
            "shift_y": moving[:, 0] - matched[:, 0],
            "shift_x": moving[:, 1] - matched[:, 1],
            "nominal_y": nominal[:, 0], "nominal_x": nominal[:, 1],
            "placement_shift_y": moving[:, 0] - nominal[:, 0],
            "placement_shift_x": moving[:, 1] - nominal[:, 1],
            f"{field_prefix}_rotation_mdeg": estimates[name]["rotation_mdeg"],
            f"{field_prefix}_tile_transform_applied": transforms[name] is not None,
        }).to_csv(shift_paths[name], index=False, mode="x")

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
    canvas_origin = pos.min(axis=0)
    tile_sizes = np.vstack([
        np.repeat(readers[name].metadata.size[None, :], readers[name].metadata.num_images, axis=0)
        for name in layout.rounds
    ])
    canvas_shape = np.ceil((pos + tile_sizes).max(axis=0) - canvas_origin).astype(int)
    summary = dict(
        rounds=round_summary,
        canvas_origin_yx=canvas_origin.tolist(),
        canvas_shape_yx=canvas_shape.tolist(),
        rotate90=args.rotate90,
        coarse_offsets_yx={name: offset.tolist() for name, offset in offsets.items()},
        rotation_refinement_passes=refinement_passes,
        max_shift_px_yx=max_shift_px.tolist(),
        filter_sigma=args.filter_sigma,
        shift_outlier_sigma=args.shift_outlier_sigma,
        lsq_max_residual_px=args.lsq_max_residual_px,
        rotation_threshold_mdeg=args.rotation_threshold_mdeg,
        edge_groups=groups,
        note="Every round uses canvas pixel (y, x) = joint coordinate - canvas_origin_yx; "
        "apply its recorded tile transform and rotate90 before placement, without per-round recentering.",
    )
    with open(f"{out}_summary.json", "x") as f:
        json.dump(summary, f, indent=2, allow_nan=False)
    for g, v in groups.items():
        res = "/".join(
            "n/a" if v[k] is None else f"{v[k]:.2f}"
            for k in ("residual_median", "residual_p90", "residual_max")
        )
        print(
            f"[Joint] {g:7s} edges={v['edges']:4d} inlier={v['inlier']:4d} rescued={v['rescued']:3d} "
            f"residual median/p90/max = {res} px"
        )
    print(f"[Joint] shared canvas origin (y, x): {canvas_origin.tolist()}; shape: {canvas_shape.tolist()}")
    print(f"[Joint] wrote {', '.join(config_paths.values())} and {out}_summary.json")


if __name__ == "__main__":
    main()
