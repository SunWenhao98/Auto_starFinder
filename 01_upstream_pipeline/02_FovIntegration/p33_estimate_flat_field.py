#!/usr/bin/env python3
"""Estimate a flat-field (illumination) profile per channel, pooled over the FOVs of many samples.

Every FOV is reduced to its MIP; the profile is the mean over all FOVs of all given
samples, Gaussian-smoothed and scaled to mean 1, in raw sensor orientation. Pooling
many samples averages out tissue content, so the profile is less noisy than one
estimated from a single sample (which is what 32 does with --flat_field auto).

FOVs are read in place from the raw rounds: <data_dir>/<round>/PositionXXX/*<token>*.tif.
Output: <output_dir>/<channel>.tif (float32), the layout expected by
32_ashlar_stitch_mosaic_joint.sh --flat_field <output_dir>.

Example (IF channels, then the ref-round DAPI):
  python p33_estimate_flat_field.py --output_dir flat_field_GBM --round IF \\
      --channels ch00=561-CA9,ch01=488-CD144,ch02=647-CD31,ch03=DAPI \\
      --data_dirs /path/03_rawTifDir/GBM001/01_data /path/03_rawTifDir/GBM002/01_data
  python p33_estimate_flat_field.py --output_dir flat_field_GBM --round round001 --channels ch03=refDAPI \\
      --data_dirs /path/03_rawTifDir/GBM001/01_data /path/03_rawTifDir/GBM002/01_data
"""

import argparse
import importlib.util
import os
from pathlib import Path

import numpy as np
import scipy.ndimage
import skimage.io

_spec = importlib.util.spec_from_file_location(
    "prepare_noRef_layout",
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "p21_prepare_noRef_layout.py"
    ),
)
layout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(layout)


def main():
    parser = argparse.ArgumentParser(
        description="Pooled flat-field profile per channel"
    )
    parser.add_argument(
        "--data_dirs", nargs="+", required=True, help="01_data dirs (one per sample)"
    )
    parser.add_argument(
        "--round",
        required=True,
        help="Round dir inside each 01_data, e.g. IF or round001",
    )
    parser.add_argument(
        "--channels",
        required=True,
        help="token=name mapping, e.g. ch03=DAPI,ch02=647-CD31",
    )
    parser.add_argument("--output_dir", required=True)
    parser.add_argument(
        "--sigma", type=float, default=64.0, help="Gaussian smoothing (px)"
    )
    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    for token, name in layout.parse_channels(args.channels):
        acc, n, used = None, 0, 0
        for data_dir in args.data_dirs:
            round_dir = Path(data_dir) / args.round
            if not round_dir.is_dir():
                print(f"[FlatField] {name}: skip {data_dir} (no {args.round})")
                continue
            used += 1
            for pos_dir in layout.sorted_position_dirs(round_dir):
                path = layout.find_channel_file(pos_dir, token)
                img = skimage.io.imread(path)
                img = (np.max(img, axis=0) if img.ndim == 3 else img).astype(np.float64)
                if acc is not None and img.shape != acc.shape:
                    raise ValueError(
                        f"FOV shape {img.shape} differs from {acc.shape}: {path}"
                    )
                acc = img if acc is None else acc + img
                n += 1
        if acc is None:
            print(f"[FlatField] {name}: no FOVs found, nothing written")
            continue
        ff = scipy.ndimage.gaussian_filter(acc / n, args.sigma).astype(np.float32)
        ff /= ff.mean()
        h, w = ff.shape
        c = ff[
            h // 2 - h // 8 : h // 2 + h // 8, w // 2 - w // 8 : w // 2 + w // 8
        ].mean()
        out = os.path.join(args.output_dir, f"{name}.tif")
        skimage.io.imsave(out, ff, check_contrast=False)
        print(
            f"[FlatField] {name}: {n} FOVs from {used} samples, corner/centre {ff[:h // 20, :w // 20].mean() / c:.3f} -> {out}"
        )


if __name__ == "__main__":
    main()
