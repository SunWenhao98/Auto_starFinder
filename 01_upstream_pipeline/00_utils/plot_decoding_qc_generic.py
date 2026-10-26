#!/usr/bin/env python3
"""
Create generic QC figures for StarFinder SpotDecode decoding logs.

The script reads per-submit ``*_decoding_results.csv`` files produced by
``parse_pipeline_logs.py``. It keeps visualization focused on the six decoding
QC metrics currently used for upstream log review; parser and summarizer output
schemas are left unchanged.
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd



QC_METRICS = [
    "SpotsFound_Total",
    "Crosstalk_Ratio",
    "StrictMatch_Count_Total",
    "StrictMatch_Total_Ratio",
    "SeqD_SingleCheck_Prop_Total",
    "SeqF_SingleCheck_Prop_Total",
]

LOG_SCALE_METRICS = {"SpotsFound_Total", "StrictMatch_Count_Total"}
RAW_CROSSTALK_METRICS = {"SpotsFound_Total", "Crosstalk_Ratio"}
FILTER_HIGH_CROSSTALK_METRICS = [
    "StrictMatch_Count_Total",
    "StrictMatch_Total_Ratio",
    "SeqD_SingleCheck_Prop_Total",
    "SeqF_SingleCheck_Prop_Total",
]
BOUNDED_RATIO_METRICS = {
    "Crosstalk_Ratio",
    "StrictMatch_Total_Ratio",
    "SeqD_SingleCheck_Prop_Total",
    "SeqF_SingleCheck_Prop_Total",
}

METRIC_LABELS = {
    "SpotsFound_Total": "Spots found",
    "Crosstalk_Ratio": "Crosstalk ratio",
    "StrictMatch_Count_Total": "Strict-match spots",
    "StrictMatch_Total_Ratio": "Strict-match ratio",
    "SeqD_SingleCheck_Prop_Total": "seqD barcode match prop.",
    "SeqF_SingleCheck_Prop_Total": "seqF barcode match prop.",
}

OKABE_ITO = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"]
SUBMIT_RE = re.compile(r"^(?P<submit>submit(?P<number>\d+))_(?P<label>.+?)_decoding_results\.csv$")
SAMPLE_RE = re.compile(r"^(GBM\d+|[A-Za-z]+\d+)$")
NON_CONDITION_TOKENS = {"spfDecodeTest", "SpotDecode", "decoding"}


class QCError(ValueError):
    """Raised when decoding QC inputs do not match expected schema."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot six-metric StarFinder SpotDecode decoding QC PNG figures.",
        allow_abbrev=False,
    )
    parser.add_argument("--batch-root", type=Path, required=True, help="StarFinder batch root.")
    parser.add_argument(
        "--zz-decoding",
        type=Path,
        default=None,
        help="Directory containing *_decoding_results.csv files. Defaults to <batch-root>/zz_decoding.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to <zz-decoding>/plot_decoding_qc_generic.",
    )
    parser.add_argument(
        "--crosstalk-cutoff",
        type=float,
        default=0.8,
        help="Flag FOVs with Crosstalk_Ratio greater than this cutoff.",
    )
    parser.add_argument("--group_by", choices=("condition", "sample"), default="condition", help="Plot by inferred condition or by sample.")
    parser.add_argument("--dpi", type=int, default=300, help="PNG output resolution.")
    return parser.parse_args()


def infer_submit_metadata(path: Path) -> tuple[str, int, str, str]:
    match = SUBMIT_RE.match(path.name)
    if not match:
        raise QCError(f"Cannot parse submit/sample from filename: {path.name}")
    submit_name = match.group("submit")
    submit_number = int(match.group("number"))
    label_parts = match.group("label").split("_")
    sample = label_parts[0]
    if not SAMPLE_RE.match(sample):
        sample = match.group("label")
    condition = "_".join(label_parts[1:]) if len(label_parts) > 1 else ""
    if not condition or condition in NON_CONDITION_TOKENS:
        condition = f"group{submit_number // 10:02d}"
    return submit_name, submit_number, sample, condition


def read_decoding_tables(zz_decoding: Path) -> pd.DataFrame:
    paths = sorted(zz_decoding.glob("*_decoding_results.csv"))
    if not paths:
        raise QCError(f"No *_decoding_results.csv files found in {zz_decoding}")

    frames: list[pd.DataFrame] = []
    for path in paths:
        submit_name, submit_number, sample, condition = infer_submit_metadata(path)
        frame = pd.read_csv(path)
        required = {"FOV_name", *QC_METRICS}
        missing = required.difference(frame.columns)
        if missing:
            raise QCError(f"Missing columns in {path}: {', '.join(sorted(missing))}")
        frame.insert(0, "submit_name", submit_name)
        frame.insert(1, "submit_number", submit_number)
        frame.insert(2, "sample", sample)
        frame.insert(3, "condition", condition)
        frames.append(frame)

    data = pd.concat(frames, ignore_index=True)
    data["fov_number"] = data["FOV_name"].astype(str).str.extract(r"(\d+)").astype(float)
    for column in QC_METRICS:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data.sort_values(["condition", "sample", "submit_number", "fov_number", "FOV_name"]).reset_index(drop=True)


def save_figure(fig: plt.Figure, output_dir: Path, stem: str, dpi: int) -> None:
    fig.savefig(output_dir / f"{stem}.png", bbox_inches="tight", dpi=dpi, facecolor="white")
    plt.close(fig)


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8,
            "axes.labelsize": 9,
            "axes.titlesize": 9,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "legend.fontsize": 7,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def write_summary_tables(data: pd.DataFrame, output_dir: Path, crosstalk_cutoff: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    tidy = data.melt(
        id_vars=["submit_name", "submit_number", "sample", "condition", "FOV_name", "fov_number"],
        value_vars=QC_METRICS,
        var_name="metric",
        value_name="value",
    )
    tidy.to_csv(output_dir / "decoding_qc_tidy.csv", index=False)

    submit_summary = (
        data.groupby(["condition", "sample", "submit_name"], dropna=False)[QC_METRICS]
        .agg(["count", "mean", "median", "min", "max"])
        .reset_index()
    )
    submit_summary.columns = ["_".join([str(part) for part in col if part]) for col in submit_summary.columns.to_flat_index()]
    submit_summary.to_csv(output_dir / "decoding_qc_submit_summary.csv", index=False)

    flagged = data.loc[
        data["Crosstalk_Ratio"] > crosstalk_cutoff,
        ["condition", "sample", "submit_name", "FOV_name", "Crosstalk_Ratio"],
    ]
    flagged.to_csv(output_dir / "decoding_qc_high_crosstalk_fovs.csv", index=False)
    return tidy, flagged


def sample_color_map(data: pd.DataFrame) -> dict[str, str]:
    samples = list(dict.fromkeys(data["sample"].astype(str)))
    return {sample: OKABE_ITO[index % len(OKABE_ITO)] for index, sample in enumerate(samples)}


def select_metric_plot_data(data: pd.DataFrame, metric: str, crosstalk_cutoff: float) -> pd.DataFrame:
    if metric in RAW_CROSSTALK_METRICS:
        return data
    if metric in FILTER_HIGH_CROSSTALK_METRICS:
        return data.loc[data["Crosstalk_Ratio"] <= crosstalk_cutoff]
    raise QCError(f"Unsupported metric for plotting: {metric}")


def add_shared_legend(fig: plt.Figure, sample_colors: dict[str, str]) -> None:
    handles = [
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=color, markeredgecolor=color, markersize=4, label=sample)
        for sample, color in sample_colors.items()
    ]
    handles.append(plt.Line2D([0], [0], marker="x", color="#B00020", linestyle="none", markersize=5, label="Crosstalk > cutoff"))
    handles.append(plt.Line2D([0], [0], color="#B00020", linestyle="--", linewidth=1.1, label="Crosstalk cutoff"))
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.02),
        ncol=min(5, len(handles)),
        frameon=False,
        fontsize=8,
        handlelength=1.6,
        columnspacing=1.2,
    )


def format_count_tick(value: float, _position: int) -> str:
    if value <= 0 or not math.isfinite(value):
        return ""
    if value >= 1_000_000:
        return f"{value / 1_000_000:g}M"
    if value >= 1_000:
        return f"{value / 1_000:g}k"
    return f"{value:g}"


def set_log_count_axis(ax: plt.Axes, values: pd.Series) -> None:
    positive = values.loc[values > 0].dropna()
    if positive.empty:
        return
    lower = 10 ** math.floor(math.log10(float(positive.min())))
    upper = 10 ** math.ceil(math.log10(float(positive.max())))
    if lower == upper:
        upper *= 10
    ax.set_ylim(lower, upper)
    ax.yaxis.set_major_locator(mticker.LogLocator(base=10, subs=(1.0, 2.0, 5.0), numticks=10))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(format_count_tick))
    ax.yaxis.set_minor_locator(mticker.NullLocator())


def set_linear_metric_axis(ax: plt.Axes, values: pd.Series, metric: str, crosstalk_cutoff: float) -> None:
    finite = values.dropna()
    finite = finite.loc[finite.map(math.isfinite)]
    if finite.empty:
        return
    data_min = float(finite.min())
    data_max = float(finite.max())
    target_max = max(data_max, crosstalk_cutoff) if metric == "Crosstalk_Ratio" else data_max
    span = target_max - data_min
    padding = max(span * 0.15, 0.02 if metric in BOUNDED_RATIO_METRICS else 1.0)
    lower = data_min - padding
    upper = target_max + padding
    if metric in BOUNDED_RATIO_METRICS:
        lower = max(0.0, lower)
        upper = min(1.0, upper)
        if upper - lower < 0.08:
            midpoint = (upper + lower) / 2
            lower = max(0.0, midpoint - 0.04)
            upper = min(1.0, midpoint + 0.04)
    ax.set_ylim(lower, upper)


def plot_metric_panel(
    ax: plt.Axes,
    data: pd.DataFrame,
    metric: str,
    condition_order: list[str],
    sample_colors: dict[str, str],
    crosstalk_cutoff: float,
) -> None:
    plot_data = select_metric_plot_data(data, metric, crosstalk_cutoff)
    grouped = [plot_data.loc[plot_data["condition"] == condition, metric].dropna().to_numpy() for condition in condition_order]
    positions = list(range(1, len(condition_order) + 1))
    nonempty = [(pos, values) for pos, values in zip(positions, grouped) if len(values)]
    if nonempty:
        box = ax.boxplot(
            [values for _, values in nonempty],
            positions=[pos for pos, _ in nonempty],
            widths=0.52,
            patch_artist=True,
            showfliers=False,
            medianprops={"color": "#222222", "linewidth": 1.3},
            boxprops={"facecolor": "#E6E6E6", "edgecolor": "#555555", "linewidth": 1.0},
            whiskerprops={"color": "#555555", "linewidth": 1.0},
            capprops={"color": "#555555", "linewidth": 1.0},
        )
        for patch in box["boxes"]:
            patch.set_alpha(0.7)

    for _, row in plot_data.dropna(subset=[metric]).iterrows():
        condition_index = condition_order.index(str(row["condition"]))
        fov_number = int(row["fov_number"]) if math.isfinite(float(row["fov_number"])) else 0
        jitter = ((fov_number % 17) - 8) / 80
        is_high_crosstalk = float(row["Crosstalk_Ratio"]) > crosstalk_cutoff
        marker = "x" if is_high_crosstalk else "o"
        color = "#B00020" if is_high_crosstalk and metric in RAW_CROSSTALK_METRICS else sample_colors[str(row["sample"])]
        ax.scatter(
            condition_index + 1 + jitter,
            float(row[metric]),
            s=36 if is_high_crosstalk and metric in RAW_CROSSTALK_METRICS else 14,
            marker=marker,
            color=color,
            alpha=0.85,
            linewidths=1.8 if is_high_crosstalk and metric in RAW_CROSSTALK_METRICS else 1.0,
            zorder=5 if is_high_crosstalk and metric in RAW_CROSSTALK_METRICS else 3,
        )

    ax.set_title(METRIC_LABELS[metric], fontsize=10, fontweight="bold")
    ax.set_xlabel("Condition")
    ax.set_ylabel(METRIC_LABELS[metric])
    ax.set_xticks(positions, condition_order, rotation=35, ha="right")
    ax.grid(axis="y", color="#D0D0D0", linewidth=0.6, alpha=0.7)
    if metric in LOG_SCALE_METRICS:
        ax.set_yscale("log")
        ax.set_ylabel(f"{METRIC_LABELS[metric]} (log scale)")
        set_log_count_axis(ax, plot_data[metric])
    else:
        set_linear_metric_axis(ax, plot_data[metric], metric, crosstalk_cutoff)
    if metric == "Crosstalk_Ratio":
        ax.axhline(crosstalk_cutoff, color="#B00020", linestyle="--", linewidth=1.1)


def plot_six_metric_summary(data: pd.DataFrame, output_dir: Path, crosstalk_cutoff: float, dpi: int) -> None:
    condition_order = list(dict.fromkeys(data["condition"].astype(str)))
    sample_colors = sample_color_map(data)
    fig, axes = plt.subplots(2, 3, figsize=(11.2, 8.0), constrained_layout=False)
    fig.suptitle("Decoding QC summary by inferred condition", fontsize=13, fontweight="bold", y=0.975)
    for ax, metric in zip(axes.flat, QC_METRICS):
        plot_metric_panel(ax, data, metric, condition_order, sample_colors, crosstalk_cutoff)
    add_shared_legend(fig, sample_colors)
    fig.subplots_adjust(left=0.07, right=0.985, top=0.91, bottom=0.15, wspace=0.32, hspace=0.46)
    save_figure(fig, output_dir, "decoding_qc_2x3_by_submit", dpi)


def dataframe_to_markdown(data: pd.DataFrame) -> str:
    if data.empty:
        return ""
    text_frame = data.copy()
    for column in text_frame.columns:
        if pd.api.types.is_float_dtype(text_frame[column]):
            text_frame[column] = text_frame[column].map(lambda value: f"{value:.6g}")
        else:
            text_frame[column] = text_frame[column].astype(str)

    columns = list(text_frame.columns)
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in text_frame.iterrows():
        values = [str(row[column]).replace("|", "\\|") for column in columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_markdown_report(data: pd.DataFrame, flagged: pd.DataFrame, output_dir: Path, crosstalk_cutoff: float) -> None:
    lines = [
        "# Generic Decoding QC Summary",
        "",
        f"- Total FOV rows: {len(data)}",
        f"- Submit count: {data['submit_name'].nunique()}",
        f"- Sample count: {data['sample'].nunique()}",
        f"- Condition count: {data['condition'].nunique()}",
        "- Visualized metrics: " + ", ".join(QC_METRICS),
        "- Condition inference: explicit filename tokens after sample are used when present; otherwise `submit00N -> group00`, `submit01N -> group01`, etc.",
        "- Y-axis rule: `SpotsFound_Total` and `StrictMatch_Count_Total` use log scale with 1/2/5 ticks; ratio/proportion metrics use data-adaptive linear ranges.",
        f"- High-crosstalk cutoff: Crosstalk_Ratio > {crosstalk_cutoff}",
        f"- High-crosstalk FOV rows: {len(flagged)}",
        "- Plot filtering: `SpotsFound_Total` and `Crosstalk_Ratio` show raw rows with high-crosstalk FOVs marked; strict-match and seqD/seqF metrics exclude high-crosstalk FOVs from box/scatter plotting.",
        "",
        "## Output Files",
        "",
        "- `decoding_qc_tidy.csv`: long-format metric table",
        "- `decoding_qc_submit_summary.csv`: per-condition/per-sample/per-submit metric summary",
        "- `decoding_qc_high_crosstalk_fovs.csv`: FOVs above the crosstalk cutoff",
        "- `decoding_qc_2x3_by_submit.png`: six-metric QC panel plot",
    ]
    if not flagged.empty:
        lines.extend(["", "## High-Crosstalk FOVs", ""])
        lines.append(dataframe_to_markdown(flagged))
    (output_dir / "decoding_qc_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    zz_decoding = args.zz_decoding or args.batch_root / "zz_decoding"
    output_dir = args.output_dir or zz_decoding / "plot_decoding_qc_generic"
    if output_dir.exists():
        raise QCError(f"Output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)

    configure_style()
    data = read_decoding_tables(zz_decoding)
    data["source_condition"] = data["condition"]
    if args.group_by == "sample":
        data["condition"] = data["sample"]
    data.to_csv(output_dir / "decoding_qc_all_fovs.csv", index=False)
    _, flagged = write_summary_tables(data, output_dir, args.crosstalk_cutoff)
    plot_six_metric_summary(data, output_dir, args.crosstalk_cutoff, args.dpi)
    write_markdown_report(data, flagged, output_dir, args.crosstalk_cutoff)

    print(f"输入: {zz_decoding}")
    print(f"输出: {output_dir}")
    print(f"FOV rows: {len(data)}")
    print(f"High-crosstalk rows: {len(flagged)}")


if __name__ == "__main__":
    main()
