#!/usr/bin/env python3
"""Prepare one round's channel layout for explicit TileConfiguration inputs."""

import argparse
import csv
import io
import os
import re
import shutil
from pathlib import Path


POSITION_RE = re.compile(r"Position(\d+)", re.IGNORECASE)
CHANNEL_RE = re.compile(r"(?:^|_)ch0*(\d+)(?=[_.]|$)", re.IGNORECASE)


def parse_channels(spec):
    channels = []
    for item in spec.split(","):
        token, dirname = item.strip().replace(":", "=", 1).split("=", 1)
        channels.append((token, dirname))
    return channels


def find_channel_file(position_dir, token):
    channel_number = int(token.lower().removeprefix("ch"))
    candidates = []
    for path in position_dir.iterdir():
        match = CHANNEL_RE.search(path.name)
        if path.suffix.lower() in {".tif", ".tiff"} and match:
            if int(match.group(1)) == channel_number:
                candidates.append(path)
    # Each requested source channel has one physical acquisition per FOV.
    source, = candidates
    source = source.resolve(strict=True)
    with source.open("rb") as handle:
        handle.read(1)
    return source


def convert_dtype(image, output_format):
    import numpy as np

    if image.dtype == np.dtype(output_format):
        return image
    if np.issubdtype(image.dtype, np.integer):
        values = image.astype(np.float32) / np.iinfo(image.dtype).max
    else:
        values = image
    return (np.clip(values, 0, 1) * np.iinfo(output_format).max).astype(output_format)


def link_file(source, target):
    source = source.resolve(strict=True)
    if target.parent.is_symlink():
        raise FileExistsError(f"Layout output directory is a symlink: {target.parent}")
    target.parent.mkdir(parents=True, exist_ok=True)
    link_target = os.path.relpath(source, target.parent.resolve(strict=True))
    try:
        target.symlink_to(link_target)
    except FileExistsError:
        if target.is_symlink() and target.resolve(strict=True) == source:
            return
        raise FileExistsError(f"Layout target already belongs to another input: {target}")


def link_method_initial_files(method_root, round_manifest, config_name, raw_rounds_dir):
    """Expose one completed method-local MAF result through each round's input path."""
    sources = (method_root / config_name, method_root / "tile_summary.csv")
    with sources[0].open(encoding="utf-8") as handle:
        expected = {
            f"Position{int(match.group(1)):03d}"
            for line in handle
            if (match := POSITION_RE.search(line.split(";", 1)[0]))
        }
    with round_manifest.open(newline="", encoding="utf-8") as handle:
        rounds = list(csv.DictReader(handle))
    # A shared initial must not silently omit extra/missing acquisitions in another round.
    # Check this join once here using directory names, without reading image pixels.
    for row in rounds:
        observed = {
            f"Position{int(match.group(1)):03d}"
            for path in (raw_rounds_dir / row["rawdata_round"]).iterdir()
            if path.is_dir() and (match := POSITION_RE.fullmatch(path.name))
        }
        if observed != expected:
            raise ValueError(
                f"Shared initial FOV coverage differs for {row['rawdata_round']}: "
                f"missing={sorted(expected - observed)}, extra={sorted(observed - expected)}"
            )
    for row in rounds:
        if not row["subdir"]:
            continue
        for source in sources:
            target = method_root / row["subdir"] / source.name
            link_file(source, target)
            print(f"[LINK] {target} -> {os.readlink(target)}", flush=True)


def write_output(source, target, layout_mode, output_format):
    if layout_mode == "symlink":
        link_file(source, target)
        return

    if target.parent.is_symlink():
        raise FileExistsError(f"Channel output directory is a symlink: {target.parent}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        if output_format == "preserve":
            with source.open("rb") as source_handle:
                shutil.copyfileobj(source_handle, handle)
            return
        import tifffile

        image = tifffile.imread(source)
        image = convert_dtype(image, output_format)
        tifffile.imwrite(handle, image, photometric="minisblack")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw_round_dir", required=True, type=Path)
    parser.add_argument("--output_dir", required=True, type=Path)
    parser.add_argument("--channels", required=True)
    parser.add_argument("--manifest_path", required=True, type=Path)
    parser.add_argument("--layout_mode", choices=["symlink", "copy"], default="symlink")
    parser.add_argument("--output_format", choices=["preserve", "uint8", "uint16"], default="preserve")
    args = parser.parse_args()

    if args.layout_mode == "symlink" and args.output_format != "preserve":
        raise ValueError("A symlink layout requires output_format=preserve; use copy for conversion.")
    if args.output_dir.is_symlink():
        raise FileExistsError(f"Round output directory is a symlink: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = args.output_dir.resolve(strict=True)
    channels = parse_channels(args.channels)
    positions = [path for path in args.raw_round_dir.iterdir() if path.is_dir() and POSITION_RE.fullmatch(path.name)]
    positions.sort(key=lambda path: int(POSITION_RE.fullmatch(path.name).group(1)))
    if not positions:
        raise FileNotFoundError(f"No PositionXXX directories found in {args.raw_round_dir}")

    rows = []
    for position_dir in positions:
        position = f"Position{int(POSITION_RE.fullmatch(position_dir.name).group(1)):03d}"
        for token, channel in channels:
            source = find_channel_file(position_dir, token)
            target = output_dir / channel / f"{position}.tif"
            link_target = os.path.relpath(source, target.parent) if args.layout_mode == "symlink" else ""
            rows.append([position, token, channel, str(source), str(target), args.layout_mode, args.output_format, link_target])

    manifest = io.StringIO(newline="")
    writer = csv.writer(manifest)
    writer.writerow(["position", "raw_channel_token", "channel", "source", "target", "layout_mode", "output_format", "link_target"])
    writer.writerows(rows)
    manifest_text = manifest.getvalue()
    if args.manifest_path.exists() or args.manifest_path.is_symlink():
        if args.manifest_path.is_symlink():
            raise FileExistsError(f"Layout manifest is a symlink: {args.manifest_path}")
        with args.manifest_path.open(encoding="utf-8", newline="") as handle:
            if handle.read() != manifest_text:
                raise FileExistsError(f"Layout manifest already describes another layout: {args.manifest_path}")

    for row in rows:
        write_output(Path(row[3]), Path(row[4]), args.layout_mode, args.output_format)
    args.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.manifest_path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(manifest_text)
    except FileExistsError:
        with args.manifest_path.open(encoding="utf-8", newline="") as handle:
            if handle.read() != manifest_text:
                raise FileExistsError(f"Layout manifest changed concurrently: {args.manifest_path}")

    print(f"Prepared round layout: {output_dir}")
    print(f"Positions: {len(positions)}")
    print(f"Channels: {', '.join(channel for _, channel in channels)}")
    print(f"Layout mode: {args.layout_mode}")
    print(f"Output format: {args.output_format}")
    print(f"Manifest: {args.manifest_path}")


if __name__ == "__main__":
    main()
