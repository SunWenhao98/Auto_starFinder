"""Estimate one sensor-oriented flat-field profile per imaging round and channel."""

import argparse
import csv
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter
import tifffile


ROUND_ROLES = {"ref", "IF", "seqE"}
DEFAULT_SIGMA = 64.0


def _normalise_profile(image, source):
    if image.ndim != 2 or not np.isfinite(image).all() or np.any(image <= 0):
        raise ValueError(f"Expected a finite, positive YX flat-field profile: {source}")
    profile = (image / image.mean(dtype=np.float64)).astype(np.float32)
    if not np.isfinite(profile).all() or np.any(profile <= 0):
        raise ValueError(f"Flat-field profile cannot be represented as positive float32: {source}")
    return profile


def load_flat_field(path):
    """Read a YX TIFF profile and normalize its sensor gain to mean one."""
    return _normalise_profile(tifffile.imread(path), path)


def estimate_flat_field(paths, sigma=DEFAULT_SIGMA):
    """Average FOV MIPs, then smooth and normalize in the original sensor frame."""
    total = None
    count = 0
    for count, path in enumerate(paths, start=1):
        with tifffile.TiffFile(path) as tif:
            series = tif.series[0]
            if series.axes == "YX":
                mip = series.asarray()
            elif series.axes in {"ZYX", "QYX", "IYX"}:
                # Plain multi-page grayscale TIFF may label its page axis Q or I.
                mip = np.max(series.asarray(), axis=0)
            else:
                raise ValueError(f"Expected grayscale YX or ZYX TIFF at {path}, got {series.axes}")
        if total is None:
            total = mip.astype(np.float64)
        else:
            if mip.shape != total.shape:
                raise ValueError(f"TIFF shape {mip.shape} does not match {total.shape}: {path}")
            total += mip

    if count == 0:
        raise ValueError("Flat-field estimation requires at least one source TIFF")
    total /= count
    return _normalise_profile(gaussian_filter(total, sigma=sigma), "pooled FOV MIPs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input_manifest", required=True, type=Path,
        help="CSV columns round,channel,source_tiff. Relative TIFF paths resolve from the CSV directory.",
    )
    parser.add_argument("--output_dir", required=True, type=Path, help="New directory for profiles and profiles.csv.")
    parser.add_argument("--sigma", type=float, default=DEFAULT_SIGMA, help="Gaussian smoothing sigma in sensor pixels.")
    args = parser.parse_args()

    input_manifest = args.input_manifest.resolve(strict=True)
    groups = {}
    with input_manifest.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            role = row["round"].strip()
            channel = row["channel"].strip()
            if role not in ROUND_ROLES or Path(channel).name != channel or channel in {"", ".", ".."}:
                raise ValueError(f"Invalid flat-field round or channel: {role!r}, {channel!r}")
            path = (input_manifest.parent / row["source_tiff"].strip()).resolve(strict=True)
            paths = groups.setdefault((role, channel), {})
            if path in paths:
                raise ValueError(f"Repeated FOV for {role}/{channel}: {path}")
            paths[path] = None
    if not groups:
        raise ValueError(f"No source TIFFs listed in {input_manifest}")

    output_dir = args.output_dir.absolute()
    output_dir.mkdir(parents=True)
    output_dir = output_dir.resolve(strict=True)
    print(f"Source manifest: {input_manifest}")
    print(f"Output directory: {output_dir}")
    print(f"Gaussian sigma: {args.sigma:g} sensor pixels")

    profiles = []
    for (role, channel), paths in groups.items():
        profile_path = output_dir / role / f"{channel}.tif"
        print(f"Estimating {role}/{channel} from {len(paths)} FOV TIFFs")
        profile = estimate_flat_field(paths, sigma=args.sigma)
        profile_path.parent.mkdir(exist_ok=True)
        tifffile.imwrite(profile_path, profile, photometric="minisblack")
        profiles.append((role, channel, profile_path))
        print(f"Wrote {profile_path}, gain min={profile.min():.4g}, max={profile.max():.4g}")

    profile_manifest = output_dir / "profiles.csv"
    with profile_manifest.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("round", "channel", "profile_tif"))
        writer.writerows(profiles)
    print(f"Profile manifest: {profile_manifest}")


if __name__ == "__main__":
    main()
