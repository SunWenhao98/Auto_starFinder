#!/usr/bin/env python3
"""Create sample-level raw data symlinks without copying image data."""

import argparse
import os
from pathlib import Path


def make_symlink(src, dst, force=False):
    if not src.exists():
        raise FileNotFoundError(f"Source path not found: {src}")

    abs_src = src.resolve()

    if dst.is_symlink():
        current = os.readlink(dst)
        current_path = Path(current)
        if not current_path.is_absolute():
            current_path = (dst.parent / current_path).resolve()
        else:
            current_path = current_path.resolve()

        if current_path == abs_src and current == str(abs_src):
            return "exists"
        if not force:
            raise FileExistsError(
                f"Symlink exists with non-absolute or different target: {dst} -> {current}"
            )
        dst.unlink()
    elif dst.exists():
        if not force:
            raise FileExistsError(f"Destination exists and is not a symlink: {dst}")
        raise FileExistsError(
            f"Refusing to replace non-symlink destination even with --force: {dst}"
        )

    dst.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(str(abs_src), dst)
    return "created"


def main():
    parser = argparse.ArgumentParser(description="Prepare sample raw data symlinks")
    parser.add_argument("--source_project_root", required=True, type=Path)
    parser.add_argument("--target_project_root", required=True, type=Path)
    parser.add_argument("--project_name", required=True)
    parser.add_argument(
        "--entries",
        default="round001,IF,round011",
        help="Comma-separated entries under 01_data to symlink.",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source_sample = args.source_project_root / args.project_name
    target_sample = args.target_project_root / args.project_name
    target_data = target_sample / "01_data"
    target_data.mkdir(parents=True, exist_ok=True)

    for entry in [x.strip() for x in args.entries.split(",") if x.strip()]:
        src = source_sample / "01_data" / entry
        dst = target_data / entry
        status = make_symlink(src, dst, args.force)
        print(f"{status}: {dst} -> {src}")

    print(f"Prepared raw data symlinks for {args.project_name}: {target_data}")


if __name__ == "__main__":
    main()
