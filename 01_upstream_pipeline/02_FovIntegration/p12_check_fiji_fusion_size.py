#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys


DEFAULT_MAX_PIXELS = 2_147_483_647
COORDINATE_PATTERN = re.compile(
    r"\(\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*,\s*"
    r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*,"
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether a TileConfiguration fits one ImageJ XY plane."
    )
    parser.add_argument("--config_file", type=Path, required=True)
    parser.add_argument("--image_xy", type=int, required=True)
    parser.add_argument("--report_file", type=Path, required=True)
    parser.add_argument("--max_pixels", type=int, default=DEFAULT_MAX_PIXELS)
    return parser.parse_args()


def read_coordinates(config_file: Path) -> list[tuple[float, float]]:
    coordinates = []
    for line in config_file.read_text().splitlines():
        match = COORDINATE_PATTERN.search(line)
        if match:
            coordinates.append((float(match.group(1)), float(match.group(2))))
    if not coordinates:
        raise ValueError(f"No tile coordinates found in {config_file}")
    return coordinates


def build_report(
    coordinates: list[tuple[float, float]], image_xy: int, max_pixels: int
) -> dict[str, int | float | bool | str]:
    if image_xy <= 0:
        raise ValueError("--image_xy must be greater than zero")
    if max_pixels <= 0:
        raise ValueError("--max_pixels must be greater than zero")

    x_values = [coordinate[0] for coordinate in coordinates]
    y_values = [coordinate[1] for coordinate in coordinates]
    mosaic_width = math.ceil(max(x_values) + image_xy - min(x_values))
    mosaic_height = math.ceil(max(y_values) + image_xy - min(y_values))
    pixel_count = mosaic_width * mosaic_height
    fiji_fusion_safe = pixel_count < max_pixels

    return {
        "mosaic_width": mosaic_width,
        "mosaic_height": mosaic_height,
        "pixel_count": pixel_count,
        "imagej_int32_limit": max_pixels,
        "limit_utilization": pixel_count / max_pixels,
        "fiji_fusion_safe": fiji_fusion_safe,
        "recommendation": (
            "Fiji fusion is allowed" if fiji_fusion_safe else "Use Ashlar stitching"
        ),
    }


def main() -> int:
    args = parse_arguments()
    try:
        coordinates = read_coordinates(args.config_file)
        report = build_report(coordinates, args.image_xy, args.max_pixels)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    args.report_file.write_text(json.dumps(report, indent=2) + "\n")
    status = "SAFE" if report["fiji_fusion_safe"] else "UNSAFE"
    print(f"FIJI_FUSION_PREFLIGHT: {status}")
    print(f"MOSAIC_WIDTH: {report['mosaic_width']}")
    print(f"MOSAIC_HEIGHT: {report['mosaic_height']}")
    print(f"PIXEL_COUNT: {report['pixel_count']}")
    print(f"IMAGEJ_INT32_LIMIT: {report['imagej_int32_limit']}")
    print(f"RECOMMENDATION: {report['recommendation']}")
    print(f"REPORT_FILE: {args.report_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
