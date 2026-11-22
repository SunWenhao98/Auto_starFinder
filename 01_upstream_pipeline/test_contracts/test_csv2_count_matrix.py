from __future__ import annotations

from pathlib import Path
import sys

import anndata as ad
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "04_CellReadsIntegration"))

import csv2CountMatrix as count_matrix


def _write_reads_csv(path: Path) -> None:
    pd.DataFrame(
        {
            "gene_name": [
                "GeneA_rbRNA",
                "GeneA_ntRNA",
                "GeneB",
                "GeneB_ntRNA",
                "Ignored_rbRNA",
            ],
            "gene": ["GeneA", "GeneA", "GeneB", "GeneB", "Ignored"],
            "cell_barcode": [1, 1, 1, 2, 0],
            "column": [10, 11, 12, 20, 99],
            "row": [30, 31, 32, 40, 99],
        }
    ).to_csv(path, index=False)


def test_explicit_csv_produces_dense_expected_anndata(tmp_path: Path) -> None:
    input_csv = tmp_path / "reads.csv"
    output_h5ad = tmp_path / "result.h5ad"
    _write_reads_csv(input_csv)

    count_matrix.convert_csv_to_h5ad(input_csv, output_h5ad)

    result = ad.read_h5ad(output_h5ad)
    assert isinstance(result.X, np.ndarray)
    assert isinstance(result.layers["rbRNA"], np.ndarray)
    assert isinstance(result.layers["ntRNA"], np.ndarray)
    assert result.obs_names.tolist() == ["1", "2"]
    assert result.var_names.tolist() == ["GeneA", "GeneB"]
    np.testing.assert_array_equal(result.X, np.array([[2, 1], [0, 1]]))
    np.testing.assert_array_equal(result.layers["rbRNA"], np.array([[1, 0], [0, 0]]))
    np.testing.assert_array_equal(result.layers["ntRNA"], np.array([[1, 0], [0, 1]]))
    assert "points" not in result.uns
    points_path = tmp_path / "result_points.parquet"
    points = pd.read_parquet(points_path)
    expected = pd.read_csv(input_csv).rename(
        columns={"gene_name": "feature_name", "column": "x", "row": "y"}
    )
    expected = expected.loc[expected["cell_barcode"] != 0].reset_index(drop=True)
    pd.testing.assert_frame_equal(points, expected)


def test_missing_explicit_csv_produces_no_h5ad(tmp_path: Path) -> None:
    output_h5ad = tmp_path / "result.h5ad"

    with pytest.raises(FileNotFoundError):
        count_matrix.convert_csv_to_h5ad(tmp_path / "missing.csv", output_h5ad)

    assert not output_h5ad.exists()


@pytest.mark.parametrize("existing_output", ["result.h5ad", "result_points.parquet"])
def test_existing_output_is_not_overwritten(tmp_path: Path, existing_output: str) -> None:
    input_csv = tmp_path / "reads.csv"
    _write_reads_csv(input_csv)
    existing = tmp_path / existing_output
    original = b"already published result"
    existing.write_bytes(original)

    with pytest.raises(FileExistsError):
        count_matrix.convert_csv_to_h5ad(input_csv, tmp_path / "result.h5ad")

    assert existing.read_bytes() == original
    other = "result_points.parquet" if existing_output == "result.h5ad" else "result.h5ad"
    assert not (tmp_path / other).exists()
