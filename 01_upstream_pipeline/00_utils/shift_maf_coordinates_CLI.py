#!/usr/bin/env python3
"""平移 Leica LAS X MAF 坐标，仅替换数值，逐字节保留头部及其他内容。

示例：python shift_maf_coordinates_CLI.py --input_file input.maf \
    --x_shift 0.0001 --y_shift -0.0002 --output_file shifted.maf
偏移量与原 StageXPos/StageYPos 单位相同，不做单位换算。
"""
from __future__ import annotations

import argparse
import os
import re
import tempfile
from decimal import Decimal, DecimalException, localcontext
from pathlib import Path
from xml.parsers import expat


ROOT_TAG = "XYZStagePointDefinitionList"
POINT_TAG = "XYZStagePointDefinition"
START_TAG = re.compile(rb'''<XYZStagePointDefinition\b(?:[^>"']|"[^"]*"|'[^']*')*>''')
ATTRIBUTE = re.compile(rb'''([^\s=<>]+)\s*=\s*(["'])(.*?)\2''', re.DOTALL)
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def parse_decimal(value: str) -> Decimal:
    """只接受有限十进制数，避免 NaN/Infinity 进入采集坐标。"""
    if NUMBER.fullmatch(value) is None:
        raise ValueError(f"invalid finite decimal: {value!r}")
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError(f"invalid finite decimal: {value!r}")
    return number


def shift_coordinates(raw_bytes: bytes, x_shift: Decimal, y_shift: Decimal) -> tuple[bytes, int]:
    """用 XML 解析器定位真实采集点，再拼接未改动字节和新坐标。"""
    if not x_shift.is_finite() or not y_shift.is_finite():
        raise ValueError("shifts must be finite")
    parser = expat.ParserCreate()
    shifts = {b"StageXPos": x_shift, b"StageYPos": y_shift}
    replacements: list[tuple[int, int, bytes]] = []
    point_count = 0
    depth = 0

    def start_element(name: str, attributes: dict[str, str]) -> None:
        nonlocal depth, point_count
        if depth == 0 and name != ROOT_TAG:
            raise ValueError(f"MAF root must be {ROOT_TAG}")
        if depth == 1 and name != POINT_TAG:
            raise ValueError(f"unexpected stage-list child: {name}")
        if name == POINT_TAG:
            if depth != 1:
                raise ValueError("stage points must be direct children of the root")
            offset = parser.CurrentByteIndex
            tag = START_TAG.match(raw_bytes, offset)
            if tag is None:
                raise ValueError("unsupported MAF encoding; expected ASCII-compatible XML")
            found: set[bytes] = set()
            for attribute in ATTRIBUTE.finditer(tag.group()):
                key = attribute.group(1)
                if key not in shifts:
                    continue
                found.add(key)
                value = parse_decimal(attributes[key.decode("ascii")])
                shift = shifts[key]
                if shift == 0:
                    continue
                # 根据有效数字和数量级差扩展精度，避免二进制浮点误差或舍入。
                with localcontext() as context:
                    context.prec = max(
                        len(value.as_tuple().digits), len(shift.as_tuple().digits), 28
                    ) + abs(value.adjusted() - shift.adjusted()) + 2
                    shifted = format(value + shift, "f").encode("ascii")
                replacements.append((
                    offset + attribute.start(3), offset + attribute.end(3), shifted
                ))
            if found != set(shifts):
                raise ValueError(f"StageXPos/StageYPos missing at stage point {point_count + 1}")
            point_count += 1
        depth += 1

    def end_element(name: str) -> None:
        nonlocal depth
        depth -= 1

    def reject_doctype(name: str, system_id: str | None, public_id: str | None, internal: int) -> None:
        raise ValueError("DOCTYPE is not supported in MAF files")

    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    parser.StartDoctypeDeclHandler = reject_doctype
    parser.Parse(raw_bytes, True)
    if point_count == 0:
        raise ValueError("MAF contains no stage points")

    chunks: list[bytes] = []
    cursor = 0
    for start, end, value in replacements:
        chunks.extend((raw_bytes[cursor:start], value))
        cursor = end
    chunks.append(raw_bytes[cursor:])
    return b"".join(chunks), point_count


def publish_output(output_bytes: bytes, input_file: Path, output_file: Path) -> None:
    """先写同目录临时文件，再原子发布；已有输出绝不覆盖。"""
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output_file.name}.", dir=output_file.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(output_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, input_file.stat().st_mode & 0o666)
        os.link(temporary_path, output_file)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="平移所有 MAF 采集点的 StageXPos/StageYPos，原样保留头部和其余字节。",
        epilog="新坐标 = 原坐标 + shift；单位与原坐标一致，不做换算。输出父目录须已存在。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input_file", required=True, type=Path, help="输入 MAF 文件，只读")
    parser.add_argument("--x_shift", default="0", help="X 坐标偏移量，允许负数")
    parser.add_argument("--y_shift", default="0", help="Y 坐标偏移量，允许负数")
    parser.add_argument("--output_file", required=True, type=Path, help="输出文件完整路径，不得已存在")
    args = parser.parse_args()
    input_file = Path(args.input_file)
    output_file = Path(args.output_file)
    try:
        x_shift = parse_decimal(args.x_shift)
        y_shift = parse_decimal(args.y_shift)
        if input_file.resolve() == output_file.resolve():
            raise ValueError("input_file and output_file must be different paths")
        if output_file.exists() or output_file.is_symlink():
            raise FileExistsError(f"refusing to overwrite output_file: {output_file}")
        output_bytes, count = shift_coordinates(input_file.read_bytes(), x_shift, y_shift)
        publish_output(output_bytes, input_file, output_file)
    except (OSError, ValueError, DecimalException, expat.ExpatError) as error:
        parser.exit(1, f"ERROR: {error}\n")

    print(f"input_file={input_file}")
    print(f"output_file={output_file}")
    print(f"x_shift={x_shift}, y_shift={y_shift}")
    print(f"point_count={count}")
    print("STATUS: SUCCESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
