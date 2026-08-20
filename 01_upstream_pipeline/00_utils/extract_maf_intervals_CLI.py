#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT_TAG = "XYZStagePointDefinitionList"
POINT_TAG = "XYZStagePointDefinition"
ROOT_MARKER = b"<XYZStagePointDefinitionList"
POSITION_IDENTIFIER_PATTERN = re.compile(r"Position([0-9]+)")
EXPECTED_PREAMBLE = (
    b'<?xml version="1.0"?>\n'
    b"<!--Leica Application Suite X (LAS X)-->\n"
    b"<!--Leica Microsystems CMS GmbH-->\n"
    b"<!--http://www.confocal-microscopy.com-->\n"
    b"<!--LAS X 4.6.1.27508-->\n"
)


def parse_position_ranges(value: str) -> set[int]:
    normalized = re.sub(r"\s+", "", value)
    if not normalized:
        raise ValueError("position_ranges cannot be empty")

    positions: set[int] = set()
    for item in normalized.split(","):
        if not item:
            raise ValueError("position_ranges contains an empty item")

        if re.fullmatch(r"[0-9]+", item):
            start = end = int(item)
        else:
            match = re.fullmatch(r"([0-9]+)-([0-9]+)", item)
            if match is None:
                raise ValueError(f"invalid position range: {item!r}")
            start = int(match.group(1))
            end = int(match.group(2))

        if start > end:
            raise ValueError(f"position range start is greater than end: {item!r}")
        positions.update(range(start, end + 1))

    return positions


def _validate_paths(input_path: Path, output_path: Path) -> None:
    if not input_path.is_file():
        raise FileNotFoundError(f"input_file not found or not a regular file: {input_path}")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("input_file and output_file must be different paths")
    if output_path.exists():
        raise FileExistsError(f"output_file already exists; refusing to overwrite: {output_path}")
    if not output_path.parent.is_dir():
        raise FileNotFoundError(f"output_file parent directory not found: {output_path.parent}")


def _extract_preamble(raw_bytes: bytes) -> bytes:
    root_offset = raw_bytes.find(ROOT_MARKER)
    if root_offset < 0:
        raise ValueError(f"MAF root element {ROOT_TAG!r} not found")
    preamble = raw_bytes[:root_offset]
    if preamble != EXPECTED_PREAMBLE:
        raise ValueError("MAF XML declaration or LAS X comment preamble does not match the expected format")
    return preamble


def _parse_position_number(point: ET.Element, index: int) -> int:
    identifier = point.get("PositionIdentifier")
    if identifier is None:
        raise ValueError(f"PositionIdentifier missing at stage-point index {index}")
    match = POSITION_IDENTIFIER_PATTERN.fullmatch(identifier)
    if match is None:
        raise ValueError(f"PositionIdentifier must match PositionN at stage-point index {index}: {identifier!r}")

    position_id = point.get("PositionID")
    if position_id is None or re.fullmatch(r"[0-9]+", position_id) is None:
        raise ValueError(f"PositionID must be a nonnegative integer for {identifier}: {position_id!r}")

    number = int(match.group(1))
    if int(position_id) != number:
        raise ValueError(f"PositionID {position_id} does not match {identifier}")
    return number


def _validate_serialized_output(output_bytes: bytes, preamble: bytes, expected_numbers: list[int]) -> None:
    if not output_bytes.startswith(preamble):
        raise ValueError("serialized MAF preamble changed unexpectedly")

    root = ET.fromstring(output_bytes)
    if root.tag != ROOT_TAG:
        raise ValueError(f"serialized MAF root must be {ROOT_TAG!r}, found {root.tag!r}")

    points = list(root)
    if any(point.tag != POINT_TAG for point in points):
        raise ValueError("serialized MAF contains an unexpected direct child element")
    observed_numbers = [_parse_position_number(point, index) for index, point in enumerate(points, start=1)]
    if observed_numbers != expected_numbers:
        raise ValueError("serialized MAF PositionIdentifier sequence does not match the requested positions")


def _publish_without_overwrite(output_bytes: bytes, input_path: Path, output_path: Path) -> None:
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(output_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, input_path.stat().st_mode & 0o666)
        os.link(temporary_path, output_path)
    except FileExistsError as error:
        raise FileExistsError(f"output_file already exists; refusing to overwrite: {output_path}") from error
    finally:
        temporary_path.unlink(missing_ok=True)


def extract_maf_positions(
    input_file: str | Path,
    output_file: str | Path,
    requested_positions: set[int],
) -> dict[str, int]:
    if not requested_positions:
        raise ValueError("requested_positions cannot be empty")

    input_path = Path(input_file)
    output_path = Path(output_file)
    _validate_paths(input_path, output_path)

    raw_bytes = input_path.read_bytes()
    preamble = _extract_preamble(raw_bytes)
    root = ET.fromstring(raw_bytes)
    if root.tag != ROOT_TAG:
        raise ValueError(f"MAF root must be {ROOT_TAG!r}, found {root.tag!r}")

    points = list(root)
    if any(point.tag != POINT_TAG for point in points):
        raise ValueError("MAF contains an unexpected direct child element")

    point_numbers: list[int] = []
    seen_numbers: set[int] = set()
    for index, point in enumerate(points, start=1):
        number = _parse_position_number(point, index)
        if number in seen_numbers:
            raise ValueError(f"duplicate PositionIdentifier found: Position{number}")
        seen_numbers.add(number)
        point_numbers.append(number)

    missing_numbers = sorted(requested_positions - seen_numbers)
    if missing_numbers:
        missing_text = ",".join(f"Position{number}" for number in missing_numbers[:20])
        raise ValueError(f"requested Position values are missing: {missing_text}")

    expected_numbers = [number for number in point_numbers if number in requested_positions]
    for point, number in zip(points, point_numbers, strict=True):
        if number not in requested_positions:
            root.remove(point)

    output_bytes = preamble + ET.tostring(root, encoding="utf-8")
    _validate_serialized_output(output_bytes, preamble, expected_numbers)
    _publish_without_overwrite(output_bytes, input_path, output_path)

    initial_count = len(points)
    kept_count = len(expected_numbers)
    return {
        "initial_count": initial_count,
        "requested_count": len(requested_positions),
        "kept_count": kept_count,
        "removed_count": initial_count - kept_count,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从 Leica LAS X MAF 文件中提取多个 Position 单点或连续闭区间。",
        epilog=(
            "示例:\n"
            "  python extract_maf_intervals_CLI.py --input_file input.maf "
            "--output_file selected.maf --position_ranges \"67, 896-902, 908-913\""
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input_file", required=True, type=Path, help="输入 MAF 文件路径")
    parser.add_argument("--output_file", required=True, type=Path, help="输出 MAF 文件路径，不能已存在")
    parser.add_argument(
        "--position_ranges",
        required=True,
        help="要提取的 Position，例如：67, 896-902, 908-913",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        requested_positions = parse_position_ranges(args.position_ranges)
        stats = extract_maf_positions(args.input_file, args.output_file, requested_positions)
    except (OSError, ValueError, ET.ParseError) as error:
        parser.exit(1, f"ERROR: {error}\n")

    print(f"input_file={args.input_file}")
    print(f"output_file={args.output_file}")
    print(f"position_ranges={args.position_ranges}")
    print(f"initial_count={stats['initial_count']}")
    print(f"requested_count={stats['requested_count']}")
    print(f"kept_count={stats['kept_count']}")
    print(f"removed_count={stats['removed_count']}")
    print("STATUS: SUCCESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
