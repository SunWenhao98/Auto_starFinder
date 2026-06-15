#!/usr/bin/env python3
"""
parse_pipeline_logs.py

统一从 StarFinder batch root 下的 submit* 目录提取日志结果。

使用示例：
  python parse_pipeline_logs.py --batch-root /path/to/batch --log-type decoding
  python parse_pipeline_logs.py --batch-root /path/to/batch --log-type global_spf
  python parse_pipeline_logs.py --batch-root /path/to/batch --log-type dapi_cp
  python parse_pipeline_logs.py --batch-root /path/to/batch --log-type gr_shift

固定映射：
  decoding   -> logs_global_readDecoding  -> zz_decoding
  global_spf -> logs_global_spot_finding  -> zz_globalspf
  dapi_cp    -> logs_dapi_segmentation    -> zz_dapicp
  gr_shift   -> logs_global_registration  -> zz_grshift

输入约定：
  --batch-root 指向包含 submit* 子目录的批次目录。
  --log-type  只能是 decoding/global_spf/dapi_cp/gr_shift 之一。

输出约定：
  每个包含目标日志目录的 submit* 会生成一个 CSV：
    <batch-root>/<zz_dir>/<submit_name>_<log_type>_results.csv

说明：
  - 不依赖 pandas，只使用 Python 标准库。
  - 缺失目标日志目录的 submit* 会跳过并打印警告。
  - gr_shift 输出一行一个 Position-Round，Time/dx/dy/dz 独立列保存，PositionXXX 按 XXX 数字排序。
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class LogConfig:
    log_dir: str
    output_dir: str
    columns: list[str]


DECODING_COLUMNS = [
    "submit_directory", "FOV_name", "SpotsFound_Total", "Crosstalk_Total", "Crosstalk_Ratio",
    "QCCount_Total", "QCCount_Total_Ratio", "ValidQCCount_Total", "ValidSpots_Total",
    "ValidQC_Total_Ratio", "IntensityQC_Count", "IntensityQC_Total_Ratio",
    "SeqD_SingleCheck_Count_Total", "SeqF_SingleCheck_Count_Total",
    "SeqD_SingleCheck_Prop_Total", "SeqF_SingleCheck_Prop_Total",
    "seqEnd_Count_Total", "seqEnd_Total_Ratio", "StrictMatch_Count_Total",
    "StrictMatch_Total_Ratio", "StrictMatch_vs_seqEnd_Ratio",
]

CONFIGS = {
    "decoding": LogConfig("logs_global_readDecoding", "zz_decoding", DECODING_COLUMNS),
    "global_spf": LogConfig(
        "logs_global_spot_finding",
        "zz_globalspf",
        ["submit_directory", "FOV_name", "SPF_Method", "Reference_Round", "Threshold", "Spots_Found"],
    ),
    "dapi_cp": LogConfig(
        "logs_dapi_segmentation",
        "zz_dapicp",
        [
            "submit_directory", "FOV_name", "raw_cell_detected", "raw_dapi_area",
            "filtered_dapi_area", "area_reduction_ratio", "filtered_cell_detected",
            "filtered_cell_removed",
        ],
    ),
    "gr_shift": LogConfig(
        "logs_global_registration",
        "zz_grshift",
        [
            "submit_directory", "FOV_name", "position_number", "round_name", "reference_round",
            "time", "dx", "dy", "dz",
        ],
    ),
}


def natural_number_from_position(value: str) -> int:
    match = re.search(r"(\d+)$", value or "")
    return int(match.group(1)) if match else 10**12


def log_task_id(path: Path) -> int:
    match = re.search(r"_(\d+)\.out$", path.name)
    return int(match.group(1)) if match else 10**12


def search(pattern: str, text: str, default: str = "0", flags: int = 0) -> str:
    match = re.search(pattern, text, flags)
    return match.group(1) if match else default


def to_int_text(value: str) -> str:
    value = str(value).replace(",", "")
    try:
        return str(int(value))
    except ValueError:
        return "0"


def ratio(num: int, den: int) -> str:
    return str(num / den) if den else "0"


def parse_stat(pattern: str, text: str) -> tuple[float, int, int]:
    match = re.search(pattern, text)
    if not match:
        return 0.0, 0, 0
    return float(match.group(1)), int(match.group(2)), int(match.group(3))


def parse_count_stat(pattern: str, text: str) -> tuple[float, int]:
    match = re.search(pattern, text)
    if not match:
        return 0.0, 0
    return float(match.group(1)), int(match.group(2))


def parse_decoding(text: str, submit_directory: str) -> list[dict[str, str]]:
    fov = search(r"选中的 Position 文件夹名称:\s*(Position\d+)", text, "")
    if not fov:
        return []
    qc_prop, qc_num, qc_den = parse_stat(
        r"([\d\.]+) \[(\d+) / (\d+)\] percent of reads are below score thresh (?!.*of all valid spots).*",
        text,
    )
    valid_prop, valid_num, valid_den = parse_stat(
        r"([\d\.]+) \[(\d+) / (\d+)\] percent of reads are below score thresh .* of all valid spots",
        text,
    )
    intensity_prop, intensity_num, _ = parse_stat(
        r"([\d\.]+) \[(\d+) / (\d+)\] percent of reads have intensity above [\d\.eE+-]+ in Reference Round \(Round \d+\)",
        text,
    )
    seqd_prop, seqd_num = parse_count_stat(
        r"([\d\.]+) \[(\d+) / \d+\] percent of reads match seqD barcode pattern", text
    )
    seqf_prop, seqf_num = parse_count_stat(
        r"([\d\.]+) \[(\d+) / \d+\] percent of reads match seqF barcode pattern", text
    )
    seqend_prop, seqend_num = parse_count_stat(
        r"([\d\.]+) \[(\d+) / \d+\] percent of good reads match barcode pattern", text
    )
    strict_prop, strict_num = parse_count_stat(
        r"([\d\.]+) \[(\d+) / \d+\] percent of good reads are in codebook", text
    )
    crosstalk = int(search(r"Geting max color\.\.\.\s+(\d+)\s+Decoding\.\.\.", text, "0", re.MULTILINE))
    return [{
        "submit_directory": submit_directory,
        "FOV_name": fov,
        "SpotsFound_Total": str(qc_den),
        "Crosstalk_Total": str(crosstalk),
        "Crosstalk_Ratio": ratio(crosstalk, qc_den),
        "QCCount_Total": str(qc_num),
        "QCCount_Total_Ratio": ratio(qc_num, qc_den),
        "ValidQCCount_Total": str(valid_num),
        "ValidSpots_Total": str(valid_den),
        "ValidQC_Total_Ratio": ratio(valid_num, valid_den),
        "IntensityQC_Count": str(intensity_num),
        "IntensityQC_Total_Ratio": str(intensity_prop),
        "SeqD_SingleCheck_Count_Total": str(seqd_num),
        "SeqF_SingleCheck_Count_Total": str(seqf_num),
        "SeqD_SingleCheck_Prop_Total": str(seqd_prop),
        "SeqF_SingleCheck_Prop_Total": str(seqf_prop),
        "seqEnd_Count_Total": str(seqend_num),
        "seqEnd_Total_Ratio": ratio(seqend_num, valid_den),
        "StrictMatch_Count_Total": str(strict_num),
        "StrictMatch_Total_Ratio": ratio(strict_num, valid_den),
        "StrictMatch_vs_seqEnd_Ratio": ratio(strict_num, seqend_num),
    }]


def parse_global_spf(text: str, submit_directory: str) -> list[dict[str, str]]:
    fov = search(r"选中的 Position 文件夹名称:\s*(\S+)", text, "")
    if not fov:
        return []
    return [{
        "submit_directory": submit_directory,
        "FOV_name": fov,
        "SPF_Method": search(r"Method:\s+(\S+)", text, ""),
        "Reference_Round": search(r"Reference round:\s+(\d+)", text, "0"),
        "Threshold": search(r"Intensity threshold:\s+([\d\.eE+-]+)", text, "0"),
        "Spots_Found": search(r"Number of spots found by \w+:\s+(\d+)", text, "0"),
    }]


def parse_dapi_cp(text: str, submit_directory: str) -> list[dict[str, str]]:
    fov = search(r"Loading 3D DAPI stack: .*/(Position\d+)/", text, "")
    if not fov:
        return []
    filtered = re.search(r"Filtered detected cells: (\d+) \(Removed (\d+)\)", text)
    return [{
        "submit_directory": submit_directory,
        "FOV_name": fov,
        "raw_cell_detected": search(r"Raw detected cells: (\d+)", text, "0"),
        "raw_dapi_area": to_int_text(search(r"Overall area of raw dapi: ([\d,]+)", text, "0")),
        "filtered_dapi_area": to_int_text(search(r"Overall area of filtered dapi: ([\d,]+)", text, "0")),
        "area_reduction_ratio": search(r"Area reduction ratio: ([\d\.]+)%", text, "0"),
        "filtered_cell_detected": filtered.group(1) if filtered else "0",
        "filtered_cell_removed": filtered.group(2) if filtered else "0",
    }]


def parse_gr_shift(text: str, submit_directory: str) -> list[dict[str, str]]:
    fov = search(r"选中的\s*Position\s*文件夹名称[:：]\s*(Position\d+)", text, "")
    if not fov:
        return []
    pos_num = natural_number_from_position(fov)
    rows = []
    rounds = re.findall(
        r"Round\s*(\d+)\s*vs\.\s*Round\s*(\d+)\s*finished\s*\[time=([0-9.]+)\]\s*[\r\n]+Shifted\s*by\s*([\-0-9]+)\s+([\-0-9]+)\s+([\-0-9]+)",
        text,
    )
    for moving_round, reference_round, elapsed, dx, dy, dz in rounds:
        rows.append({
            "submit_directory": submit_directory,
            "FOV_name": fov,
            "position_number": str(pos_num),
            "round_name": f"Round{moving_round}",
            "reference_round": f"Round{reference_round}",
            "time": elapsed,
            "dx": dx,
            "dy": dy,
            "dz": dz,
        })
    return rows


PARSERS: dict[str, Callable[[str, str], list[dict[str, str]]]] = {
    "decoding": parse_decoding,
    "global_spf": parse_global_spf,
    "dapi_cp": parse_dapi_cp,
    "gr_shift": parse_gr_shift,
}


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def iter_submit_dirs(batch_root: Path) -> Iterable[Path]:
    return sorted((p for p in batch_root.iterdir() if p.is_dir() and p.name.startswith("submit")), key=lambda p: p.name)


def parse_batch(batch_root: Path, log_type: str) -> int:
    config = CONFIGS[log_type]
    parser = PARSERS[log_type]
    output_dir = batch_root / config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    processed = 0
    for submit_dir in iter_submit_dirs(batch_root):
        log_dir = submit_dir / config.log_dir
        if not log_dir.is_dir():
            print(f"警告: {submit_dir.name} 缺少 {config.log_dir}，跳过。")
            continue
        rows: list[dict[str, str]] = []
        for log_file in sorted(log_dir.glob("*.out"), key=log_task_id):
            text = log_file.read_text(encoding="utf-8", errors="ignore")
            rows.extend(parser(text, batch_root.name))
        if log_type == "gr_shift":
            rows.sort(key=lambda row: (int(row.get("position_number") or 10**12), int(row.get("round_name", "Round0").replace("Round", "") or 0)))
        else:
            rows.sort(key=lambda row: natural_number_from_position(row.get("FOV_name", "")))
        if not rows:
            print(f"警告: {log_dir} 中没有可解析记录，跳过写出。")
            continue
        output_csv = output_dir / f"{submit_dir.name}_{log_type}_results.csv"
        write_csv(output_csv, config.columns, rows)
        processed += 1
        print(f"写出: {output_csv}")
    if processed == 0:
        print(f"未找到可处理日志: batch_root={batch_root}, log_type={log_type}")
    return processed


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="统一提取 StarFinder pipeline 日志为 per-submit CSV。",
        epilog="示例: python parse_pipeline_logs.py --batch-root /path/to/batch --log-type decoding",
        allow_abbrev=False,
    )
    parser.add_argument("--batch-root", required=True, type=Path, help="包含 submit* 子目录的批次目录")
    parser.add_argument("--log-type", required=True, choices=sorted(CONFIGS), help="日志类型")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    batch_root = args.batch_root.expanduser().resolve()
    if not batch_root.is_dir():
        raise SystemExit(f"错误: batch root 不存在或不是目录: {batch_root}")
    parse_batch(batch_root, args.log_type)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
