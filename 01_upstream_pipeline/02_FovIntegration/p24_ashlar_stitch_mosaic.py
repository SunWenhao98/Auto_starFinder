"""
Ashlar direct stitch from pre-computed TileConfiguration.registered.txt.

This skips EdgeAligner and reuses DAPI-derived coordinates for other IF
channels, for example DAPI -> 488-CD144/561-CA9/647-CD31.
"""

import argparse
import os
import sys


def build_parser():
    parser = argparse.ArgumentParser(
        description="Direct Ashlar mosaic from TileConfiguration.registered.txt"
    )
    parser.add_argument("--input_dir", required=True)
    parser.add_argument(
        "--config_file", required=True, help="Path to TileConfiguration.registered.txt"
    )
    parser.add_argument(
        "--output_image_prefix",
        required=True,
        help="Output prefix, e.g. /path/to/stitched_488-CD144",
    )
    parser.add_argument("--channel_from", type=str, default=None)
    parser.add_argument("--channel_to", type=str, default=None)
    parser.add_argument("--make_3d", type=str, default="false")
    parser.add_argument(
        "--rotate90",
        action="store_true",
        default=False,
        help="Rotate each FOV clockwise by 90 degrees before stitching.",
    )
    parser.add_argument(
        "--pixel_size_um",
        type=float,
        default=1.0,
        help="Physical pixel size in um/pixel for OME output metadata.",
    )
    parser.add_argument(
        "--slice_indices",
        default="",
        help="Comma-separated 1-based z-slice indices to write as extra 2D mosaics, e.g. '1,10,20'.",
    )
    parser.add_argument(
        "--output_format",
        choices=["preserve", "uint8", "uint16"],
        default="preserve",
        help="Output dtype policy before handing tiles to Ashlar.",
    )
    return parser


if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
    build_parser().parse_args()

import numpy as np
import skimage.io
from ashlar import reg
from ashlar.reg import Mosaic, PyramidWriter


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


def convert_dtype(image, output_format):
    output_format = output_format.lower()
    if output_format == "preserve":
        return image
    if output_format == "uint8":
        if image.dtype == np.uint8:
            return image
        if np.issubdtype(image.dtype, np.integer):
            info = np.iinfo(image.dtype)
            return np.clip(image.astype(np.float32) / info.max * 255, 0, 255).astype(np.uint8)
        return (np.clip(image, 0, 1) * 255).astype(np.uint8)
    if output_format == "uint16":
        if image.dtype == np.uint16:
            return image
        if np.issubdtype(image.dtype, np.integer):
            info = np.iinfo(image.dtype)
            return np.clip(image.astype(np.float32) / info.max * 65535, 0, 65535).astype(np.uint16)
        return (np.clip(image, 0, 1) * 65535).astype(np.uint16)
    raise ValueError(f"Unsupported output_format: {output_format}")


def output_dtype(input_dtype, output_format):
    if output_format == "preserve":
        return input_dtype
    return np.dtype(output_format)


def _replace_channel_path(fname, channel_from, channel_to):
    if not channel_from or not channel_to:
        return fname

    from_name = channel_from.strip().lower()
    to_name = channel_to.strip()
    parts = fname.replace("\\", "/").split("/")
    for idx, part in enumerate(parts):
        if part.lower() == from_name:
            parts[idx] = to_name
            return "/".join(parts)

    filename = parts[-1]
    filename_lower = filename.lower()
    token_idx = filename_lower.find(from_name)
    if token_idx >= 0:
        parts[-1] = (
            filename[:token_idx]
            + to_name
            + filename[token_idx + len(from_name):]
        )
        return "/".join(parts)

    raise ValueError(
        f"Could not replace channel token '{channel_from}' in '{fname}'. "
        "Use a real channel folder name such as DAPI/488-CD144, or a "
        "filename token such as ch03."
    )


class TiffDirectReader(reg.PlateReader):
    """Reader that exposes TileConfiguration coordinates to Ashlar's Mosaic."""

    def __init__(
        self,
        directory,
        config_file,
        channel_from=None,
        channel_to=None,
        mode="mip",
        rotate90=False,
        pixel_size_um=1.0,
        slice_index=None,
        output_format="preserve",
    ):
        self.path = directory
        self.mode = mode
        self.rotate90 = rotate90
        self.pixel_size_um = pixel_size_um
        self.slice_index = slice_index
        self.output_format = output_format
        self.coords_data = self._parse_config(config_file, channel_from, channel_to)

        if not self.coords_data:
            print("Error: No coordinates found in config file!")
            sys.exit(1)

        first_file = os.path.join(self.path, self.coords_data[0]["filename"])
        try:
            img = skimage.io.imread(first_file)
            print(f"[DirectReader] First file: {os.path.basename(first_file)}")
            print(f"[DirectReader] Raw Shape: {img.shape}, Detected input dtype: {img.dtype}")
            print(f"[DirectReader] Stitch output_format: {self.output_format}")

            self.raw_ndim = img.ndim
            self.pixel_dtype = output_dtype(img.dtype, self.output_format)

            if self.raw_ndim == 3:
                self.z_depth = img.shape[0]
                self.tile_size_val = np.array(img.shape[-2:])
            else:
                self.z_depth = 1
                self.tile_size_val = np.array(img.shape)

            if self.rotate90:
                self.tile_size_val = np.array(
                    [self.tile_size_val[1], self.tile_size_val[0]]
                )
                print("[DirectReader] Rotate90 enabled: tile dimensions swapped")

            if self.mode == "slice":
                if self.slice_index is None:
                    raise ValueError("slice mode requires slice_index")
                if self.slice_index < 1 or self.slice_index > self.z_depth:
                    raise ValueError(
                        f"slice_index {self.slice_index} out of range [1, {self.z_depth}]"
                    )

            print(f"[DirectReader] Z-depth: {self.z_depth}")
            print(f"[DirectReader] Tile Size (Y, X): {self.tile_size_val}")
            print(f"[DirectReader] Pixel size: {self.pixel_size_um} um/pixel")
        except Exception as e:
            print(f"Error reading first image {first_file}: {e}")
            sys.exit(1)

    def _parse_config(self, config_file, channel_from, channel_to):
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
                if channel_from and channel_to:
                    fname = _replace_channel_path(fname, channel_from, channel_to)

                coords_str = parts[-1].strip().replace("(", "").replace(")", "")
                try:
                    vals = list(map(float, coords_str.split(",")))
                    data.append({"filename": fname, "x": vals[0], "y": vals[1]})
                except Exception as e:
                    print(f"Warning: Skipping line: {line} -> {e}")
        return data

    @property
    def metadata(self):
        class Meta:
            pass

        m = Meta()
        m.num_images = len(self.coords_data)
        m.num_channels = self.z_depth if self.mode == "stack" else 1
        m.pixel_size = self.pixel_size_um
        m.positions = np.array([[d["y"], d["x"]] for d in self.coords_data])
        m.size = self.tile_size_val
        m.filename = [d["filename"] for d in self.coords_data]
        m.origin = m.positions.min(axis=0)
        m.pixel_dtype = self.pixel_dtype
        return m

    def _apply_rotate90(self, img_2d):
        if self.rotate90:
            return np.rot90(img_2d, k=3)  # clockwise 90 degrees
        return img_2d

    def _finalize_image(self, image):
        image = self._apply_rotate90(image)
        return convert_dtype(image, self.output_format)

    def read(self, series, c):
        fname = self.coords_data[series]["filename"]
        full_path = os.path.join(self.path, fname)
        img = skimage.io.imread(full_path)

        if self.mode == "mip":
            if img.ndim == 3:
                return self._finalize_image(np.max(img, axis=0))
            return self._finalize_image(img)

        if self.mode == "stack":
            if img.ndim == 3:
                z_index = min(c, self.z_depth - 1)
                return self._finalize_image(img[z_index, :, :])
            return self._finalize_image(img)

        if self.mode == "slice":
            if img.ndim == 3:
                return self._finalize_image(img[self.slice_index - 1, :, :])
            if self.slice_index != 1:
                raise ValueError(f"2D input only supports slice_index=1: {full_path}")
            return self._finalize_image(img)

        return self._finalize_image(img)


class DirectAligner:
    """Minimal aligner interface required by ashlar.reg.Mosaic."""

    def __init__(self, reader):
        self.reader = reader
        self.metadata = reader.metadata
        self.origin = self.metadata.positions.min(axis=0)
        self.positions = self.metadata.positions - self.origin
        self.centers = self.positions + self.metadata.size / 2

    @property
    def mosaic_shape(self):
        upper = self.positions + self.metadata.size
        return tuple(np.ceil(upper.max(axis=0)).astype(int))


def main():
    args = build_parser().parse_args()
    do_make_3d = args.make_3d.lower() == "true"
    slice_indices = parse_slice_indices(args.slice_indices)

    os.makedirs(os.path.dirname(args.output_image_prefix), exist_ok=True)

    path_2d = f"{args.output_image_prefix}_2d.ome.tif"
    path_3d = f"{args.output_image_prefix}_3d.ome.tif"

    channel_info = ""
    if args.channel_from and args.channel_to:
        channel_info = f" (replacing {args.channel_from} -> {args.channel_to})"
    print(f"=== Direct Stitch{channel_info} ===")
    print(f"Config: {args.config_file}")
    print(f"Output Prefix: {args.output_image_prefix}")
    print(f"Output format: {args.output_format}")

    print("\n=== Phase 1: Writing 2D MIP Mosaic (Direct, no alignment) ===")
    reader_2d = TiffDirectReader(
        args.input_dir,
        args.config_file,
        channel_from=args.channel_from,
        channel_to=args.channel_to,
        mode="mip",
        rotate90=args.rotate90,
        pixel_size_um=args.pixel_size_um,
        output_format=args.output_format,
    )
    aligner_2d = DirectAligner(reader_2d)

    mosaic_2d = Mosaic(aligner=aligner_2d, shape=aligner_2d.mosaic_shape, verbose=True)
    writer_2d = PyramidWriter(
        mosaics=[mosaic_2d], path=path_2d, scale=2, tile_size=1024, verbose=True
    )
    writer_2d.run()
    print(f"2D Image saved: {path_2d}")

    for slice_index in slice_indices:
        path_slice = f"{args.output_image_prefix}_z{slice_index:03d}_2d.ome.tif"
        print(f"\n=== Phase 2: Writing Z-slice {slice_index} Mosaic ===")
        reader_slice = TiffDirectReader(
            args.input_dir,
            args.config_file,
            channel_from=args.channel_from,
            channel_to=args.channel_to,
            mode="slice",
            rotate90=args.rotate90,
            pixel_size_um=args.pixel_size_um,
            slice_index=slice_index,
            output_format=args.output_format,
        )
        aligner_slice = DirectAligner(reader_slice)

        mosaic_slice = Mosaic(
            aligner=aligner_slice, shape=aligner_slice.mosaic_shape, verbose=True
        )
        writer_slice = PyramidWriter(
            mosaics=[mosaic_slice], path=path_slice, scale=2, tile_size=1024, verbose=True
        )
        writer_slice.run()
        print(f"Z-slice {slice_index} image saved: {path_slice}")

    if do_make_3d:
        print("\n=== Phase 3: Writing 3D Stack Mosaic ===")
        reader_3d = TiffDirectReader(
            args.input_dir,
            args.config_file,
            channel_from=args.channel_from,
            channel_to=args.channel_to,
            mode="stack",
            rotate90=args.rotate90,
            pixel_size_um=args.pixel_size_um,
            output_format=args.output_format,
        )
        aligner_3d = DirectAligner(reader_3d)

        mosaic_3d = Mosaic(
            aligner=aligner_3d, shape=aligner_3d.mosaic_shape, verbose=True
        )
        writer_3d = PyramidWriter(
            mosaics=[mosaic_3d], path=path_3d, scale=2, tile_size=1024, verbose=True
        )
        writer_3d.run()
        print(f"3D Image saved: {path_3d}")

    print("\nDirect stitch complete.")


if __name__ == "__main__":
    main()
