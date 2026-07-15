#!/usr/bin/env python3
"""Combine TE-nt and TE-rb stitched images into an RGB image."""

import argparse
from pathlib import Path

import numpy as np
import tifffile


def read_first_series(path):
    with tifffile.TiffFile(path) as tif:
        image = tif.series[0].asarray()
    image = np.squeeze(image)
    if image.ndim != 2:
        raise ValueError(f"Expected a 2D image after squeeze, got {image.shape}: {path}")
    return image


def rescale_uint8(image, p_min, p_max):
    lo, hi = np.percentile(image, [p_min, p_max])
    if hi <= lo:
        return np.zeros(image.shape, dtype=np.uint8)
    scaled = (image.astype(np.float32) - lo) / (hi - lo)
    return np.clip(scaled * 255, 0, 255).astype(np.uint8)


def main():
    parser = argparse.ArgumentParser(description="Make TE nt/rb RGB image")
    parser.add_argument("--red_image", required=True, type=Path, help="TE-nt stitched image")
    parser.add_argument("--green_image", required=True, type=Path, help="TE-rb stitched image")
    parser.add_argument("--output_image", required=True, type=Path)
    parser.add_argument(
        "--rescale_to_uint8",
        action="store_true",
        help="Percentile-rescale both channels to uint8 before RGB merge.",
    )
    parser.add_argument("--percentile_min", type=float, default=0.0)
    parser.add_argument("--percentile_max", type=float, default=99.9)
    args = parser.parse_args()

    red = read_first_series(args.red_image)
    green = read_first_series(args.green_image)
    if red.shape != green.shape:
        raise ValueError(
            f"Image shape mismatch: red {red.shape} vs green {green.shape}"
        )

    if args.rescale_to_uint8:
        red = rescale_uint8(red, args.percentile_min, args.percentile_max)
        green = rescale_uint8(green, args.percentile_min, args.percentile_max)
        dtype = np.uint8
    else:
        dtype = np.result_type(red.dtype, green.dtype)
        red = red.astype(dtype, copy=False)
        green = green.astype(dtype, copy=False)

    rgb = np.zeros(red.shape + (3,), dtype=dtype)
    rgb[..., 0] = red
    rgb[..., 1] = green

    args.output_image.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(
        args.output_image,
        rgb,
        bigtiff=True,
        photometric="rgb",
        metadata={"axes": "YXS"},
        ome=True,
    )
    print(f"RGB image saved: {args.output_image}")
    print(f"Red channel: {args.red_image}")
    print(f"Green channel: {args.green_image}")
    print(f"Shape: {rgb.shape}, dtype: {rgb.dtype}")


if __name__ == "__main__":
    main()
