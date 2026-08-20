#!/usr/bin/env python3
"""Compare independent Python and Matlab mosaic translation results."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path


SCHEMA_NAME = "starfinder_translation_registration"
SCHEMA_VERSION = "1.1"
IDENTITY_FIELDS = (
    "image",
    "height_px",
    "width_px",
    "dtype",
    "size_bytes",
    "mtime_epoch_s",
)
EXPECTED_COORDINATE_SYSTEM = {
    "axis_order": "xy",
    "units": "pixel",
    "pixel_origin": "zero_based",
    "x_axis": "image_column_increasing_right",
    "y_axis": "image_row_increasing_down",
    "formula": {
        "x_ref": "x_moving + shift_x_px",
        "y_ref": "y_moving + shift_y_px",
    },
}


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected boolean value, got {value!r}")


def _validate_image_identity(label: str, identity: dict) -> tuple:
    missing = [field for field in IDENTITY_FIELDS if field not in identity]
    if missing:
        raise ValueError(f"{label} identity is missing: {', '.join(missing)}")
    image = identity["image"]
    if not isinstance(image, str) or not image or not Path(image).is_absolute():
        raise ValueError(f"{label} image must be a canonical absolute path")
    if not isinstance(identity["dtype"], str) or not identity["dtype"]:
        raise ValueError(f"{label} dtype must be a non-empty string")
    for field in ("height_px", "width_px"):
        value = identity[field]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{label} {field} must be a positive integer")
    for field in ("size_bytes", "mtime_epoch_s"):
        value = identity[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} {field} must be a non-negative integer")
    return tuple(identity[field] for field in IDENTITY_FIELDS)


def _validated_identity(result: dict, expected_backend: str) -> tuple:
    if result.get("schema_name") != SCHEMA_NAME:
        raise ValueError("Unexpected schema_name")
    if result.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unexpected schema_version")
    if result.get("transform_type") != "translation_2d":
        raise ValueError("Unexpected transform_type")
    if result.get("mapping") != "moving_to_reference":
        raise ValueError("Unexpected transform mapping")
    if result.get("coordinate_system") != EXPECTED_COORDINATE_SYSTEM:
        raise ValueError("Unexpected coordinate_system contract")
    if result.get("method", {}).get("backend") != expected_backend:
        raise ValueError(f"Expected backend {expected_backend}")
    if result.get("quality", {}).get("status") != "PASS":
        raise ValueError("Both backend transforms must have quality status PASS")
    shift_x = float(result.get("transform", {}).get("shift_x_px", math.nan))
    shift_y = float(result.get("transform", {}).get("shift_y_px", math.nan))
    if not math.isfinite(shift_x) or not math.isfinite(shift_y):
        raise ValueError("Backend transform contains a non-finite shift")
    identity = (
        _validate_image_identity("reference", result.get("reference", {})),
        _validate_image_identity("moving", result.get("moving", {})),
    )
    return identity, shift_x, shift_y


def compare_transforms(
    python_result: dict,
    matlab_result: dict,
    *,
    agreement_tolerance_px: float,
) -> dict:
    python_identity, python_shift_x, python_shift_y = _validated_identity(
        python_result, "python"
    )
    matlab_identity, matlab_shift_x, matlab_shift_y = _validated_identity(
        matlab_result, "matlab"
    )
    if python_identity != matlab_identity:
        raise ValueError("Python and Matlab transforms refer to different inputs")
    delta_x = matlab_shift_x - python_shift_x
    delta_y = matlab_shift_y - python_shift_y
    euclidean = math.hypot(delta_x, delta_y)
    agreement = "PASS" if euclidean <= agreement_tolerance_px else "REVIEW_REQUIRED"
    return {
        "schema_name": "starfinder_translation_registration_comparison",
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reference_image": python_identity[0][0],
        "moving_image": python_identity[1][0],
        "mapping": "moving_to_reference",
        "python": {
            "shift_x_px": python_shift_x,
            "shift_y_px": python_shift_y,
        },
        "matlab": {
            "shift_x_px": matlab_shift_x,
            "shift_y_px": matlab_shift_y,
        },
        "delta_shift_x_px": delta_x,
        "delta_shift_y_px": delta_y,
        "euclidean_delta_px": euclidean,
        "agreement_tolerance_px": agreement_tolerance_px,
        "agreement_status": agreement,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python_json", type=Path, required=True)
    parser.add_argument("--matlab_json", type=Path, required=True)
    parser.add_argument("--output_json", type=Path, required=True)
    parser.add_argument("--output_csv", type=Path, required=True)
    parser.add_argument("--agreement_tolerance_px", type=float, default=0.5)
    parser.add_argument("--fail_on_disagreement", type=parse_bool, default=True)
    parser.add_argument("--overwrite", type=parse_bool, default=False)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    outputs = (args.output_json, args.output_csv)
    existing = [path for path in outputs if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            "Refusing to overwrite existing output(s): "
            + ", ".join(str(path) for path in existing)
        )
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    result = compare_transforms(
        json.loads(args.python_json.read_text()),
        json.loads(args.matlab_json.read_text()),
        agreement_tolerance_px=args.agreement_tolerance_px,
    )
    args.output_json.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    flat = {
        key: value
        for key, value in result.items()
        if not isinstance(value, (dict, list))
    }
    flat.update(
        {
            "python_shift_x_px": result["python"]["shift_x_px"],
            "python_shift_y_px": result["python"]["shift_y_px"],
            "matlab_shift_x_px": result["matlab"]["shift_x_px"],
            "matlab_shift_y_px": result["matlab"]["shift_y_px"],
        }
    )
    with args.output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat))
        writer.writeheader()
        writer.writerow(flat)
    print(f"Comparison status: {result['agreement_status']}")
    if result["agreement_status"] != "PASS" and args.fail_on_disagreement:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
