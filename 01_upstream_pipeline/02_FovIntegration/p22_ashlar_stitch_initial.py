import argparse
import os
import sys

import numpy as np
import pandas as pd
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
        type=float,
        default=150.0,
        help="Maximum allowed corrective shift in pixels. Converted to microns for Ashlar.",
    )
    parser.add_argument(
        "--filter_sigma",
        type=float,
        default=1.0,
        help="Gaussian sigma for alignment filtering.",
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
        default="auto",
        help="Explicit Ashlar max_error threshold, or 'auto' to use stitch_alpha.",
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

    effective_max_shift = args.max_shift_px * args.pixel_size_um
    explicit_max_error = None
    if args.max_error.strip().lower() not in {"", "auto", "none", "nan"}:
        explicit_max_error = float(args.max_error)

    aligner_instance = EdgeAligner(
        reader_mip,
        channel=0,
        max_shift=effective_max_shift,
        filter_sigma=args.filter_sigma,
        alpha=args.stitch_alpha,
        max_error=explicit_max_error,
        verbose=True,
    )
    print(
        f"[Ashlar] max_shift: {effective_max_shift} um ~= "
        f"{effective_max_shift / args.pixel_size_um:.1f} px"
    )
    print(f"[Ashlar] stitch_alpha: {args.stitch_alpha}")
    print(f"[Ashlar] explicit max_error: {explicit_max_error if explicit_max_error is not None else 'auto'}")
    try:
        aligner_instance.run()
    except Exception:
        if hasattr(aligner_instance, "neighbors_graph") and hasattr(aligner_instance, "_cache"):
            write_edge_diagnostics(aligner_instance, edge_csv_path)
        raise
    write_edge_diagnostics(aligner_instance, edge_csv_path)

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
