from pathlib import Path
import importlib.util

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "p05_extract_gene_counts.py"


def load_module():
    spec = importlib.util.spec_from_file_location("extract_gene_counts", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_gene_counts_merges_configured_suffixes(tmp_path):
    module = load_module()
    registration_dir = tmp_path / "02_registration001_GBM001"
    for pos, genes in {
        "Position001": ["MDK_rbRNA", "MDK_ntRNA", "HLA_B_rbRNA", "H1_0_ntRNA"],
        "Position002": ["MDK_rbRNA", "H3-3B_ntRNA", "BADLABEL_stateX"],
    }.items():
        pos_dir = registration_dir / pos
        pos_dir.mkdir(parents=True)
        pd.DataFrame({"Gene": genes}).to_csv(pos_dir / "goodPoints_max3d_0.2_tri.csv", index=False)

    result = module.extract_gene_counts(
        registration_dir=registration_dir,
        target_file="goodPoints_max3d_0.2_tri.csv",
        gene_column="Gene",
        suffix_regex=r"_(rbRNA|ntRNA)$",
        output_subdir="00_gene_counts",
        sample_id="GBM001",
    )

    counts = pd.read_csv(result.gene_counts_csv).set_index("gene_symbol")["gene_counts"].to_dict()
    assert counts["MDK"] == 3
    assert counts["HLA_B"] == 1
    assert counts["H1_0"] == 1
    assert counts["H3-3B"] == 1
    assert counts["BADLABEL_stateX"] == 1

    suffix_summary = pd.read_csv(result.suffix_summary_csv).set_index("suffix")["count"].to_dict()
    assert suffix_summary["rbRNA"] == 3
    assert suffix_summary["ntRNA"] == 3
    assert suffix_summary["NO_MATCH"] == 1


def test_extract_gene_counts_writes_position_summary(tmp_path):
    module = load_module()
    registration_dir = tmp_path / "02_registration001_GBM002"
    (registration_dir / "Position001").mkdir(parents=True)
    (registration_dir / "Position003").mkdir(parents=True)
    pd.DataFrame({"Gene": ["A_rbRNA", "B_ntRNA"]}).to_csv(
        registration_dir / "Position001" / "goodPoints.csv", index=False
    )
    pd.DataFrame({"Gene": ["A_ntRNA"]}).to_csv(
        registration_dir / "Position003" / "goodPoints.csv", index=False
    )

    result = module.extract_gene_counts(
        registration_dir=registration_dir,
        target_file="goodPoints.csv",
        gene_column="Gene",
        suffix_regex=r"_(rbRNA|ntRNA)$",
        output_subdir="00_gene_counts",
        sample_id="GBM002",
        start_pos=1,
        end_pos=3,
    )

    summary = pd.read_csv(result.position_summary_csv)
    assert summary["position"].tolist() == ["Position001", "Position003"]
    assert summary["status"].tolist() == ["processed", "processed"]
    assert summary["rows_used"].tolist() == [2, 1]
