#!/usr/bin/env python3
"""Apply per-FOV registration shifts to a reference TileConfiguration."""

import argparse
import csv
import re
from pathlib import Path


def build_parser():
    parser = argparse.ArgumentParser(
        description="Apply registration shifts to coordinates prepared for raw TIFF layouts"
    )
    parser.add_argument("--work_dir", required=True, type=Path)
    parser.add_argument("--registration_dir", required=True, type=Path)
    parser.add_argument("--registered_config", required=True, type=Path)
    parser.add_argument("--shifted_config_name", required=True)
    parser.add_argument("--registration_log_name", required=True)
    parser.add_argument(
        "--rotate90", action="store_true",
        help="Rotate shift coordinates for rotated FOV pixels.",
    )
    parser.add_argument("--shift_sign", type=float, default=1.0)
    return parser


POSITION_RE = re.compile(r"Position(\d+)", re.IGNORECASE)
SHIFT_RE = re.compile(r"Shifted by\s+([-+0-9.eE\s]+)")


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


def transform_shift(row_shift, col_shift, shift_sign, rotate90):
    if rotate90:
        return shift_sign * col_shift, -shift_sign * row_shift
    return shift_sign * row_shift, shift_sign * col_shift


def write_config(path, records, shifts, shift_sign, rotate90):
    with open(path, "x", encoding="utf-8", newline="\n") as handle:
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
    with open(path, "x", encoding="utf-8", newline="") as handle:
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
                "moving_x",
                "moving_y",
                "moving_z",
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
    output_config = args.work_dir / args.shifted_config_name
    shift_csv = output_config.with_suffix(".shifts.csv")
    for output in (output_config, shift_csv):
        if output.exists() or output.is_symlink():
            raise FileExistsError(f"Output already exists: {output}")

    records = parse_tile_config(args.registered_config)
    positions = [record["position"] for record in records]
    shifts = load_shifts(args.registration_dir, positions, args.registration_log_name)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    write_config(output_config, records, shifts, args.shift_sign, args.rotate90)
    write_shift_csv(shift_csv, records, shifts, args.shift_sign, args.rotate90)

    print(f"Registered config: {args.registered_config}", flush=True)
    print(f"Wrote shifted config: {output_config}", flush=True)
    print(f"Wrote shift table: {shift_csv}", flush=True)


if __name__ == "__main__":
    main()
