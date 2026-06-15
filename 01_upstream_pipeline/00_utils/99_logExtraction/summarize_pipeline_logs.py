#!/usr/bin/env python3
"""
summarize_pipeline_logs.py

统一汇总 parse_pipeline_logs.py 生成的 per-submit CSV。

使用示例：
  python summarize_pipeline_logs.py --batch-root /path/to/batch --log-type decoding
  python summarize_pipeline_logs.py --batch-root /path/to/batch --log-type global_spf
  python summarize_pipeline_logs.py --batch-root /path/to/batch --log-type dapi_cp
  python summarize_pipeline_logs.py --batch-root /path/to/batch --log-type gr_shift

固定映射：
  decoding   -> zz_decoding   -> zz_sum_decoding
  global_spf -> zz_globalspf  -> zz_sum_globalspf
  dapi_cp    -> zz_dapicp     -> zz_sum_dapicp
  gr_shift   -> zz_grshift    -> zz_sum_grshift

输出约定：
  summary 目录创建在对应 zz_* 目录内部，例如：
    <batch-root>/zz_decoding/zz_sum_decoding/

  保留单指标 summary CSV，便于后续可视化脚本逐指标读取。
  gr_shift 不使用字符串打包，分别输出 time/dx/dy/dz 四个指标 summary。
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SummaryConfig:
    parse_dir: str
    sum_dir: str
    result_suffix: str
    metrics: dict[str, str]


CONFIGS = {
    "decoding": SummaryConfig(
        "zz_decoding",
        "zz_sum_decoding",
        "decoding_summary_result.csv",
        {
            "SpotsFound_Total": "SpotsFound_Total_summary.csv",
            "Crosstalk_Ratio": "Crosstalk_Ratio_summary.csv",
            "ValidQCCount_Total": "ValidQCCount_Total_summary.csv",
            "ValidQC_Total_Ratio": "ValidQC_Total_Ratio_summary.csv",
            "IntensityQC_Count": "IntensityQC_Count_data_summary.csv",
            "IntensityQC_Total_Ratio": "IntensityQC_Total_Ratio_data_summary.csv",
            "SeqD_SingleCheck_Count_Total": "SeqD_SingleCheck_Count_Total_summary.csv",
            "SeqF_SingleCheck_Count_Total": "SeqF_SingleCheck_Count_Total_summary.csv",
            "SeqD_SingleCheck_Prop_Total": "SeqD_SingleCheck_Prop_Total_summary.csv",
            "SeqF_SingleCheck_Prop_Total": "SeqF_SingleCheck_Prop_Total_summary.csv",
            "seqEnd_Count_Total": "seqEnd_Count_Total_summary.csv",
            "seqEnd_Total_Ratio": "seqEnd_Total_Ratio_summary.csv",
            "StrictMatch_Count_Total": "StrictMatch_Count_Total_summary.csv",
            "StrictMatch_Total_Ratio": "StrictMatch_Total_Ratio_summary.csv",
            "StrictMatch_vs_seqEnd_Ratio": "StrictMatch_vs_seqEnd_Ratio_summary.csv",
        },
    ),
    "global_spf": SummaryConfig(
        "zz_globalspf",
        "zz_sum_globalspf",
        "global_spf_summary_result.csv",
        {"Spots_Found": "Spots_Found_data_summary.csv"},
    ),
    "dapi_cp": SummaryConfig(
        "zz_dapicp",
        "zz_sum_dapicp",
        "dapi_cp_summary_result.csv",
        {
            "raw_cell_detected": "raw_cell_detected_data_summary.csv",
            "raw_dapi_area": "raw_dapi_area_data_summary.csv",
            "filtered_dapi_area": "filtered_dapi_area_data_summary.csv",
            "area_reduction_ratio": "area_reduction_ratio_data_summary.csv",
            "filtered_cell_detected": "filtered_cell_detected_data_summary.csv",
            "filtered_cell_removed": "filtered_cell_removed_data_summary.csv",
        },
    ),
    "gr_shift": SummaryConfig(
        "zz_grshift",
        "zz_sum_grshift",
        "grshift_summary_result.csv",
        {
            "time": "time_summary.csv",
            "dx": "dx_summary.csv",
            "dy": "dy_summary.csv",
            "dz": "dz_summary.csv",
        },
    ),
}


def position_number(value: str) -> int:
    match = re.search(r"(\d+)$", value or "")
    return int(match.group(1)) if match else 10**12


def round_number(value: str) -> int:
    match = re.search(r"(\d+)$", value or "")
    return int(match.group(1)) if match else 10**12


def submit_key(path: Path, log_type: str) -> str:
    suffix = f"_{log_type}_results.csv"
    if path.name.endswith(suffix):
        return path.name[: -len(suffix)]
    return path.stem


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_matrix(path: Path, row_key: str, columns: list[str], rows: list[tuple[str, dict[str, str]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[row_key] + columns)
        writer.writeheader()
        for key, values in rows:
            out = {row_key: key}
            out.update({column: values.get(column, "") for column in columns})
            writer.writerow(out)


def summarize_standard(csv_files: list[Path], log_type: str, metric: str) -> tuple[list[str], list[tuple[str, dict[str, str]]]]:
    matrix: dict[str, dict[str, str]] = {}
    columns: list[str] = []
    for path in csv_files:
        key = submit_key(path, log_type)
        columns.append(key)
        for row in read_rows(path):
            fov = row.get("FOV_name", "")
            if not fov:
                continue
            matrix.setdefault(fov, {})[key] = row.get(metric, "")
    rows = sorted(matrix.items(), key=lambda item: position_number(item[0]))
    return columns, rows


def summarize_gr_shift(csv_files: list[Path], metric: str) -> tuple[list[str], list[tuple[str, dict[str, str]]]]:
    matrix: dict[str, dict[str, str]] = {}
    columns: list[str] = []
    seen_columns: set[str] = set()
    for path in csv_files:
        key = submit_key(path, "gr_shift")
        for row in read_rows(path):
            fov = row.get("FOV_name", "")
            round_name = row.get("round_name", "")
            if not fov or not round_name:
                continue
            column = f"{key}__{round_name}"
            if column not in seen_columns:
                columns.append(column)
                seen_columns.add(column)
            matrix.setdefault(fov, {})[column] = row.get(metric, "")
    columns.sort(key=lambda col: (col.split("__", 1)[0], round_number(col.split("__", 1)[1]) if "__" in col else 0))
    rows = sorted(matrix.items(), key=lambda item: position_number(item[0]))
    return columns, rows


def write_combined_summary(path: Path, metric_files: dict[str, Path]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        first = True
        for metric, metric_file in metric_files.items():
            if not first:
                writer.writerow([])
            first = False
            writer.writerow([f"### {metric} ###"])
            with metric_file.open(newline="", encoding="utf-8") as source:
                for row in csv.reader(source):
                    writer.writerow(row)


def summarize_batch(batch_root: Path, log_type: str) -> int:
    config = CONFIGS[log_type]
    parse_dir = batch_root / config.parse_dir
    sum_dir = parse_dir / config.sum_dir
    sum_dir.mkdir(parents=True, exist_ok=True)
    csv_files = sorted(parse_dir.glob(f"*_{log_type}_results.csv")) if parse_dir.is_dir() else []
    if not csv_files:
        print(f"未找到可汇总 CSV: {parse_dir}")
        return 0

    metric_outputs: dict[str, Path] = {}
    for metric, filename in config.metrics.items():
        if log_type == "gr_shift":
            columns, rows = summarize_gr_shift(csv_files, metric)
        else:
            columns, rows = summarize_standard(csv_files, log_type, metric)
        output = sum_dir / filename
        write_matrix(output, "FOV_name", columns, rows)
        metric_outputs[metric] = output
        print(f"写出: {output}")

    combined = sum_dir / f"{batch_root.name}_{config.result_suffix}"
    write_combined_summary(combined, metric_outputs)
    print(f"写出: {combined}")
    return len(metric_outputs)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="统一汇总 parse_pipeline_logs.py 输出的 per-submit CSV。",
        epilog="示例: python summarize_pipeline_logs.py --batch-root /path/to/batch --log-type decoding",
        allow_abbrev=False,
    )
    parser.add_argument("--batch-root", required=True, type=Path, help="包含 zz_* 输出目录的批次目录")
    parser.add_argument("--log-type", required=True, choices=sorted(CONFIGS), help="日志类型")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    batch_root = args.batch_root.expanduser().resolve()
    if not batch_root.is_dir():
        raise SystemExit(f"错误: batch root 不存在或不是目录: {batch_root}")
    summarize_batch(batch_root, args.log_type)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
