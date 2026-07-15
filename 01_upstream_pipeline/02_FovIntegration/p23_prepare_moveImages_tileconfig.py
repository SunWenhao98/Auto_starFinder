#!/usr/bin/env python3
"""
Build shifted TileConfiguration and raw-channel layout for direct mosaic stitching.

This path-level worker reads registered coordinates, applies per-position
registration shifts, materializes raw channel images under raw-<channel>/, and
writes a shifted TileConfiguration whose entries are bare PositionXXX.tif names.
"""

import argparse
import csv
import re
import shutil
import sys
from pathlib import Path


def build_parser():
    parser = argparse.ArgumentParser(
        description="Prepare raw channel layout and shifted TileConfiguration for direct stitching"
    )
    parser.add_argument("--work_dir", required=True, type=Path)
    parser.add_argument("--raw_round_dir", required=True, type=Path)
    parser.add_argument("--registration_dir", required=True, type=Path)
    parser.add_argument("--registered_config", required=True, type=Path)
    parser.add_argument("--shifted_config_name", required=True)
    parser.add_argument("--registration_log_name", required=True)
    parser.add_argument(
        "--channel_names",
        required=True,
        help="Comma-separated channel names matching raw PositionXXX/*ch0x.tif numeric order.",
    )
    parser.add_argument(
        "--output_format",
        choices=["preserve", "uint8", "uint16"],
        default="preserve",
        help="Format for materialized raw-<channel> images.",
    )
    parser.add_argument(
        "--rotate90",
        action="store_true",
        help="Rotate IF_registration shift coordinates; does not rotate image pixels.",
    )
    parser.add_argument(
        "--shift_sign",
        type=float,
        default=1.0,
        help="Multiplier for IF_registration shift direction.",
    )
    return parser


if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
    build_parser().parse_args()

import numpy as np
import skimage.io


POSITION_RE = re.compile(r"Position(\d+)", re.IGNORECASE)
SHIFT_RE = re.compile(r"Shifted by\s+([-+0-9.eE\s]+)")
CH_TIF_RE = re.compile(r"ch0*(\d+)", re.IGNORECASE)


def position_name_from_path(path):
    match = POSITION_RE.search(str(path))
    if not match:
        return None
    return f"Position{int(match.group(1)):03d}"


def parse_tile_config(path):
    records = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("dim"):
                continue
            if "(" not in stripped or ")" not in stripped:
                continue
            parts = line.split(";")
            fname = parts[0].strip()
            coords = parts[-1].strip().replace("(", "").replace(")", "")
            vals = [float(v.strip()) for v in coords.split(",")]
            while len(vals) < 3:
                vals.append(0.0)
            pos_name = position_name_from_path(fname)
            if pos_name is None:
                raise ValueError(f"Could not parse PositionXXX from config entry: {fname}")
            records.append(
                {
                    "position": pos_name,
                    "filename": fname,
                    "x": vals[0],
                    "y": vals[1],
                    "z": vals[2],
                }
            )
    return records


def parse_shift_from_log(log_path):
    text = log_path.read_text(errors="ignore")
    matches = SHIFT_RE.findall(text)
    if not matches:
        raise ValueError(f"No 'Shifted by ...' entry found in {log_path}")
    vals = [float(v) for v in matches[-1].split()]
    while len(vals) < 3:
        vals.append(0.0)
    return vals[0], vals[1], vals[2]


def load_shifts(registration_dir, positions, registration_log_name):
    shifts = {}
    missing = []
    for pos in positions:
        log_path = registration_dir / pos / "log" / registration_log_name
        if not log_path.exists():
            missing.append(str(log_path))
            continue
        shifts[pos] = parse_shift_from_log(log_path)
    if missing:
        sample = "\n".join(missing[:5])
        raise FileNotFoundError(f"Missing shift logs, examples:\n{sample}")
    return shifts


def channel_sort_key(path):
    match = CH_TIF_RE.search(path.name)
    if not match:
        raise ValueError(f"Could not parse ch0x token from raw tif name: {path}")
    return int(match.group(1)), path.name


def sorted_channel_tifs(position_dir):
    files = [
        path
        for path in position_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".tif", ".tiff"} and CH_TIF_RE.search(path.name)
    ]
    return sorted(files, key=channel_sort_key)


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


def write_channel_tif(src, dst, output_format):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()

    image = skimage.io.imread(src)
    print(f"[IMAGE] Source={src} shape={image.shape} dtype={image.dtype} output_format={output_format}")
    if output_format == "preserve":
        shutil.copy2(src, dst)
        return

    image = convert_dtype(image, output_format)
    skimage.io.imsave(dst, image, check_contrast=False)


def extract_raw_channels(raw_round_dir, work_dir, channel_names, positions, output_format):
    for pos in positions:
        pos_dir = raw_round_dir / pos
        if not pos_dir.exists():
            raise FileNotFoundError(f"Raw position folder not found: {pos_dir}")
        files = sorted_channel_tifs(pos_dir)
        if len(files) < len(channel_names):
            raise ValueError(
                f"{pos_dir} has {len(files)} ch0x tif files, fewer than channel_names {channel_names}"
            )
        for channel_name, src in zip(channel_names, files):
            dst = work_dir / f"raw-{channel_name}" / f"{pos}.tif"
            write_channel_tif(src, dst, output_format)


def transform_shift(row_shift, col_shift, shift_sign, rotate90):
    if rotate90:
        return shift_sign * col_shift, -shift_sign * row_shift
    return shift_sign * row_shift, shift_sign * col_shift


def write_config(path, records, shifts, shift_sign, rotate90):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Define the number of dimensions we are working on\n")
        handle.write("dim = 3\n\n")
        handle.write("# Define the image coordinates\n")
        for rec in records:
            row_shift, col_shift, z_shift = shifts[rec["position"]]
            y_shift, x_shift = transform_shift(row_shift, col_shift, shift_sign, rotate90)
            x = rec["x"] + x_shift
            y = rec["y"] + y_shift
            z = rec["z"] + shift_sign * z_shift
            fname = f"{rec['position']}.tif"
            handle.write(f"{fname}; ; ({x:.2f}, {y:.2f}, {z:.2f})\n")


def write_shift_csv(path, records, shifts, shift_sign, rotate90):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "position",
                "ref_x",
                "ref_y",
                "shift_y",
                "shift_x",
                "shift_z",
                "applied_shift_y",
                "applied_shift_x",
                "if_x",
                "if_y",
                "if_z",
                "shift_sign",
                "rotate90",
            ]
        )
        for rec in records:
            row_shift, col_shift, z_shift = shifts[rec["position"]]
            y_shift, x_shift = transform_shift(row_shift, col_shift, shift_sign, rotate90)
            writer.writerow(
                [
                    rec["position"],
                    rec["x"],
                    rec["y"],
                    row_shift,
                    col_shift,
                    z_shift,
                    y_shift,
                    x_shift,
                    rec["x"] + x_shift,
                    rec["y"] + y_shift,
                    rec["z"] + shift_sign * z_shift,
                    shift_sign,
                    rotate90,
                ]
            )


def main():
    args = build_parser().parse_args()

    if not args.registered_config.exists():
        raise FileNotFoundError(f"Registered config not found: {args.registered_config}")
    if not args.raw_round_dir.exists():
        raise FileNotFoundError(f"Raw round directory not found: {args.raw_round_dir}")

    args.work_dir.mkdir(parents=True, exist_ok=True)
    output_config = args.work_dir / args.shifted_config_name

    records = parse_tile_config(args.registered_config)
    positions = [r["position"] for r in records]
    shifts = load_shifts(args.registration_dir, positions, args.registration_log_name)
    channel_names = [c.strip() for c in args.channel_names.split(",") if c.strip()]
    if not channel_names:
        raise ValueError("No channel names configured.")

    extract_raw_channels(args.raw_round_dir, args.work_dir, channel_names, positions, args.output_format)
    write_config(output_config, records, shifts, args.shift_sign, args.rotate90)
    shift_csv = args.work_dir / "if_registration_shifts.csv"
    write_shift_csv(shift_csv, records, shifts, args.shift_sign, args.rotate90)

    print(f"Registered config: {args.registered_config}")
    print(f"Wrote shifted config: {output_config}")
    print(f"Materialized raw channel dirs: {', '.join('raw-' + c for c in channel_names)}")
    print(f"Output format: {args.output_format}")
    print(f"Rotate shift coordinates for rotated FOV pixels: {args.rotate90}")
    print(f"Wrote shift table: {shift_csv}")


if __name__ == "__main__":
    main()
