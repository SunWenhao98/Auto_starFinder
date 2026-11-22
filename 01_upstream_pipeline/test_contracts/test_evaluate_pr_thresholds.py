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
        "decoding_rounds": 2, "voxel_size": [1, 1, 1],
        "quality_threshold": 0.5, "intensityThresh_PR": 999,
        "codebook_genes": ["A_rbRNA", "A_ntRNA", "B_rbRNA", "ZERO_ntRNA"],
        "codebook_sequences": ["11", "12", "21", "22"],
        "source_mat": "/read_only/source.mat", "source_allspots": "/read_only/allspots.csv",
    }
    (path / "metadata.json").write_text(json.dumps(metadata))
    return metadata


def legacy_evaluate(*args, **kwargs):
    return RUNNER.evaluate(*args, **kwargs, intensity_neighborhood="volume27")


@pytest.mark.parametrize("radius", [[1, 1, 0], [3, 3, 3]])
def test_legacy_non_cube27_window_cannot_be_relabelled_volume27(tmp_path, radius):
    evidence = tmp_path / "evidence"
    metadata = write_evidence(evidence)
    metadata["voxel_size"] = radius
    (evidence / "metadata.json").write_text(json.dumps(metadata))
    output = tmp_path / "results"
    with pytest.raises(ValueError):
        legacy_evaluate(evidence, output)
    assert not output.exists()


def rows(path):
    with path.open() as handle:
        return list(csv.DictReader(handle))


def test_six_thresholds_use_all_round_sums_and_preserve_records(tmp_path):
    evidence = tmp_path / "evidence"
    write_evidence(evidence)
    output = tmp_path / "results"
    legacy_evaluate(evidence, output, RUNNER.DEFAULT_VOLUME27_THRESHOLDS, chunk_size=1)
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
        legacy_evaluate(evidence, output, [0], chunk_size=2)
    assert marker.read_text() == "original"
    with h5py.File(evidence / "evidence.mat", "r+") as handle:
        handle["codebook_index"][0, 0] = 999
    with pytest.raises(ValueError):
        legacy_evaluate(evidence, tmp_path / "invalid", [0], chunk_size=2)


def test_zero_survivors_produce_complete_zero_counts(tmp_path):
    evidence = tmp_path / "evidence"
    write_evidence(evidence)
    output = tmp_path / "empty"
    legacy_evaluate(evidence, output, [1000], chunk_size=2)
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
    legacy_evaluate(evidence, output)
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
        legacy_evaluate(evidence, tmp_path / "invalid_empty")


def write_v2_evidence(path):
    metadata = write_evidence(path)
    plane_signal = np.array([36, 36, 20, 20, 72, 0, 180], dtype=np.float32)
    volume_signal = np.array([108, 100, 108, 100, 216, 0, 540], dtype=np.float32)
    sums = np.zeros((7, 2, 5, 3), dtype=np.float32)
    for neighborhood, factor in enumerate((1 / 9, 5 / 9, 1, 2, 3)):
        sums[:, :, neighborhood, 0] = plane_signal[:, None] * factor
    sums[:, :, 4, 0] = volume_signal[:, None]
    sums[1, :, 4, :] = [36, 100, 0]
    sums[2, :, 2, :] = [20, 20, 0]  # Positive tie, no forced channel winner.
    sums[2, :, 4, :] = [108, 20, 0]
    sums[3, :, 4, :] = [60, 100, 0]
    sums[:, :, 3, :] = (sums[:, :, 2, :] + sums[:, :, 4, :]) / 2
    sums[6, :, 0, :] = 0  # Dark center with bright in-plane neighbors.
    totals = sums.sum(axis=3, keepdims=True)
    l1 = np.divide(sums, totals, out=np.full_like(sums, np.nan), where=totals != 0)
    l2 = sums / (np.sqrt(np.square(sums).sum(axis=3, keepdims=True)) + 1e-6)
    counts = np.tile([1, 5, 9, 19, 27], (7, 1)).astype(np.uint8)
    counts[2] = [1, 4, 6, 14, 18]
    fields = {"neighborhood_channel_sum": sums.reshape(7, -1),
              "neighborhood_channel_l1": l1.reshape(7, -1),
              "neighborhood_channel_l2": l2.reshape(7, -1),
              "neighborhood_voxel_count": counts,
              "neighborhood_zero_signal": (totals[:, :, :, 0] == 0).reshape(7, -1),
              "pr_round_signal": sums[:, :, 2, :].max(axis=2)}
    with h5py.File(path / "evidence.mat", "r+") as handle:
        intensity = handle["intensity"][...].T.reshape(7, 2, 5)
        intensity[:, :, 1:4] = sums[:, :, 4, :]
        intensity[:, :, 4] = sums[:, :, 4, :].max(axis=2)
        handle["intensity"][...] = intensity.reshape(7, -1).T
        for key, value in fields.items():
            handle[key] = value.T
    metadata.update({"schema_version": 2, "gating_neighborhood": "plane9",
                     "nominal_gate_voxels": 9, "gating_threshold_scale": 0.8,
                     "neighborhood_order": list(RUNNER.NEIGHBORHOODS),
                     "neighborhood_nominal_voxels": list(RUNNER.NOMINAL_VOXELS),
                     "neighborhood_column_order": "round,neighborhood,channel"})
    (path / "metadata.json").write_text(json.dumps(metadata))
    return metadata


def test_plane9_default_gate_and_same_mu_groups_are_distinct_from_volume27(tmp_path):
    evidence = tmp_path / "evidence"
    write_v2_evidence(evidence)
    output = tmp_path / "plane9"
    RUNNER.evaluate(evidence, output, chunk_size=2)
    summary = {int(float(row["threshold"])): row for row in rows(output / "summary.csv")}
    assert sorted(summary) == [0, 36, 72, 108, 144, 180]
    assert int(summary[36]["n_intensity_pass_records"]) == 4
    assert int(summary[36]["n_quality_intensity_pass_records"]) == 3
    assert int(summary[36]["n_final_records"]) == 3
    assert int(summary[36]["n_final_unique_xyz"]) == 2
    assert float(summary[36]["conditional_decode_rate"]) == 1
    assert float(summary[36]["fixed_candidate_yield"]) == pytest.approx(3 / 7)
    assert summary[36]["intensity_neighborhood"] == "plane9"
    assert float(summary[36]["mu"]) == pytest.approx(5)
    assert [int(row["candidate_id"]) for row in rows(output / "PR036" / "goodPoints.csv")] == [1, 2, 7]
    assert {row["gene_symbol"]: int(row["gene_counts"])
            for row in rows(output / "PR036" / "gene_counts_totalRNA.csv")} == {"A": 2, "B": 1, "ZERO": 0}
    groups = {row["group"]: row for row in rows(output / "same_mu_neighborhood_groups.csv") if float(row["mu"]) == 5}
    assert {key: int(row["n_candidate_records"]) for key, row in groups.items()} == {
        "both_pass": 3, "plane9_only": 1, "volume27_only": 1, "neither_pass": 2}
    assert sum(int(row["n_decoded_records"]) for row in groups.values()) == 5
    assert all(float(row["plane9_threshold"]) == 36 and float(row["volume27_threshold"]) == 108
               for row in groups.values())
    volume_output = tmp_path / "volume27"
    RUNNER.evaluate(evidence, volume_output, chunk_size=2, intensity_neighborhood="volume27")
    volume_summary = {int(float(row["threshold"])): row for row in rows(volume_output / "summary.csv")}
    assert sorted(volume_summary) == [0, 108, 216, 324, 432, 540]
    assert [int(row["candidate_id"]) for row in rows(volume_output / "PR108" / "goodPoints.csv")] == [1, 3, 7]


def test_neighborhood_summary_preserves_zero_tie_and_agreement_semantics(tmp_path):
    evidence = tmp_path / "evidence"
    write_v2_evidence(evidence)
    output = tmp_path / "summary"
    RUNNER.evaluate(evidence, output, [36], chunk_size=1)
    diagnostics = {(int(row["round"]), row["neighborhood"]): row
                   for row in rows(output / "neighborhood_round_summary.csv")}
    assert len(diagnostics) == 10
    plane = diagnostics[1, "plane9"]
    assert int(plane["n_zero_signal_records"]) == 1
    assert int(plane["n_positive_tie_records"]) == 1
    assert int(plane["n_unique_winner_ch1"]) == 5
    assert int(plane["actual_voxels_min"]) == 6
    assert int(diagnostics[1, "center1"]["n_zero_signal_records"]) == 2
    assert float(plane["mean_top1_l1_nonzero"]) == pytest.approx(5.5 / 6)
    assert float(plane["mean_top1_minus_top2_l1_nonzero"]) == pytest.approx(5 / 6)
    channel = [row for row in rows(output / "neighborhood_channel_summary.csv")
               if row["round"] == "1" and row["neighborhood"] == "plane9"]
    assert sum(float(row["mean_l1_nonzero"]) for row in channel) == pytest.approx(1)
    assert float(channel[0]["mean_channel_sum"]) == pytest.approx(364 / 7)
    assert float(channel[0]["mean_l2"]) == pytest.approx((5 + 1 / np.sqrt(2)) / 7)
    agreement = rows(output / "plane9_volume27_round_comparison.csv")[0]
    assert int(agreement["n_both_unique_nonzero_winners"]) == 5
    assert int(agreement["n_agree_unique_winners"]) == 3
    assert int(agreement["n_disagree_unique_winners"]) == 2
    assert float(agreement["winner_agreement_rate"]) == pytest.approx(3 / 5)
    assert {float(row["baseline_threshold"]) for row in rows(output / "gene_count_correlations.csv")} == {0}
    pearson = next(row for row in rows(output / "gene_count_correlations.csv") if row["method"] == "pearson")
    assert float(pearson["correlation"]) == pytest.approx(
        np.corrcoef(np.log2([5, 2, 1]), np.log2([3, 2, 1]))[0, 1])


def test_v1_requires_explicit_volume27_and_cannot_be_reinterpreted_as_plane9(tmp_path):
    evidence = tmp_path / "evidence"
    write_evidence(evidence)
    with pytest.raises(ValueError, match="Schema v1"):
        RUNNER.evaluate(evidence, tmp_path / "wrong")
    assert not (tmp_path / "wrong").exists()
    RUNNER.evaluate(evidence, tmp_path / "legacy", [108], intensity_neighborhood="volume27")
    assert len(rows(tmp_path / "legacy" / "PR108" / "goodPoints.csv")) == 4


@pytest.mark.parametrize("corruption", ["dimensions", "order", "nan_nonzero", "pr_signal"])
def test_v2_rejects_ambiguous_or_corrupt_neighborhood_evidence(tmp_path, corruption):
    evidence = tmp_path / "evidence"
    metadata = write_v2_evidence(evidence)
    if corruption == "order":
        metadata["neighborhood_order"][0] = "plane9"
        (evidence / "metadata.json").write_text(json.dumps(metadata))
    else:
        with h5py.File(evidence / "evidence.mat", "r+") as handle:
            if corruption == "dimensions":
                del handle["neighborhood_channel_l2"]
                handle["neighborhood_channel_l2"] = np.zeros((29, 7))
            elif corruption == "nan_nonzero":
                handle["neighborhood_channel_l1"][0, 0] = np.nan
            else:
                handle["pr_round_signal"][0, 0] = 999
    with pytest.raises(ValueError):
        RUNNER.evaluate(evidence, tmp_path / "invalid")


@pytest.mark.parametrize("matlab_empty_encoding", [False, True])
def test_v2_empty_candidates_keep_complete_neighborhood_outputs(tmp_path, matlab_empty_encoding):
    evidence = tmp_path / "evidence"
    write_v2_evidence(evidence)
    with h5py.File(evidence / "evidence.mat", "r+") as handle:
        for key in list(handle):
            width = handle[key].shape[0]
            dtype = handle[key].dtype
            del handle[key]
            if matlab_empty_encoding:
                handle[key] = np.array([0, width], dtype=np.uint64)
                handle[key].attrs["MATLAB_empty"] = np.uint8(1)
            else:
                handle[key] = np.empty((width, 0), dtype=dtype)
    output = tmp_path / "empty"
    RUNNER.evaluate(evidence, output)
    assert len(rows(output / "neighborhood_channel_summary.csv")) == 30
    assert all(row["mean_channel_sum"] == "" for row in rows(output / "neighborhood_channel_summary.csv"))
    assert len(rows(output / "same_mu_neighborhood_groups.csv")) == 24
    assert all(int(row["n_candidate_records"]) == 0 for row in rows(output / "same_mu_neighborhood_groups.csv"))
