#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple

import pandas as pd


class ExtractResult(NamedTuple):
    gene_counts_csv: Path
    position_summary_csv: Path
    suffix_summary_csv: Path
    normalization_report_tsv: Path


POSITION_RE = re.compile(r"Position(\d+)", re.IGNORECASE)


def parse_optional_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    value = value.strip()
    if value == "" or value.lower() in {"none", "null", "na"}:
        return None
    return int(value)


def position_number(path: Path) -> int | None:
    match = POSITION_RE.search(path.name)
    if not match:
        return None
    return int(match.group(1))


def iter_position_dirs(registration_dir: Path, start_pos: int | None, end_pos: int | None) -> list[Path]:
    positions = []
    for candidate in registration_dir.iterdir():
        if not candidate.is_dir() or not candidate.name.startswith("Position"):
            continue
        number = position_number(candidate)
        if number is None:
            continue
        if start_pos is not None and number < start_pos:
            continue
        if end_pos is not None and number > end_pos:
            continue
        positions.append(candidate)
    positions.sort(key=lambda path: position_number(path) or 0)
    return positions


def normalize_gene_label(raw_gene: object, suffix_regex: str | None) -> tuple[str | None, str]:
    if pd.isna(raw_gene):
        return None, "EMPTY"
    gene = str(raw_gene).strip()
    if gene == "":
        return None, "EMPTY"
    if not suffix_regex:
        return gene, "NO_SUFFIX_RULE"
    match = re.search(suffix_regex, gene)
    if not match:
        return gene, "NO_MATCH"
    suffix = match.group(1) if match.groups() else match.group(0).lstrip("_")
    normalized = re.sub(suffix_regex, "", gene)
    return normalized, suffix


def output_prefix(sample_id: str, target_file: str) -> str:
    return f"{sample_id}_{Path(target_file).stem}"


def extract_gene_counts(
    registration_dir: Path | str,
    target_file: str,
    gene_column: str = "Gene",
    suffix_regex: str | None = r"_(rbRNA|ntRNA)$",
    output_subdir: str = "00_gene_counts",
    sample_id: str | None = None,
    start_pos: int | None = None,
    end_pos: int | None = None,
) -> ExtractResult:
    registration_dir = Path(registration_dir)
    if not registration_dir.is_dir():
        raise FileNotFoundError(f"registration_dir does not exist: {registration_dir}")

    start_pos = parse_optional_int(start_pos)
    end_pos = parse_optional_int(end_pos)
    sample_id = sample_id or registration_dir.name
    out_dir = registration_dir / output_subdir
    out_dir.mkdir(parents=True, exist_ok=True)

    gene_counter: Counter[str] = Counter()
    suffix_counter: Counter[str] = Counter()
    position_rows = []
    normalization_rows = []

    positions = iter_position_dirs(registration_dir, start_pos, end_pos)
    if not positions:
        raise RuntimeError(f"No Position* directories found in {registration_dir}")

    for pos_dir in positions:
        csv_path = pos_dir / target_file
        if not csv_path.exists():
            position_rows.append(
                {"position": pos_dir.name, "status": "missing_file", "file": str(csv_path), "rows_total": 0, "rows_used": 0}
            )
            continue

        df = pd.read_csv(csv_path)
        if gene_column not in df.columns:
            position_rows.append(
                {"position": pos_dir.name, "status": "missing_gene_column", "file": str(csv_path), "rows_total": len(df), "rows_used": 0}
            )
            continue

        rows_used = 0
        for raw_gene in df[gene_column]:
            normalized, suffix = normalize_gene_label(raw_gene, suffix_regex)
            suffix_counter[suffix] += 1
            if normalized is None:
                continue
            gene_counter[normalized] += 1
            rows_used += 1
            if normalized != str(raw_gene).strip() or suffix in {"NO_MATCH", "NO_SUFFIX_RULE"}:
                normalization_rows.append(
                    {
                        "position": pos_dir.name,
                        "raw_gene": str(raw_gene).strip(),
                        "gene_symbol": normalized,
                        "suffix": suffix,
                    }
                )

        position_rows.append(
            {"position": pos_dir.name, "status": "processed", "file": str(csv_path), "rows_total": len(df), "rows_used": rows_used}
        )

    if not gene_counter:
        raise RuntimeError("No gene labels were counted from processed files")

    prefix = output_prefix(sample_id, target_file)
    gene_counts_csv = out_dir / f"{prefix}_gene_counts.csv"
    position_summary_csv = out_dir / f"{prefix}_position_summary.csv"
    suffix_summary_csv = out_dir / f"{prefix}_suffix_summary.csv"
    normalization_report_tsv = out_dir / f"{prefix}_gene_normalization_report.tsv"

    pd.DataFrame(sorted(gene_counter.items()), columns=["gene_symbol", "gene_counts"]).to_csv(gene_counts_csv, index=False)
    pd.DataFrame(position_rows).to_csv(position_summary_csv, index=False)
    pd.DataFrame(sorted(suffix_counter.items()), columns=["suffix", "count"]).to_csv(suffix_summary_csv, index=False)
    pd.DataFrame(normalization_rows).to_csv(normalization_report_tsv, sep="\t", index=False)

    return ExtractResult(gene_counts_csv, position_summary_csv, suffix_summary_csv, normalization_report_tsv)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate StarFinder goodPoints Gene labels to gene-level counts.")
    parser.add_argument("--registration-dir", required=True, type=Path, help="Registration directory containing Position* folders.")
    parser.add_argument("--target-file", default="goodPoints_max3d_0.2_tri.csv", help="CSV file name under each Position* folder.")
    parser.add_argument("--gene-column", default="Gene", help="Column containing decoded gene/state labels.")
    parser.add_argument("--suffix-regex", default=r"_(rbRNA|ntRNA)$", help="Regex for state suffix to remove from the end of Gene labels.")
    parser.add_argument("--output-subdir", default="00_gene_counts", help="Output subdirectory under registration-dir.")
    parser.add_argument("--sample-id", default=None, help="Sample ID prefix for output files. Defaults to registration dir name.")
    parser.add_argument("--start-pos", default=None, help="Optional first Position number, inclusive. Use none to disable.")
    parser.add_argument("--end-pos", default=None, help="Optional last Position number, inclusive. Use none to disable.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = extract_gene_counts(
        registration_dir=args.registration_dir,
        target_file=args.target_file,
        gene_column=args.gene_column,
        suffix_regex=args.suffix_regex,
        output_subdir=args.output_subdir,
        sample_id=args.sample_id,
        start_pos=parse_optional_int(args.start_pos),
        end_pos=parse_optional_int(args.end_pos),
    )
    print(f"Gene counts: {result.gene_counts_csv}")
    print(f"Position summary: {result.position_summary_csv}")
    print(f"Suffix summary: {result.suffix_summary_csv}")
    print(f"Normalization report: {result.normalization_report_tsv}")
    print("STATUS: SUCCESS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
