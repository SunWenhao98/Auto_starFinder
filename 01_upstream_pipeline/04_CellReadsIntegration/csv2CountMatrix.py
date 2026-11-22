from __future__ import annotations

import argparse
from pathlib import Path

import anndata as ad
import pandas as pd


def convert_csv_to_h5ad(input_csv: Path, output_h5ad: Path) -> Path:
    """Write dense counts plus a sibling <h5ad stem>_points.parquet molecular table.

    Preserve the existing cell/gene axes and barcode != 0 molecular rows, but do
    not embed points in AnnData. Downstream 001/001b consume the counts alone.
    """
    points_parquet = output_h5ad.with_name(f"{output_h5ad.stem}_points.parquet")
    if output_h5ad.exists() or points_parquet.exists():
        raise FileExistsError(f"Refusing to overwrite output: {output_h5ad} or {points_parquet}")

    molecules = pd.read_csv(input_csv)
    molecules = molecules.rename(
        columns={"gene_name": "feature_name", "column": "x", "row": "y"}
    )
    filtered = molecules[molecules["cell_barcode"] != 0]

    total_counts = filtered.groupby(["cell_barcode", "gene"]).size().unstack(fill_value=0)
    rb_counts = (
        filtered[filtered["feature_name"].str.endswith("_rbRNA")]
        .groupby(["cell_barcode", "gene"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=total_counts.index, columns=total_counts.columns, fill_value=0)
    )
    nt_counts = (
        filtered[filtered["feature_name"].str.endswith("_ntRNA")]
        .groupby(["cell_barcode", "gene"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=total_counts.index, columns=total_counts.columns, fill_value=0)
    )

    print(f"Writing points Parquet: {points_parquet}", flush=True)
    filtered.to_parquet(points_parquet, index=False)
    del filtered, molecules
    print(f"Wrote points Parquet: {points_parquet}", flush=True)

    adata = ad.AnnData(X=total_counts.values)
    adata.obs_names = total_counts.index.astype(str)
    adata.var_names = total_counts.columns.astype(str)
    adata.layers["rbRNA"] = rb_counts.values
    adata.layers["ntRNA"] = nt_counts.values
    print(f"Writing dense AnnData without points: {output_h5ad}", flush=True)
    adata.write_h5ad(output_h5ad)
    return output_h5ad


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a CellReads CSV to dense AnnData and separate points Parquet",
        epilog="Points are saved beside --output_h5ad as <h5ad stem>_points.parquet.",
    )
    parser.add_argument("--input_csv", type=Path, required=True)
    parser.add_argument("--output_h5ad", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(f"Reading molecular file: {args.input_csv}")
    output_h5ad = convert_csv_to_h5ad(args.input_csv, args.output_h5ad)
    print(f"Wrote dense AnnData: {output_h5ad}")


if __name__ == "__main__":
    main()
