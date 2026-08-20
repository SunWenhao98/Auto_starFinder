#!/usr/bin/env python3
"""Estimate a moving-to-reference 2D translation for stitched DAPI mosaics."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
from typing import Callable, Iterable, Sequence


SCHEMA_NAME = "starfinder_translation_registration"
SCHEMA_VERSION = "1.1"


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected boolean value, got {value!r}")


def compose_global_shift(
    local_shift_yx: Sequence[float],
    fixed_origin_yx: Sequence[int],
    moving_origin_yx: Sequence[int],
) -> tuple[float, float]:
    """Convert a local ROI shift to the full-image moving-to-reference shift."""
    shift_y = (
        float(local_shift_yx[0])
        + float(fixed_origin_yx[0])
        - float(moving_origin_yx[0])
    )
    shift_x = (
        float(local_shift_yx[1])
        + float(fixed_origin_yx[1])
        - float(moving_origin_yx[1])
    )
    return shift_y, shift_x


class TiffWindowReader:
    """Read two-dimensional TIFF windows without decoding the full mosaic."""

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self._tiff = None
        self._store = None
        self._array = None

    def __enter__(self) -> "TiffWindowReader":
        import tifffile
        import zarr

        self._tiff = tifffile.TiffFile(self.path)
        series = self._tiff.series[0]
        if len(series.shape) != 2:
            self._tiff.close()
            raise ValueError(
                f"Expected a 2D TIFF/OME-TIFF, got shape {series.shape} for {self.path}"
            )
        self._store = series.aszarr()
        self._array = zarr.open(self._store, mode="r")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._store is not None and hasattr(self._store, "close"):
            self._store.close()
        if self._tiff is not None:
            self._tiff.close()

    @property
    def shape(self) -> tuple[int, int]:
        if self._array is None:
            raise RuntimeError("TiffWindowReader must be opened with a context manager")
        return int(self._array.shape[0]), int(self._array.shape[1])

    @property
    def dtype(self):
        if self._array is None:
            raise RuntimeError("TiffWindowReader must be opened with a context manager")
        return self._array.dtype

    def read_window(self, y0: int, y1: int, x0: int, x1: int):
        import numpy as np

        if self._array is None:
            raise RuntimeError("TiffWindowReader must be opened with a context manager")
        return np.asarray(self._array[y0:y1, x0:x1])


def _downsample_block_mean(image, factor: int):
    import numpy as np

    if factor < 1:
        raise ValueError("overview_downsample must be at least 1")
    array = np.asarray(image)
    if array.ndim != 2:
        raise ValueError(f"Expected a 2D array, got shape {array.shape}")
    if factor == 1:
        return array.astype(np.float32, copy=True)
    height, width = array.shape
    out_height = math.ceil(height / factor)
    out_width = math.ceil(width / factor)
    padded_values = np.zeros(
        (out_height * factor, out_width * factor), dtype=np.float32
    )
    padded_valid = np.zeros_like(padded_values, dtype=np.float32)
    finite = np.isfinite(array)
    padded_values[:height, :width] = np.where(finite, array, 0).astype(np.float32)
    padded_valid[:height, :width] = finite.astype(np.float32)
    values = padded_values.reshape(out_height, factor, out_width, factor)
    valid = padded_valid.reshape(out_height, factor, out_width, factor)
    sums = values.sum(axis=(1, 3), dtype=np.float64)
    counts = valid.sum(axis=(1, 3), dtype=np.float64)
    return np.divide(
        sums,
        counts,
        out=np.zeros_like(sums, dtype=np.float32),
        where=counts > 0,
    )


def build_overview(
    reader: TiffWindowReader,
    downsample: int,
    block_px: int,
):
    import numpy as np

    if downsample < 1:
        raise ValueError("overview_downsample must be at least 1")
    if block_px < downsample:
        raise ValueError("overview_block_px must be at least overview_downsample")
    height, width = reader.shape
    overview = np.zeros(
        (math.ceil(height / downsample), math.ceil(width / downsample)),
        dtype=np.float32,
    )
    aligned_block = max(downsample, (block_px // downsample) * downsample)
    for y0 in range(0, height, aligned_block):
        y1 = min(height, y0 + aligned_block)
        oy0 = y0 // downsample
        for x0 in range(0, width, aligned_block):
            x1 = min(width, x0 + aligned_block)
            ox0 = x0 // downsample
            block = reader.read_window(y0, y1, x0, x1)
            reduced = _downsample_block_mean(block, downsample)
            overview[
                oy0 : oy0 + reduced.shape[0], ox0 : ox0 + reduced.shape[1]
            ] = reduced
    return overview


def _phase_correlation(
    fixed,
    moving,
    *,
    upsample_factor: int,
    fixed_mask=None,
    moving_mask=None,
    overlap_ratio: float = 0.3,
    apply_window: bool = False,
):
    import numpy as np
    from skimage.registration import phase_cross_correlation

    if apply_window:
        fixed = np.asarray(fixed, dtype=np.float32)
        moving = np.asarray(moving, dtype=np.float32)
        window = np.outer(np.hanning(fixed.shape[0]), np.hanning(fixed.shape[1]))
        fixed = (fixed - float(np.mean(fixed))) * window
        moving = (moving - float(np.mean(moving))) * window

    kwargs = {"upsample_factor": upsample_factor}
    if fixed_mask is not None or moving_mask is not None:
        kwargs.update(
            {
                "reference_mask": fixed_mask,
                "moving_mask": moving_mask,
                "overlap_ratio": overlap_ratio,
            }
        )
    shift, error, phase = phase_cross_correlation(fixed, moving, **kwargs)
    shift = np.asarray(shift, dtype=float)
    if shift.shape != (2,) or not np.all(np.isfinite(shift)):
        raise RuntimeError(f"Phase correlation returned invalid shift {shift}")
    safe_error = float(error) if math.isfinite(float(error)) else None
    safe_phase = float(phase) if math.isfinite(float(phase)) else None
    return (float(shift[0]), float(shift[1])), safe_error, safe_phase


def _overlap_bounds(
    fixed_shape: Sequence[int],
    moving_shape: Sequence[int],
    shift_yx: Sequence[float],
) -> tuple[int, int, int, int]:
    fixed_height, fixed_width = int(fixed_shape[0]), int(fixed_shape[1])
    moving_height, moving_width = int(moving_shape[0]), int(moving_shape[1])
    shift_y, shift_x = float(shift_yx[0]), float(shift_yx[1])
    y0 = max(0, math.ceil(shift_y))
    x0 = max(0, math.ceil(shift_x))
    y1 = min(fixed_height, math.floor(shift_y + moving_height))
    x1 = min(fixed_width, math.floor(shift_x + moving_width))
    return y0, y1, x0, x1


def _candidate_fixed_origins(
    bounds: Sequence[int], roi_size_px: int, candidate_count: int
) -> list[tuple[int, int]]:
    import numpy as np

    y0, y1, x0, x1 = (int(value) for value in bounds)
    if y1 - y0 < roi_size_px or x1 - x0 < roi_size_px:
        return []
    side = max(1, math.ceil(math.sqrt(candidate_count)))
    y_values = np.linspace(y0, y1 - roi_size_px, side)
    x_values = np.linspace(x0, x1 - roi_size_px, side)
    origins = {
        (int(round(y)), int(round(x))) for y in y_values for x in x_values
    }
    return sorted(origins)


def _valid_ratio(array) -> float:
    import numpy as np

    values = np.asarray(array)
    return float(np.count_nonzero(np.isfinite(values) & (values != 0)) / values.size)


def _select_roi_pairs(
    fixed_shape: Sequence[int],
    moving_shape: Sequence[int],
    coarse_shift_yx: Sequence[float],
    roi_size_px: int,
    roi_count: int,
    read_fixed: Callable[[int, int, int, int], object],
    read_moving: Callable[[int, int, int, int], object],
) -> list[dict]:
    import numpy as np

    bounds = _overlap_bounds(fixed_shape, moving_shape, coarse_shift_yx)
    candidate_origins = _candidate_fixed_origins(
        bounds, roi_size_px, max(roi_count * 4, 9)
    )
    ranked = []
    for fixed_y0, fixed_x0 in candidate_origins:
        moving_y0 = int(round(fixed_y0 - float(coarse_shift_yx[0])))
        moving_x0 = int(round(fixed_x0 - float(coarse_shift_yx[1])))
        if (
            moving_y0 < 0
            or moving_x0 < 0
            or moving_y0 + roi_size_px > int(moving_shape[0])
            or moving_x0 + roi_size_px > int(moving_shape[1])
        ):
            continue
        fixed_roi = read_fixed(
            fixed_y0,
            fixed_y0 + roi_size_px,
            fixed_x0,
            fixed_x0 + roi_size_px,
        )
        moving_roi = read_moving(
            moving_y0,
            moving_y0 + roi_size_px,
            moving_x0,
            moving_x0 + roi_size_px,
        )
        fixed_valid = _valid_ratio(fixed_roi)
        moving_valid = _valid_ratio(moving_roi)
        if min(fixed_valid, moving_valid) < 0.02:
            continue
        texture = float(np.std(fixed_roi, dtype=np.float64)) + float(
            np.std(moving_roi, dtype=np.float64)
        )
        if not math.isfinite(texture) or texture <= 0:
            continue
        ranked.append(
            {
                "fixed_origin_yx": (fixed_y0, fixed_x0),
                "moving_origin_yx": (moving_y0, moving_x0),
                "fixed_roi": np.asarray(fixed_roi, dtype=np.float32),
                "moving_roi": np.asarray(moving_roi, dtype=np.float32),
                "fixed_valid_ratio": fixed_valid,
                "moving_valid_ratio": moving_valid,
                "texture_score": texture,
            }
        )
    ranked.sort(key=lambda item: item["texture_score"], reverse=True)
    return ranked[:roi_count]


def robust_shift_consensus(
    shifts_yx: Iterable[Sequence[float]],
    min_valid_rois: int,
    max_spread_px: float,
) -> dict:
    import numpy as np

    shifts = np.asarray(list(shifts_yx), dtype=float)
    if shifts.ndim != 2 or shifts.shape[1:] != (2,):
        raise ValueError("Expected an N x 2 collection of y/x shifts")
    finite = np.all(np.isfinite(shifts), axis=1)
    shifts = shifts[finite]
    if shifts.shape[0] < min_valid_rois:
        raise RuntimeError(
            f"Only {shifts.shape[0]} finite ROI shifts; need {min_valid_rois}"
        )
    initial_median = np.median(shifts, axis=0)
    distances = np.linalg.norm(shifts - initial_median, axis=1)
    mad = float(np.median(np.abs(distances - np.median(distances))))
    threshold = max(0.25, 3.0 * 1.4826 * mad)
    inlier_mask = distances <= threshold
    if np.count_nonzero(inlier_mask) < min_valid_rois:
        closest = np.argsort(distances)[:min_valid_rois]
        inlier_mask = np.zeros(shifts.shape[0], dtype=bool)
        inlier_mask[closest] = True
    inlier_shifts = shifts[inlier_mask]
    consensus = np.median(inlier_shifts, axis=0)
    spread = float(np.max(np.linalg.norm(inlier_shifts - consensus, axis=1)))
    status = "PASS" if spread <= max_spread_px else "REJECTED"
    return {
        "shift_y_px": float(consensus[0]),
        "shift_x_px": float(consensus[1]),
        "inlier_mask": inlier_mask.tolist(),
        "n_valid": int(shifts.shape[0]),
        "n_inlier": int(np.count_nonzero(inlier_mask)),
        "mad_px": mad,
        "spread_px": spread,
        "status": status,
    }


def _coordinate_system() -> dict:
    return {
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


def _register_with_readers(
    fixed_shape: Sequence[int],
    moving_shape: Sequence[int],
    fixed_overview,
    moving_overview,
    read_fixed: Callable[[int, int, int, int], object],
    read_moving: Callable[[int, int, int, int], object],
    *,
    overview_downsample: int,
    roi_size_px: int,
    roi_count: int,
    min_valid_rois: int,
    upsample_factor: int,
    min_overlap_ratio: float,
    max_roi_spread_px: float,
) -> dict:
    import numpy as np

    fixed_mask = np.isfinite(fixed_overview) & (fixed_overview != 0)
    moving_mask = np.isfinite(moving_overview) & (moving_overview != 0)
    if not fixed_mask.any() or not moving_mask.any():
        raise RuntimeError("At least one overview contains no finite nonzero pixels")
    coarse_shift_overview, coarse_error, _ = _phase_correlation(
        fixed_overview,
        moving_overview,
        upsample_factor=1,
        fixed_mask=fixed_mask,
        moving_mask=moving_mask,
        overlap_ratio=min_overlap_ratio,
    )
    coarse_shift_yx = (
        coarse_shift_overview[0] * overview_downsample,
        coarse_shift_overview[1] * overview_downsample,
    )
    bounds = _overlap_bounds(fixed_shape, moving_shape, coarse_shift_yx)
    overlap_area = max(0, bounds[1] - bounds[0]) * max(0, bounds[3] - bounds[2])
    smaller_area = min(
        int(fixed_shape[0]) * int(fixed_shape[1]),
        int(moving_shape[0]) * int(moving_shape[1]),
    )
    overlap_fraction = overlap_area / smaller_area if smaller_area else 0.0
    if overlap_fraction < min_overlap_ratio:
        raise RuntimeError(
            f"Estimated overlap {overlap_fraction:.4f} is below {min_overlap_ratio:.4f}"
        )
    roi_pairs = _select_roi_pairs(
        fixed_shape,
        moving_shape,
        coarse_shift_yx,
        roi_size_px,
        roi_count,
        read_fixed,
        read_moving,
    )
    if len(roi_pairs) < min_valid_rois:
        raise RuntimeError(
            f"Only {len(roi_pairs)} usable ROI pairs; need {min_valid_rois}"
        )
    roi_results = []
    global_shifts = []
    for index, pair in enumerate(roi_pairs):
        local_shift, error, phase = _phase_correlation(
            pair["fixed_roi"],
            pair["moving_roi"],
            upsample_factor=upsample_factor,
            apply_window=True,
        )
        global_shift = compose_global_shift(
            local_shift,
            pair["fixed_origin_yx"],
            pair["moving_origin_yx"],
        )
        global_shifts.append(global_shift)
        roi_results.append(
            {
                "roi_index": index,
                "fixed_origin_yx": list(pair["fixed_origin_yx"]),
                "moving_origin_yx": list(pair["moving_origin_yx"]),
                "size_yx": [roi_size_px, roi_size_px],
                "local_shift_y_px": local_shift[0],
                "local_shift_x_px": local_shift[1],
                "global_shift_y_px": global_shift[0],
                "global_shift_x_px": global_shift[1],
                "registration_error": error,
                "phase_difference": phase,
                "fixed_valid_ratio": pair["fixed_valid_ratio"],
                "moving_valid_ratio": pair["moving_valid_ratio"],
                "texture_score": pair["texture_score"],
                "inlier": False,
            }
        )
    consensus = robust_shift_consensus(
        global_shifts,
        min_valid_rois=min_valid_rois,
        max_spread_px=max_roi_spread_px,
    )
    for roi, inlier in zip(roi_results, consensus["inlier_mask"], strict=True):
        roi["inlier"] = bool(inlier)
    return {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "transform_type": "translation_2d",
        "mapping": "moving_to_reference",
        "coordinate_system": _coordinate_system(),
        "transform": {
            "shift_x_px": consensus["shift_x_px"],
            "shift_y_px": consensus["shift_y_px"],
        },
        "quality": {
            "status": consensus["status"],
            "coarse_shift_x_px": float(coarse_shift_yx[1]),
            "coarse_shift_y_px": float(coarse_shift_yx[0]),
            "coarse_registration_error": coarse_error,
            "estimated_overlap_ratio": overlap_fraction,
            "n_rois_requested": roi_count,
            "n_rois_valid": consensus["n_valid"],
            "n_rois_inlier": consensus["n_inlier"],
            "roi_shift_mad_px": consensus["mad_px"],
            "roi_shift_spread_px": consensus["spread_px"],
        },
        "roi_results": roi_results,
    }


def register_arrays(
    fixed,
    moving,
    *,
    overview_downsample: int,
    roi_size_px: int,
    roi_count: int,
    min_valid_rois: int,
    upsample_factor: int,
    min_overlap_ratio: float,
    max_roi_spread_px: float,
) -> dict:
    import numpy as np

    fixed_array = np.asarray(fixed)
    moving_array = np.asarray(moving)
    if fixed_array.ndim != 2 or moving_array.ndim != 2:
        raise ValueError("fixed and moving must both be two-dimensional")
    result = _register_with_readers(
        fixed_array.shape,
        moving_array.shape,
        _downsample_block_mean(fixed_array, overview_downsample),
        _downsample_block_mean(moving_array, overview_downsample),
        lambda y0, y1, x0, x1: fixed_array[y0:y1, x0:x1],
        lambda y0, y1, x0, x1: moving_array[y0:y1, x0:x1],
        overview_downsample=overview_downsample,
        roi_size_px=roi_size_px,
        roi_count=roi_count,
        min_valid_rois=min_valid_rois,
        upsample_factor=upsample_factor,
        min_overlap_ratio=min_overlap_ratio,
        max_roi_spread_px=max_roi_spread_px,
    )
    result["reference"] = {
        "image": "<array>",
        "height_px": int(fixed_array.shape[0]),
        "width_px": int(fixed_array.shape[1]),
        "dtype": str(fixed_array.dtype),
    }
    result["moving"] = {
        "image": "<array>",
        "height_px": int(moving_array.shape[0]),
        "width_px": int(moving_array.shape[1]),
        "dtype": str(moving_array.dtype),
    }
    result["method"] = {
        "backend": "python",
        "algorithm": "coarse_to_fine_phase_correlation",
        "parameters": {
            "overview_downsample": overview_downsample,
            "roi_size_px": roi_size_px,
            "roi_count": roi_count,
            "min_valid_rois": min_valid_rois,
            "upsample_factor": upsample_factor,
            "min_overlap_ratio": min_overlap_ratio,
            "max_roi_spread_px": max_roi_spread_px,
        },
    }
    return result


def _file_identity(path: Path, shape: Sequence[int], dtype) -> dict:
    stat = path.stat()
    return {
        "image": str(path.resolve()),
        "height_px": int(shape[0]),
        "width_px": int(shape[1]),
        "dtype": str(dtype),
        "size_bytes": int(stat.st_size),
        "mtime_epoch_s": int(stat.st_mtime_ns // 1_000_000_000),
    }


def _assert_file_identity_unchanged(
    label: str, before: dict, after: dict
) -> None:
    if before != after:
        changed_fields = sorted(
            key for key in set(before) | set(after) if before.get(key) != after.get(key)
        )
        raise RuntimeError(
            f"{label} mosaic changed while registration was running: "
            + ", ".join(changed_fields)
        )


def register_paths(
    fixed_path: Path,
    moving_path: Path,
    *,
    overview_downsample: int,
    overview_block_px: int,
    roi_size_px: int,
    roi_count: int,
    min_valid_rois: int,
    upsample_factor: int,
    min_overlap_ratio: float,
    max_roi_spread_px: float,
) -> dict:
    import numpy as np
    import scipy
    import skimage
    import tifffile

    with TiffWindowReader(fixed_path) as fixed_reader, TiffWindowReader(
        moving_path
    ) as moving_reader:
        fixed_identity = _file_identity(
            fixed_path, fixed_reader.shape, fixed_reader.dtype
        )
        moving_identity = _file_identity(
            moving_path, moving_reader.shape, moving_reader.dtype
        )
        fixed_overview = build_overview(
            fixed_reader, overview_downsample, overview_block_px
        )
        moving_overview = build_overview(
            moving_reader, overview_downsample, overview_block_px
        )
        result = _register_with_readers(
            fixed_reader.shape,
            moving_reader.shape,
            fixed_overview,
            moving_overview,
            fixed_reader.read_window,
            moving_reader.read_window,
            overview_downsample=overview_downsample,
            roi_size_px=roi_size_px,
            roi_count=roi_count,
            min_valid_rois=min_valid_rois,
            upsample_factor=upsample_factor,
            min_overlap_ratio=min_overlap_ratio,
            max_roi_spread_px=max_roi_spread_px,
        )
        final_fixed_identity = _file_identity(
            fixed_path, fixed_reader.shape, fixed_reader.dtype
        )
        final_moving_identity = _file_identity(
            moving_path, moving_reader.shape, moving_reader.dtype
        )
        _assert_file_identity_unchanged(
            "Reference", fixed_identity, final_fixed_identity
        )
        _assert_file_identity_unchanged(
            "Moving", moving_identity, final_moving_identity
        )
        result["reference"] = fixed_identity
        result["moving"] = moving_identity
    result["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["method"] = {
        "backend": "python",
        "algorithm": "coarse_to_fine_phase_correlation",
        "backend_version": platform.python_version(),
        "library_versions": {
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "scikit_image": skimage.__version__,
            "tifffile": tifffile.__version__,
        },
        "parameters": {
            "overview_downsample": overview_downsample,
            "overview_block_px": overview_block_px,
            "roi_size_px": roi_size_px,
            "roi_count": roi_count,
            "min_valid_rois": min_valid_rois,
            "upsample_factor": upsample_factor,
            "min_overlap_ratio": min_overlap_ratio,
            "max_roi_spread_px": max_roi_spread_px,
        },
    }
    return result


def _ensure_outputs_available(paths: Iterable[Path], overwrite: bool) -> None:
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite existing output(s): {joined}")
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)


def write_result_files(
    result: dict,
    output_json: Path,
    output_csv: Path,
    output_roi_csv: Path,
    *,
    overwrite: bool,
) -> None:
    _ensure_outputs_available(
        (output_json, output_csv, output_roi_csv), overwrite=overwrite
    )
    output_json.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    summary = {
        "schema_name": result["schema_name"],
        "schema_version": result["schema_version"],
        "reference_image": result["reference"]["image"],
        "moving_image": result["moving"]["image"],
        "backend": result["method"]["backend"],
        "mapping": result["mapping"],
        "shift_x_px": result["transform"]["shift_x_px"],
        "shift_y_px": result["transform"]["shift_y_px"],
        "status": result["quality"]["status"],
        "n_rois_valid": result["quality"]["n_rois_valid"],
        "n_rois_inlier": result["quality"]["n_rois_inlier"],
        "roi_shift_spread_px": result["quality"]["roi_shift_spread_px"],
    }
    with output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary))
        writer.writeheader()
        writer.writerow(summary)
    roi_fields = list(result["roi_results"][0]) if result["roi_results"] else []
    with output_roi_csv.open("w", newline="") as handle:
        if roi_fields:
            writer = csv.DictWriter(handle, fieldnames=roi_fields)
            writer.writeheader()
            writer.writerows(result["roi_results"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixed_mosaic", type=Path, required=True)
    parser.add_argument("--moving_mosaic", type=Path, required=True)
    parser.add_argument("--output_json", type=Path, required=True)
    parser.add_argument("--output_csv", type=Path, required=True)
    parser.add_argument("--output_roi_csv", type=Path, required=True)
    parser.add_argument("--overview_downsample", type=int, default=16)
    parser.add_argument("--overview_block_px", type=int, default=4096)
    parser.add_argument("--roi_size_px", type=int, default=1024)
    parser.add_argument("--roi_count", type=int, default=9)
    parser.add_argument("--min_valid_rois", type=int, default=4)
    parser.add_argument("--upsample_factor", type=int, default=20)
    parser.add_argument("--min_overlap_ratio", type=float, default=0.2)
    parser.add_argument("--max_roi_spread_px", type=float, default=1.0)
    parser.add_argument("--overwrite", type=parse_bool, default=False)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = register_paths(
        args.fixed_mosaic.resolve(),
        args.moving_mosaic.resolve(),
        overview_downsample=args.overview_downsample,
        overview_block_px=args.overview_block_px,
        roi_size_px=args.roi_size_px,
        roi_count=args.roi_count,
        min_valid_rois=args.min_valid_rois,
        upsample_factor=args.upsample_factor,
        min_overlap_ratio=args.min_overlap_ratio,
        max_roi_spread_px=args.max_roi_spread_px,
    )
    if result["quality"]["status"] != "PASS":
        raise RuntimeError(
            "Registration was rejected: "
            f"ROI spread={result['quality']['roi_shift_spread_px']:.4f}px"
        )
    write_result_files(
        result,
        args.output_json,
        args.output_csv,
        args.output_roi_csv,
        overwrite=args.overwrite,
    )
    print(
        "Registration PASS: "
        f"shift_x_px={result['transform']['shift_x_px']:.4f}, "
        f"shift_y_px={result['transform']['shift_y_px']:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
