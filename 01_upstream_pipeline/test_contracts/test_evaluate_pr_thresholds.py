"""Synthetic evidence verifies threshold, identity, zero-gene and cache semantics."""

import csv
import importlib.util
import json
import os
from pathlib import Path

import h5py
import numpy as np
import pytest


RUNNER_PATH = Path(os.environ.get(
    "PR_EVALUATOR_PATH", Path(__file__).parents[1] / "01_spotDecoding" / "p05_evaluate_pr_thresholds.py"
))
SPEC = importlib.util.spec_from_file_location("evaluate_pr_thresholds", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def write_evidence(path):
    path.mkdir()
    # Rows 1 and 2 share XYZ; row 4 has no codebook hit; row 5 fails quality.
    # Row 7 passes every nonzero threshold but has a low center voxel.
    signals = np.array([[108, 216], [108, 216], [216, 108], [324, 324],
                        [540, 540], [0, 0], [540, 540]], dtype=float)
    intensity = np.zeros((7, 10))
    for round_index in range(2):
        intensity[:, round_index * 5] = 0.1
        intensity[:, round_index * 5 + 1] = signals[:, round_index]
        intensity[:, round_index * 5 + 2] = signals[:, round_index] / 2
        intensity[:, round_index * 5 + 4] = signals[:, round_index]
    spots = np.array([[1, 2, 3, 50, 0, 2], [1, 2, 3, 50, 0, 2],
                      [2, 2, 3, 70, 0, 1], [3, 2, 3, 70, 0, 1],
                      [4, 2, 3, 70, 0, 1], [5, 2, 3, 70, 0, 1],
                      [6, 2, 3, 70, 0, 3]], dtype=float)
    fields = {
        "candidate_id": np.arange(1, 8, dtype=np.uint64)[:, None],
        "spots": spots,
        "intensity": intensity,
        "scores": np.zeros((7, 2)),
        "color_index": np.ones((7, 2)),
        "quality_pass": np.array([1, 1, 1, 1, 0, 1, 1], dtype=bool)[:, None],
        # Deliberately all false: old extraction's PR mask must not prefilter.
        "intensity_pass": np.zeros((7, 1), dtype=bool),
        "codebook_index": np.array([1, 1, 2, 0, 3, 1, 3], dtype=np.uint32)[:, None],
        "neighbor_voxel_count": np.array([27, 27, 18, 27, 27, 27, 27])[:, None],
    }
    with h5py.File(path / "evidence.mat", "w") as handle:
        for key, value in fields.items():
            handle[key] = value.T
    metadata = {
        "schema_version": 1, "sample": "SYN", "position": "Position001",
        "decoding_rounds": 2, "voxel_size": [3, 3, 3],
        "quality_threshold": 0.5, "intensityThresh_PR": 999,
        "codebook_genes": ["A_rbRNA", "A_ntRNA", "B_rbRNA", "ZERO_ntRNA"],
        "codebook_sequences": ["11", "12", "21", "22"],
        "source_mat": "/read_only/source.mat", "source_allspots": "/read_only/allspots.csv",
    }
    (path / "metadata.json").write_text(json.dumps(metadata))
    return metadata


def rows(path):
    with path.open() as handle:
        return list(csv.DictReader(handle))


def test_six_thresholds_use_all_round_sums_and_preserve_records(tmp_path):
    evidence = tmp_path / "evidence"
    write_evidence(evidence)
    output = tmp_path / "results"
    RUNNER.evaluate(evidence, output, RUNNER.DEFAULT_THRESHOLDS, chunk_size=1)
    summary = {int(float(row["threshold"])): row for row in rows(output / "summary.csv")}
    assert sorted(summary) == [0, 108, 216, 324, 432, 540]
    assert int(summary[0]["n_candidate_records"]) == 7
    assert int(summary[0]["n_candidate_unique_xyz"]) == 6
    assert int(summary[0]["n_final_records"]) == 5
    assert int(summary[0]["n_final_unique_xyz"]) == 4
    assert int(summary[108]["n_intensity_pass_records"]) == 6
    assert int(summary[108]["n_quality_intensity_pass_records"]) == 5
    assert int(summary[108]["n_final_records"]) == 4
    assert float(summary[108]["conditional_decode_rate"]) == pytest.approx(4 / 5)
    assert float(summary[108]["fixed_candidate_yield"]) == pytest.approx(4 / 7)
    assert int(summary[216]["n_final_records"]) == 1
    assert int(summary[540]["n_final_records"]) == 1
    kept = rows(output / "PR108" / "goodPoints.csv")
    assert [int(row["candidate_id"]) for row in kept] == [1, 2, 3, 7]
    assert [row["Gene"] for row in kept] == ["A_rbRNA", "A_rbRNA", "A_ntRNA", "B_rbRNA"]
    assert [float(row["channel"]) for row in kept] == [2, 2, 1, 3]
    counts = {row["gene_symbol"]: int(row["gene_counts"]) for row in rows(output / "PR108" / "gene_counts_totalRNA.csv")}
    assert counts == {"A": 3, "B": 1, "ZERO": 0}
    per_round = rows(output / "PR216" / "round_diagnostics.csv")
    assert [int(row["failed_candidate_records"]) for row in per_round] == [3, 2]
    assert [int(row["only_failed_round_records"]) for row in per_round] == [2, 1]
    assert all(float(row["mean_center_max"]) == pytest.approx(0.1) for row in per_round)
    metadata = json.loads((output / "PR108" / "metadata.json").read_text())
    assert metadata["evidence_metadata"]["intensityThresh_PR"] == 999
    assert metadata["threshold"] == 108
    comparisons = rows(output / "gene_count_correlations.csv")
    assert {int(float(row["threshold"])) for row in comparisons} == {0, 108, 216, 324, 432, 540}
    assert all(int(row["n_genes"]) == 3 for row in comparisons)


def test_existing_output_and_invalid_evidence_fail(tmp_path):
    evidence = tmp_path / "evidence"
    write_evidence(evidence)
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("original")
    with pytest.raises(FileExistsError):
        RUNNER.evaluate(evidence, output, [0], chunk_size=2)
    assert marker.read_text() == "original"
    with h5py.File(evidence / "evidence.mat", "r+") as handle:
        handle["codebook_index"][0, 0] = 999
    with pytest.raises(ValueError):
        RUNNER.evaluate(evidence, tmp_path / "invalid", [0], chunk_size=2)


def test_zero_survivors_produce_complete_zero_counts(tmp_path):
    evidence = tmp_path / "evidence"
    write_evidence(evidence)
    output = tmp_path / "empty"
    RUNNER.evaluate(evidence, output, [1000], chunk_size=2)
    assert rows(output / "PR1000" / "goodPoints.csv") == []
    assert len(rows(output / "PR1000" / "gene_counts_by_state.csv")) == 4
    assert all(int(row["gene_counts"]) == 0 for row in rows(output / "PR1000" / "gene_counts_totalRNA.csv"))
    summary = rows(output / "summary.csv")[0]
    assert summary["conditional_decode_rate"] == ""
    assert float(summary["fixed_candidate_yield"]) == 0


@pytest.mark.parametrize("matlab_empty_encoding", [False, True])
def test_zero_candidates_preserve_matlab_empty_dimensions(tmp_path, matlab_empty_encoding):
    evidence = tmp_path / "evidence"
    write_evidence(evidence)
    with h5py.File(evidence / "evidence.mat", "r+") as handle:
        for key in list(handle):
            width = handle[key].shape[0]
            dtype = handle[key].dtype
            del handle[key]
            if matlab_empty_encoding:
                # MATLAB stores the original (N,width) dimensions, before transpose.
                handle[key] = np.array([0, width], dtype=np.uint64)
                handle[key].attrs["MATLAB_empty"] = np.uint8(1)
            else:
                handle[key] = np.empty((width, 0), dtype=dtype)
    output = tmp_path / "zero_candidates"
    RUNNER.evaluate(evidence, output)
    summary = rows(output / "summary.csv")
    assert len(summary) == 6
    assert all(int(row["n_candidate_records"]) == 0 for row in summary)
    assert all(int(row["n_candidate_unique_xyz"]) == 0 for row in summary)
    assert all(int(row["n_final_records"]) == 0 for row in summary)
    assert all(row["fixed_candidate_yield"] == "" for row in summary)
    assert rows(output / "PR000" / "goodPoints.csv") == []
    assert len(rows(output / "PR540" / "gene_counts_totalRNA.csv")) == 3
    assert all(int(row["gene_counts"]) == 0 for row in rows(output / "PR540" / "gene_counts_totalRNA.csv"))
    assert json.loads((output / "metadata.json").read_text())["status"] == "complete"


def test_dimension_vector_without_matlab_empty_attribute_is_invalid(tmp_path):
    evidence = tmp_path / "evidence"
    write_evidence(evidence)
    with h5py.File(evidence / "evidence.mat", "r+") as handle:
        del handle["candidate_id"]
        handle["candidate_id"] = np.array([0, 1], dtype=np.uint64)
    with pytest.raises(ValueError):
        RUNNER.evaluate(evidence, tmp_path / "invalid_empty")
