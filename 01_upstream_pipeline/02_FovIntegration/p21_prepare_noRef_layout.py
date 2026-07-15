#!/usr/bin/env python3
"""Prepare extra channel folders for strict TileConfiguration stitching.

Input layout example:
  round011/Position001/*_ch03.tif

Output layout example:
  IFnew_uint8/TE-DAPI/Position001.tif
"""

import argparse
import csv
import os
import re
import shutil
from pathlib import Path



POSITION_RE = re.compile(r"Position(\d+)", re.IGNORECASE)


def position_name(path):
    match = POSITION_RE.search(str(path))
    if not match:
        return None
    return f"Position{int(match.group(1)):03d}"


def parse_channels(spec):
    channels = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        sep = "=" if "=" in item else ":"
        if sep not in item:
            raise ValueError(
                f"Invalid channel spec '{item}'. Expected format like ch03=TE-DAPI."
            )
        token, dirname = [x.strip() for x in item.split(sep, 1)]
        if not token or not dirname:
            raise ValueError(f"Invalid channel spec '{item}'.")
        channels.append((token, dirname))
    if not channels:
        raise ValueError("No TE channels configured.")
    return channels


def sorted_position_dirs(raw_round_dir):
    dirs = []
    for path in raw_round_dir.iterdir():
        if path.is_dir() and position_name(path):
            dirs.append(path)
    return sorted(dirs, key=lambda p: int(POSITION_RE.search(p.name).group(1)))


def find_channel_file(position_dir, token):
    token = token.lower()
    candidates = []
    for path in position_dir.iterdir():
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in {".tif", ".tiff"}:
            continue
        if token in path.name.lower():
            candidates.append(path)
    candidates = sorted(candidates, key=lambda p: p.name)
    if not candidates:
        raise FileNotFoundError(f"No *{token}*.tif found in {position_dir}")
    if len(candidates) > 1:
        print(
            f"[WARN] Multiple files matched {token} in {position_dir}; "
            f"using {candidates[0].name}"
        )
    return candidates[0]


def convert_dtype(image, output_format):
    import numpy as np

    output_format = output_format.lower()
    if output_format == "preserve":
        return image
    if output_format == "uint8":
        if image.dtype == np.uint8:
            return image
        if np.issubdtype(image.dtype, np.integer):
            info = np.iinfo(image.dtype)
            return np.clip(image.astype(np.float32) / info.max * 255, 0, 255).astype(
                np.uint8
            )
        return (np.clip(image, 0, 1) * 255).astype(np.uint8)
    if output_format == "uint16":
        if image.dtype == np.uint16:
            return image
        if np.issubdtype(image.dtype, np.integer):
            info = np.iinfo(image.dtype)
            return np.clip(
                image.astype(np.float32) / info.max * 65535, 0, 65535
            ).astype(np.uint16)
        return (np.clip(image, 0, 1) * 65535).astype(np.uint16)
    raise ValueError(f"Unsupported output_format: {output_format}")


def write_output(src, dst, link_mode, output_format):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()

    if output_format != "preserve":
        import skimage.io

        image = skimage.io.imread(src)
        image = convert_dtype(image, output_format)
        skimage.io.imsave(dst, image, check_contrast=False)
        return

    if link_mode == "copy":
        shutil.copy2(src, dst)
    elif link_mode == "hardlink":
        os.link(src, dst)
    else:
        rel_src = os.path.relpath(src, dst.parent)
        os.symlink(rel_src, dst)


def main():
    parser = argparse.ArgumentParser(description="Prepare extra channel layout")
    parser.add_argument("--raw_round_dir", required=True, type=Path)
    parser.add_argument("--output_dir", required=True, type=Path)
    parser.add_argument(
        "--channels",
        default="ch00=raw-561-CA9,ch01=raw-488-CD144,ch02=raw-647-CD31,ch03=raw-DAPI",
        help="Comma-separated raw-token:output-dir mapping.",
    )
    parser.add_argument("--manifest_name", default="extra_layout_manifest.csv")
    parser.add_argument(
        "--link_mode",
        choices=["symlink", "hardlink", "copy"],
        default="copy",
        help="Used only when output_format=preserve.",
    )
    parser.add_argument(
        "--output_format",
        choices=["preserve", "uint8", "uint16"],
        default="preserve",
    )
    args = parser.parse_args()

    if not args.raw_round_dir.exists():
        raise FileNotFoundError(f"Raw image directory not found: {args.raw_round_dir}")

    channels = parse_channels(args.channels)
    positions = sorted_position_dirs(args.raw_round_dir)
    if not positions:
        raise FileNotFoundError(f"No PositionXXX directories found in {args.raw_round_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / args.manifest_name

    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["position", "raw_channel_token", "te_channel", "source", "target"])

        for pos_dir in positions:
            pos = position_name(pos_dir)
            for token, dirname in channels:
                src = find_channel_file(pos_dir, token)
                dst = args.output_dir / dirname / f"{pos}.tif"
                write_output(src, dst, args.link_mode, args.output_format)
                writer.writerow([pos, token, dirname, str(src), str(dst)])

    print(f"Prepared extra channel layout: {args.output_dir}")
    print(f"Positions: {len(positions)}")
    print(f"Channels: {', '.join(dirname for _, dirname in channels)}")
    print(f"Output format: {args.output_format}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
