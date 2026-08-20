#!/usr/bin/env python3
"""Apply a validated mosaic translation and write registered image/QC outputs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import stat
import tempfile
from typing import Iterable, Sequence

from p25_register_mosaic_python import (
    SCHEMA_NAME,
    SCHEMA_VERSION,
    TiffWindowReader,
    build_overview,
    parse_bool,
)


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


def validate_transform_contract(
    transform: dict,
    fixed_path: Path,
    moving_path: Path,
    fixed_shape: Sequence[int],
    moving_shape: Sequence[int],
) -> tuple[float, float]:
    if transform.get("schema_name") != SCHEMA_NAME:
        raise ValueError("Unexpected transform schema_name")
    if transform.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unexpected transform schema_version")
    if transform.get("transform_type") != "translation_2d":
        raise ValueError("Only translation_2d transforms can be applied")
    if transform.get("mapping") != "moving_to_reference":
        raise ValueError("Transform mapping must be moving_to_reference")
    if transform.get("coordinate_system") != EXPECTED_COORDINATE_SYSTEM:
        raise ValueError("Unexpected transform coordinate_system contract")
    if transform.get("method", {}).get("backend") not in {"python", "matlab"}:
        raise ValueError("Transform backend must be python or matlab")
    if transform.get("quality", {}).get("status") != "PASS":
        raise ValueError("Refusing to apply a transform whose quality status is not PASS")
    reference = transform.get("reference", {})
    moving = transform.get("moving", {})
    if Path(reference.get("image", "")).resolve() != fixed_path.resolve():
        raise ValueError("Transform reference image does not match --fixed_mosaic")
    if Path(moving.get("image", "")).resolve() != moving_path.resolve():
        raise ValueError("Transform moving image does not match --moving_mosaic")
    if [reference.get("height_px"), reference.get("width_px")] != list(fixed_shape):
        raise ValueError("Transform reference shape does not match the fixed mosaic")
    if [moving.get("height_px"), moving.get("width_px")] != list(moving_shape):
        raise ValueError("Transform moving shape does not match the moving mosaic")
    _validate_file_identity("reference", reference, fixed_path, fixed_shape)
    _validate_file_identity("moving", moving, moving_path, moving_shape)
    shift_x = float(transform.get("transform", {}).get("shift_x_px", math.nan))
    shift_y = float(transform.get("transform", {}).get("shift_y_px", math.nan))
    if not math.isfinite(shift_x) or not math.isfinite(shift_y):
        raise ValueError("Transform shift values must be finite")
    return shift_y, shift_x


def _validate_file_identity(
    label: str, identity: dict, path: Path, shape: Sequence[int]
) -> None:
    import tifffile

    missing = [field for field in IDENTITY_FIELDS if field not in identity]
    if missing:
        raise ValueError(f"Transform {label} identity is missing {', '.join(missing)}")
    if identity["image"] != str(path.resolve()):
        raise ValueError(f"Transform {label} image is not the canonical input path")
    if [identity["height_px"], identity["width_px"]] != [
        int(shape[0]),
        int(shape[1]),
    ]:
        raise ValueError(f"Transform {label} shape does not match the input file")
    with tifffile.TiffFile(path) as tif:
        dtype = str(tif.series[0].dtype)
    if not isinstance(identity["dtype"], str) or identity["dtype"] != dtype:
        raise ValueError(f"Transform {label} dtype does not match the input file")
    stat = path.stat()
    if isinstance(identity["size_bytes"], bool) or not isinstance(
        identity["size_bytes"], int
    ):
        raise ValueError(f"Transform {label} size_bytes must be an integer")
    if int(identity["size_bytes"]) != stat.st_size:
        raise ValueError(f"Transform {label} size_bytes does not match the input file")
    if isinstance(identity["mtime_epoch_s"], bool) or not isinstance(
        identity["mtime_epoch_s"], int
    ):
        raise ValueError(f"Transform {label} mtime_epoch_s must be an integer")
    actual_mtime_epoch_s = stat.st_mtime_ns // 1_000_000_000
    if int(identity["mtime_epoch_s"]) != actual_mtime_epoch_s:
        raise ValueError(
            f"Transform {label} mtime_epoch_s does not match the input file"
        )


def apply_translation_array(
    moving,
    output_shape: Sequence[int],
    shift_yx: Sequence[float],
    interpolation_order: int,
):
    import numpy as np
    from scipy import ndimage

    if interpolation_order not in {0, 1}:
        raise ValueError("interpolation_order must be 0 or 1")
    moving_array = np.asarray(moving)
    output_height, output_width = int(output_shape[0]), int(output_shape[1])
    y_coordinates = np.arange(output_height, dtype=np.float64) - float(shift_yx[0])
    x_coordinates = np.arange(output_width, dtype=np.float64) - float(shift_yx[1])
    yy, xx = np.meshgrid(y_coordinates, x_coordinates, indexing="ij")
    sampled = ndimage.map_coordinates(
        moving_array,
        [yy, xx],
        order=interpolation_order,
        mode="constant",
        cval=0.0,
        prefilter=interpolation_order > 1,
    )
    return _cast_to_dtype(sampled, moving_array.dtype)


def _cast_to_dtype(values, dtype):
    import numpy as np

    target = np.dtype(dtype)
    if np.issubdtype(target, np.integer):
        limits = np.iinfo(target)
        return np.clip(np.rint(values), limits.min, limits.max).astype(target)
    return np.asarray(values, dtype=target)


def _sample_output_tile(
    reader: TiffWindowReader,
    y0: int,
    y1: int,
    x0: int,
    x1: int,
    shift_yx: Sequence[float],
    interpolation_order: int,
):
    import numpy as np
    from scipy import ndimage

    if interpolation_order not in {0, 1}:
        raise ValueError("interpolation_order must be 0 or 1")
    shift_y, shift_x = float(shift_yx[0]), float(shift_yx[1])
    moving_height, moving_width = reader.shape
    halo = max(1, interpolation_order + 1)
    requested_y0 = math.floor(y0 - shift_y) - halo
    requested_y1 = math.ceil((y1 - 1) - shift_y) + halo + 1
    requested_x0 = math.floor(x0 - shift_x) - halo
    requested_x1 = math.ceil((x1 - 1) - shift_x) + halo + 1
    read_y0 = max(0, requested_y0)
    read_y1 = min(moving_height, requested_y1)
    read_x0 = max(0, requested_x0)
    read_x1 = min(moving_width, requested_x1)
    if read_y0 >= read_y1 or read_x0 >= read_x1:
        return np.zeros((y1 - y0, x1 - x0), dtype=reader.dtype)
    block = reader.read_window(read_y0, read_y1, read_x0, read_x1)
    y_coordinates = np.arange(y0, y1, dtype=np.float64) - shift_y - read_y0
    x_coordinates = np.arange(x0, x1, dtype=np.float64) - shift_x - read_x0
    yy, xx = np.meshgrid(y_coordinates, x_coordinates, indexing="ij")
    sampled = ndimage.map_coordinates(
        block,
        [yy, xx],
        order=interpolation_order,
        mode="constant",
        cval=0.0,
        prefilter=interpolation_order > 1,
    )
    return _cast_to_dtype(sampled, reader.dtype)


def _tile_iterator(
    moving_path: Path,
    output_shape: Sequence[int],
    shift_yx: Sequence[float],
    tile_size_px: int,
    interpolation_order: int,
):
    output_height, output_width = int(output_shape[0]), int(output_shape[1])
    with TiffWindowReader(moving_path) as reader:
        for y0 in range(0, output_height, tile_size_px):
            y1 = min(output_height, y0 + tile_size_px)
            for x0 in range(0, output_width, tile_size_px):
                x1 = min(output_width, x0 + tile_size_px)
                yield _sample_output_tile(
                    reader,
                    y0,
                    y1,
                    x0,
                    x1,
                    shift_yx,
                    interpolation_order,
                )


def _canonical_path(path: Path) -> Path:
    return Path(os.path.realpath(os.path.abspath(path)))


def _ensure_outputs_available(
    paths: Iterable[Path],
    overwrite: bool,
    protected_paths: Iterable[Path] = (),
) -> None:
    output_paths = tuple(Path(path) for path in paths)
    protected = tuple(Path(path) for path in protected_paths)
    canonical_outputs = [_canonical_path(path) for path in output_paths]
    if len(set(canonical_outputs)) != len(canonical_outputs):
        raise ValueError("Output paths contain duplicate canonical destinations")
    canonical_protected = {_canonical_path(path) for path in protected}
    aliases = [
        path
        for path, canonical in zip(output_paths, canonical_outputs, strict=True)
        if canonical in canonical_protected
    ]
    if aliases:
        raise ValueError(
            "Output path aliases an input: " + ", ".join(str(path) for path in aliases)
        )
    for path in output_paths:
        if path.is_symlink():
            raise ValueError(f"Output path must not be a symlink: {path}")
        if os.path.lexists(path):
            mode = os.lstat(path).st_mode
            if not stat.S_ISREG(mode):
                raise ValueError(f"Output path is not a regular file: {path}")
            if any(
                protected_path.exists() and os.path.samefile(path, protected_path)
                for protected_path in protected
            ):
                raise ValueError(f"Output path is a hard-link alias of an input: {path}")
    existing = [path for path in output_paths if os.path.lexists(path)]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite existing output(s): {joined}")
    for path in output_paths:
        path.parent.mkdir(parents=True, exist_ok=True)


def _unique_temp_path(output_path: Path) -> Path:
    suffix = "".join(output_path.suffixes) or ".tmp"
    descriptor, name = tempfile.mkstemp(
        prefix=f".{output_path.stem}.",
        suffix=suffix,
        dir=output_path.parent,
    )
    os.close(descriptor)
    return Path(name)


def publish_temp_file(
    temporary_path: Path, output_path: Path, *, overwrite: bool
) -> None:
    if temporary_path.is_symlink() or not temporary_path.is_file():
        raise ValueError(f"Temporary output is not a regular file: {temporary_path}")
    if output_path.is_symlink():
        raise ValueError(f"Output path must not be a symlink: {output_path}")
    if overwrite:
        os.replace(temporary_path, output_path)
        return
    os.link(temporary_path, output_path)
    temporary_path.unlink()


def write_registered_mosaic(
    moving_path: Path,
    output_path: Path,
    output_shape: Sequence[int],
    shift_yx: Sequence[float],
    dtype,
    tile_size_px: int,
    interpolation_order: int,
    compression: str,
) -> Path:
    import tifffile

    temporary_path = _unique_temp_path(output_path)
    try:
        tifffile.imwrite(
            temporary_path,
            data=_tile_iterator(
                moving_path,
                output_shape,
                shift_yx,
                tile_size_px,
                interpolation_order,
            ),
            shape=(int(output_shape[0]), int(output_shape[1])),
            dtype=dtype,
            tile=(tile_size_px, tile_size_px),
            compression=compression,
            bigtiff=True,
            ome=True,
            photometric="minisblack",
            metadata={"axes": "YX"},
        )
        return temporary_path
    except Exception:
        if os.path.lexists(temporary_path):
            temporary_path.unlink()
        raise


def _normalize_for_display(image):
    import numpy as np

    values = np.asarray(image, dtype=np.float32)
    finite = values[np.isfinite(values)]
    positive = finite[finite > 0]
    if positive.size == 0:
        return np.zeros_like(values, dtype=np.float32)
    low, high = np.percentile(positive, [1.0, 99.8])
    if not math.isfinite(float(high)) or high <= low:
        high = float(positive.max())
        low = float(positive.min())
    if high <= low:
        return np.zeros_like(values, dtype=np.float32)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def _write_qc_outputs(
    fixed_path: Path,
    moving_path: Path,
    transform: dict,
    shift_yx: Sequence[float],
    preview_downsample: int,
    overview_block_px: int,
    output_preview_tif: Path,
    output_qc_png: Path,
    output_qc_pdf: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import tifffile

    with TiffWindowReader(fixed_path) as fixed_reader, TiffWindowReader(
        moving_path
    ) as moving_reader:
        fixed_preview = build_overview(
            fixed_reader, preview_downsample, overview_block_px
        )
        moving_preview = build_overview(
            moving_reader, preview_downsample, overview_block_px
        )
    scaled_shift = (
        float(shift_yx[0]) / preview_downsample,
        float(shift_yx[1]) / preview_downsample,
    )
    registered_preview = apply_translation_array(
        moving_preview,
        fixed_preview.shape,
        scaled_shift,
        interpolation_order=1,
    )
    moving_before = np.zeros_like(fixed_preview)
    copy_height = min(fixed_preview.shape[0], moving_preview.shape[0])
    copy_width = min(fixed_preview.shape[1], moving_preview.shape[1])
    moving_before[:copy_height, :copy_width] = moving_preview[
        :copy_height, :copy_width
    ]
    tifffile.imwrite(
        output_preview_tif,
        registered_preview.astype(np.float32),
        bigtiff=False,
        metadata={"axes": "YX"},
    )
    fixed_display = _normalize_for_display(fixed_preview)
    moving_display = _normalize_for_display(moving_before)
    registered_display = _normalize_for_display(registered_preview)
    overlay = np.zeros((*fixed_preview.shape, 3), dtype=np.float32)
    overlay[..., 0] = fixed_display
    overlay[..., 2] = fixed_display
    overlay[..., 1] = registered_display
    difference = np.abs(fixed_display - registered_display)
    fig, axes = plt.subplots(1, 5, figsize=(18, 4), constrained_layout=True)
    panels = (
        (fixed_display, "Fixed/reference", "gray"),
        (moving_display, "Moving before", "gray"),
        (registered_display, "Registered moving", "gray"),
        (overlay, "Overlay: fixed magenta / moving green", None),
        (difference, "Absolute difference", "magma"),
    )
    for ax, (panel, title, cmap) in zip(axes, panels, strict=True):
        ax.imshow(panel, cmap=cmap, interpolation="nearest")
        ax.set_title(title, fontsize=9)
        ax.set_axis_off()
    method = transform.get("method", {})
    quality = transform.get("quality", {})
    fig.suptitle(
        f"{method.get('backend', 'unknown')} | "
        f"shift_x={float(shift_yx[1]):.3f}px, "
        f"shift_y={float(shift_yx[0]):.3f}px | "
        f"inlier ROI={quality.get('n_rois_inlier', 'N/A')} | "
        f"spread={quality.get('roi_shift_spread_px', 'N/A')}px",
        fontsize=10,
    )
    fig.savefig(output_qc_png, dpi=300, bbox_inches="tight")
    fig.savefig(output_qc_pdf, bbox_inches="tight")
    plt.close(fig)


def _valid_output_bbox(
    fixed_shape: Sequence[int], moving_shape: Sequence[int], shift_yx: Sequence[float]
) -> dict:
    y0 = max(0, math.ceil(float(shift_yx[0])))
    x0 = max(0, math.ceil(float(shift_yx[1])))
    y1 = min(
        int(fixed_shape[0]), math.ceil(float(shift_yx[0]) + int(moving_shape[0]))
    )
    x1 = min(
        int(fixed_shape[1]), math.ceil(float(shift_yx[1]) + int(moving_shape[1]))
    )
    return {"y0": y0, "y1": max(y0, y1), "x0": x0, "x1": max(x0, x1)}


def _clipped_source_bounds(
    fixed_shape: Sequence[int], moving_shape: Sequence[int], shift_yx: Sequence[float]
) -> dict:
    shift_y, shift_x = float(shift_yx[0]), float(shift_yx[1])
    y0 = max(0.0, -shift_y)
    x0 = max(0.0, -shift_x)
    y1 = min(float(moving_shape[0]), float(fixed_shape[0]) - shift_y)
    x1 = min(float(moving_shape[1]), float(fixed_shape[1]) - shift_x)
    return {
        "y0": y0,
        "y1": max(y0, y1),
        "x0": x0,
        "x1": max(x0, x1),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transform_json", type=Path, required=True)
    parser.add_argument("--fixed_mosaic", type=Path, required=True)
    parser.add_argument("--moving_mosaic", type=Path, required=True)
    parser.add_argument("--output_registered_mosaic", type=Path, required=True)
    parser.add_argument("--output_application_json", type=Path, required=True)
    parser.add_argument("--output_preview_tif", type=Path, required=True)
    parser.add_argument("--output_qc_png", type=Path, required=True)
    parser.add_argument("--output_qc_pdf", type=Path, required=True)
    parser.add_argument("--tile_size_px", type=int, default=1024)
    parser.add_argument("--interpolation_order", type=int, choices=(0, 1), default=1)
    parser.add_argument("--preview_downsample", type=int, default=16)
    parser.add_argument("--overview_block_px", type=int, default=4096)
    parser.add_argument("--compression", default="zlib")
    parser.add_argument("--overwrite", type=parse_bool, default=False)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.tile_size_px < 16 or args.tile_size_px % 16 != 0:
        raise ValueError("tile_size_px must be a multiple of 16 and at least 16")
    if args.preview_downsample < 1:
        raise ValueError("preview_downsample must be at least 1")
    outputs = (
        args.output_registered_mosaic,
        args.output_application_json,
        args.output_preview_tif,
        args.output_qc_png,
        args.output_qc_pdf,
    )
    fixed_path = args.fixed_mosaic.resolve()
    moving_path = args.moving_mosaic.resolve()
    transform_path = args.transform_json.resolve()
    _ensure_outputs_available(
        outputs,
        overwrite=args.overwrite,
        protected_paths=(fixed_path, moving_path, transform_path),
    )
    transform = json.loads(transform_path.read_text())
    with TiffWindowReader(fixed_path) as fixed_reader, TiffWindowReader(
        moving_path
    ) as moving_reader:
        fixed_shape = fixed_reader.shape
        moving_shape = moving_reader.shape
        moving_dtype = moving_reader.dtype
    shift_yx = validate_transform_contract(
        transform,
        fixed_path,
        moving_path,
        fixed_shape,
        moving_shape,
    )
    metadata = {
        "schema_name": "starfinder_translation_application",
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mapping": "moving_to_reference",
        "transform_json": str(transform_path),
        "reference_image": str(fixed_path),
        "moving_image": str(moving_path),
        "transform": {
            "shift_x_px": float(shift_yx[1]),
            "shift_y_px": float(shift_yx[0]),
        },
        "resampling": {
            "interpolation_order": args.interpolation_order,
            "tile_size_px": args.tile_size_px,
            "outside_value": 0,
            "compression": args.compression,
        },
        "output": {
            "registered_mosaic": str(args.output_registered_mosaic.resolve()),
            "registered_preview_tif": str(args.output_preview_tif.resolve()),
            "qc_png": str(args.output_qc_png.resolve()),
            "qc_pdf": str(args.output_qc_pdf.resolve()),
            "shape_yx": [int(fixed_shape[0]), int(fixed_shape[1])],
            "dtype": str(moving_dtype),
            "valid_output_bbox_yx": _valid_output_bbox(
                fixed_shape, moving_shape, shift_yx
            ),
            "clipped_source_bounds_yx_px": _clipped_source_bounds(
                fixed_shape, moving_shape, shift_yx
            ),
            "canvas_padding": "constant_zero",
        },
    }
    temporary_outputs: dict[Path, Path] = {}
    try:
        temporary_outputs[args.output_registered_mosaic] = write_registered_mosaic(
            moving_path,
            args.output_registered_mosaic,
            fixed_shape,
            shift_yx,
            moving_dtype,
            args.tile_size_px,
            args.interpolation_order,
            args.compression,
        )
        temporary_outputs[args.output_preview_tif] = _unique_temp_path(
            args.output_preview_tif
        )
        temporary_outputs[args.output_qc_png] = _unique_temp_path(args.output_qc_png)
        temporary_outputs[args.output_qc_pdf] = _unique_temp_path(args.output_qc_pdf)
        _write_qc_outputs(
            fixed_path,
            moving_path,
            transform,
            shift_yx,
            args.preview_downsample,
            args.overview_block_px,
            temporary_outputs[args.output_preview_tif],
            temporary_outputs[args.output_qc_png],
            temporary_outputs[args.output_qc_pdf],
        )
        temporary_outputs[args.output_application_json] = _unique_temp_path(
            args.output_application_json
        )
        temporary_outputs[args.output_application_json].write_text(
            json.dumps(metadata, indent=2, allow_nan=False) + "\n"
        )
        validate_transform_contract(
            transform,
            fixed_path,
            moving_path,
            fixed_shape,
            moving_shape,
        )
        for output_path in outputs:
            publish_temp_file(
                temporary_outputs[output_path],
                output_path,
                overwrite=args.overwrite,
            )
    except Exception:
        for temporary_path in temporary_outputs.values():
            if os.path.lexists(temporary_path):
                temporary_path.unlink()
        raise
    print(
        "Transform application PASS: "
        f"registered_mosaic={args.output_registered_mosaic}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
