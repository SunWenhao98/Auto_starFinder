from __future__ import annotations

import argparse
from pathlib import Path


def convert_csv_to_h5ad(input_csv: Path, output_h5ad: Path) -> Path:
    """Convert one explicit CellReads CSV into the legacy dense AnnData layout."""
    import anndata as ad
    import pandas as pd

    if not input_csv.is_file():
        raise FileNotFoundError(input_csv)

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

    adata = ad.AnnData(X=total_counts.values)
    adata.obs_names = total_counts.index.astype(str)
    adata.var_names = total_counts.columns.astype(str)
    adata.layers["rbRNA"] = rb_counts.values
    adata.layers["ntRNA"] = nt_counts.values
    adata.uns["points"] = filtered
    adata.write_h5ad(output_h5ad)
    return output_h5ad


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert a CellReads CSV to dense AnnData")
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
