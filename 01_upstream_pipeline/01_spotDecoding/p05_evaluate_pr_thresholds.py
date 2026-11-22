#!/usr/bin/env python3
"""Evaluate PR thresholds from immutable, unfiltered MATLAB v7.3 evidence.

All output counts retain candidate records. Unique XYZ counts are diagnostics;
they never collapse reads, gene counts, or the goodPoints export.
"""

import argparse
import csv
from contextlib import ExitStack
import json
from pathlib import Path
import re
import sqlite3

import h5py
import numpy as np
from scipy import stats


NEIGHBORHOODS = ("center1", "cross5", "plane9", "volume19", "volume27")
NOMINAL_VOXELS = (1, 5, 9, 19, 27)
DEFAULT_MU = (0, 5, 10, 15, 20, 25)
DEFAULT_THRESHOLDS = tuple(mu * 9 * 0.8 for mu in DEFAULT_MU)
DEFAULT_VOLUME27_THRESHOLDS = tuple(mu * 27 * 0.8 for mu in DEFAULT_MU)


def write_table(path, rows, fieldnames):
    with path.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def threshold_label(value):
    if float(value).is_integer():
        return f"PR{int(value):03d}"
    return "PR" + format(float(value), ".15g").replace(".", "p")


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def evidence_shape(dataset):
    """Return HDF5-oriented shape, including MATLAB's flagged empty matrices."""
    if bool(dataset.attrs.get("MATLAB_empty", 0)):
        # MATLAB_empty stores original MATLAB dimensions, before HDF5 transpose.
        matlab_shape = tuple(int(value) for value in dataset[...].ravel())
        if len(matlab_shape) != 2 or 0 not in matlab_shape or any(value < 0 for value in matlab_shape):
            raise ValueError(f"Invalid empty matrix dimensions for {dataset.name}")
        return matlab_shape[::-1]
    return dataset.shape


def evaluate(evidence_dir, output_dir, thresholds=None, chunk_size=65536,
             intensity_neighborhood="plane9"):
    evidence_dir = Path(evidence_dir).resolve()
    output_dir = Path(output_dir).absolute()
    if intensity_neighborhood not in ("plane9", "volume27"):
        raise ValueError("intensity_neighborhood must be plane9 or volume27")
    nominal_voxels = 9 if intensity_neighborhood == "plane9" else 27
    if thresholds is None:
        thresholds = [mu * nominal_voxels * 0.8 for mu in DEFAULT_MU]
    thresholds = sorted(set(float(value) for value in thresholds))
    mus = [value / (nominal_voxels * 0.8) for value in thresholds]
    if not thresholds or not all(np.isfinite(value) and value >= 0 for value in thresholds):
        raise ValueError("Thresholds must be finite nonnegative intensities")
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if len({threshold_label(value) for value in thresholds}) != len(thresholds):
        raise ValueError("Threshold output labels must be unique")

    with (evidence_dir / "metadata.json").open() as handle:
        metadata = json.load(handle)
    schema_version = metadata["schema_version"]
    if schema_version not in (1, 2):
        raise ValueError("Unsupported evidence schema")
    if schema_version == 1 and intensity_neighborhood != "volume27":
        raise ValueError("Schema v1 has no plane9 evidence; explicitly select volume27 for legacy replay")
    if schema_version == 1 and tuple(metadata["voxel_size"]) != (1, 1, 1):
        raise ValueError("Schema v1 volume27 replay requires the original 3-by-3-by-3 decoding window")
    if schema_version == 2:
        if (tuple(metadata["neighborhood_order"]) != NEIGHBORHOODS
                or metadata["neighborhood_column_order"] != "round,neighborhood,channel"
                or tuple(metadata["neighborhood_nominal_voxels"]) != NOMINAL_VOXELS):
            raise ValueError("Unsupported neighborhood ordering or nominal voxel counts")
    rounds = int(metadata["decoding_rounds"])
    genes = metadata["codebook_genes"]
    if rounds < 1 or not isinstance(genes, list) or not genes:
        raise ValueError("Evidence needs decoding rounds and a gene codebook")
    if any(not isinstance(gene, str) or not gene.strip() for gene in genes):
        raise ValueError("Codebook genes must be nonempty strings")
    if len(metadata["codebook_sequences"]) != len(genes):
        raise ValueError("Codebook gene and sequence indices must align")
    state_genes = list(dict.fromkeys(genes))
    total_genes = list(dict.fromkeys(re.sub(r"_(rbRNA|ntRNA)$", "", gene) for gene in genes))
    state_lookup = {gene: index for index, gene in enumerate(state_genes)}
    total_lookup = {gene: index for index, gene in enumerate(total_genes)}
    code_to_state = np.array([state_lookup[gene] for gene in genes])
    code_to_total = np.array([total_lookup[re.sub(r"_(rbRNA|ntRNA)$", "", gene)] for gene in genes])

    # Read MATLAB arrays with transposed HDF5 dimensions, one candidate block at a time.
    with ExitStack() as stack:
        evidence = stack.enter_context(h5py.File(evidence_dir / "evidence.mat", "r"))
        candidate_shape = evidence_shape(evidence["candidate_id"])
        if len(candidate_shape) != 2 or candidate_shape[0] != 1:
            raise ValueError("candidate_id must represent an N-by-1 MATLAB array")
        n_candidates = candidate_shape[1]
        expected_widths = {"candidate_id": 1, "spots": 6, "intensity": 5 * rounds,
                           "scores": rounds, "color_index": rounds, "quality_pass": 1,
                           "intensity_pass": 1, "codebook_index": 1, "neighbor_voxel_count": 1}
        if schema_version == 2:
            expected_widths.update({"neighborhood_channel_sum": rounds * 5 * 3,
                                    "neighborhood_channel_l1": rounds * 5 * 3,
                                    "neighborhood_channel_l2": rounds * 5 * 3,
                                    "neighborhood_voxel_count": 5,
                                    "neighborhood_zero_signal": rounds * 5,
                                    "pr_round_signal": rounds})
        for key, width in expected_widths.items():
            shape = evidence_shape(evidence[key])
            if shape != (width, n_candidates):
                raise ValueError(f"Invalid MATLAB evidence dimensions for {key}: {shape}")

        # Existing directories are never reused, including empty directories.
        output_dir.mkdir(parents=True, exist_ok=False)
        print(f"START: {metadata['sample']} {metadata['position']} | candidates={n_candidates}", flush=True)
        database_path = output_dir / "unique_xyz.sqlite3"
        unique = sqlite3.connect(database_path)
        stack.callback(unique.close)
        unique.execute("PRAGMA temp_store=FILE")
        unique.execute("PRAGMA cache_size=-8192")
        unique.execute("CREATE TABLE xyz (x REAL, y REAL, z REAL, signal REAL, quality_signal REAL, decoded_signal REAL, PRIMARY KEY(x,y,z)) WITHOUT ROWID")
        merge_xyz = """INSERT INTO xyz VALUES (?,?,?,?,?,?)
            ON CONFLICT(x,y,z) DO UPDATE SET
            signal=max(signal,excluded.signal),
            quality_signal=max(quality_signal,excluded.quality_signal),
            decoded_signal=max(decoded_signal,excluded.decoded_signal)"""

        count_arrays = [np.zeros(len(genes), dtype=np.int64) for _ in thresholds]
        stage_counts = np.zeros((len(thresholds), 3), dtype=np.int64)
        failed_round_counts = np.zeros((len(thresholds), rounds), dtype=np.int64)
        quality_failed_round_counts = np.zeros_like(failed_round_counts)
        only_failed_round_counts = np.zeros_like(failed_round_counts)
        failure_distributions = np.zeros((len(thresholds), rounds + 1), dtype=np.int64)
        limiting_round_counts = np.zeros(rounds, dtype=np.int64)
        center_sums = np.zeros(rounds)
        volume_sums = np.zeros(rounds)
        mean_voxel_sums = np.zeros(rounds)
        available_neighborhoods = NEIGHBORHOODS if schema_version == 2 else ("volume27",)
        n_neighborhoods = len(available_neighborhoods)
        sum_totals = np.zeros((rounds, n_neighborhoods, 3))
        l1_totals = np.zeros_like(sum_totals)
        l2_totals = np.zeros_like(sum_totals)
        nonzero_counts = np.zeros((rounds, n_neighborhoods), dtype=np.int64)
        zero_counts = np.zeros_like(nonzero_counts)
        tie_counts = np.zeros_like(nonzero_counts)
        winner_counts = np.zeros((rounds, n_neighborhoods, 3), dtype=np.int64)
        top1_totals = np.zeros((rounds, n_neighborhoods))
        gap_totals = np.zeros_like(top1_totals)
        neighborhood_voxel_min = np.full(n_neighborhoods, np.inf)
        neighborhood_voxel_max = np.zeros(n_neighborhoods)
        agreement_counts = np.zeros((rounds, 3), dtype=np.int64)
        outer_layer_sums = np.zeros((rounds, 3))
        same_mu_counts = np.zeros((len(thresholds), 4, 3), dtype=np.int64)
        baseline_code_counts = np.zeros(len(genes), dtype=np.int64)
        extraction_intensity_count = 0
        quality_count = 0
        matched_count = 0
        previous_candidate_id = 0
        neighbor_min = None
        neighbor_max = None
        writers = []
        for threshold in thresholds:
            folder = output_dir / threshold_label(threshold)
            folder.mkdir()
            handle = stack.enter_context((folder / "goodPoints.csv").open("x", newline=""))
            writer = csv.writer(handle)
            writer.writerow(["candidate_id", "x", "y", "z", "intensity", "channel", "Gene"])
            writers.append(writer)

        for start in range(0, n_candidates, chunk_size):
            end = min(start + chunk_size, n_candidates)
            candidate_ids = evidence["candidate_id"][0, start:end]
            spots = evidence["spots"][:, start:end].T
            intensities = evidence["intensity"][:, start:end].T.reshape(-1, rounds, 5)
            quality = evidence["quality_pass"][0, start:end].astype(bool)
            code_indices = evidence["codebook_index"][0, start:end].astype(np.int64)
            neighbors = evidence["neighbor_voxel_count"][0, start:end]
            if candidate_ids[0] <= previous_candidate_id or np.any(candidate_ids[1:] <= candidate_ids[:-1]):
                raise ValueError("candidate_id must preserve positive, strictly increasing source row identities")
            previous_candidate_id = int(candidate_ids[-1])
            if np.any(code_indices < 0) or np.any(code_indices > len(genes)):
                raise ValueError("codebook_index outside the declared 1-based codebook")
            if not np.all(np.isfinite(spots)) or not np.all(np.isfinite(intensities)):
                raise ValueError("Coordinates and raw intensities must be finite")
            if not np.all(np.isfinite(neighbors)) or np.any(neighbors <= 0):
                raise ValueError("neighbor_voxel_count must be positive and finite")

            if schema_version == 2:
                channel_sums = evidence["neighborhood_channel_sum"][:, start:end].T.reshape(-1, rounds, 5, 3)
                l1 = evidence["neighborhood_channel_l1"][:, start:end].T.reshape(-1, rounds, 5, 3)
                l2 = evidence["neighborhood_channel_l2"][:, start:end].T.reshape(-1, rounds, 5, 3)
                voxel_counts = evidence["neighborhood_voxel_count"][:, start:end].T
                zero_signal = evidence["neighborhood_zero_signal"][:, start:end].T.reshape(-1, rounds, 5).astype(bool)
                if (not np.all(np.isfinite(channel_sums)) or np.any(channel_sums < 0)
                        or not np.all(np.isfinite(l2))
                        or np.any(~np.isfinite(l1) & ~zero_signal[:, :, :, None])
                        or np.any(np.isinf(l1))
                        or not np.all(np.isnan(l1[zero_signal]))
                        or not np.array_equal(zero_signal, np.all(channel_sums == 0, axis=3))):
                    raise ValueError("Neighborhood ratios must be finite except L1 NaN at zero-signal neighborhoods")
                if (np.any(voxel_counts <= 0)
                        or np.any(voxel_counts > np.array(NOMINAL_VOXELS)[None, :])):
                    raise ValueError("Invalid actual neighborhood voxel counts")
                plane9_signal = np.max(channel_sums[:, :, 2, :], axis=2)
                volume27_signal = np.max(channel_sums[:, :, 4, :], axis=2)
                cached_pr_signal = evidence["pr_round_signal"][:, start:end].T
                if not np.array_equal(cached_pr_signal, plane9_signal):
                    raise ValueError("pr_round_signal must equal the plane9 maximum channel sum")
                round_signal = plane9_signal if intensity_neighborhood == "plane9" else volume27_signal
                selected_neighbors = voxel_counts[:, 2 if intensity_neighborhood == "plane9" else 4]
                outer_layer_sums += (channel_sums[:, :, 4, :] - channel_sums[:, :, 2, :]).sum(axis=0)
            else:
                channel_sums = intensities[:, :, None, 1:4]
                totals = channel_sums.sum(axis=3, keepdims=True)
                zero_signal = totals[:, :, :, 0] == 0
                l1 = np.divide(channel_sums, totals, out=np.full_like(channel_sums, np.nan), where=totals != 0)
                l2 = channel_sums / (np.sqrt(np.square(channel_sums).sum(axis=3, keepdims=True)) + 1e-6)
                voxel_counts = neighbors[:, None]
                round_signal = np.max(channel_sums[:, :, 0, :], axis=2)
                selected_neighbors = neighbors
            if np.any(channel_sums < 0):
                raise ValueError("Raw neighborhood sums must be nonnegative")
            channel_max = channel_sums.max(axis=3)
            winner_mask = channel_sums == channel_max[:, :, :, None]
            unique_winner = (winner_mask.sum(axis=3) == 1) & ~zero_signal
            winners = np.argmax(channel_sums, axis=3)
            sum_totals += channel_sums.sum(axis=0, dtype=np.float64)
            l1_totals += np.where(zero_signal[:, :, :, None], 0, l1).sum(axis=0, dtype=np.float64)
            l2_totals += l2.sum(axis=0, dtype=np.float64)
            nonzero_counts += (~zero_signal).sum(axis=0)
            zero_counts += zero_signal.sum(axis=0)
            tie_counts += (~zero_signal & ~unique_winner).sum(axis=0)
            for channel in range(3):
                winner_counts[:, :, channel] += (unique_winner & (winners == channel)).sum(axis=0)
            sorted_l1 = np.sort(np.where(zero_signal[:, :, :, None], 0, l1), axis=3)
            top1_totals += sorted_l1[:, :, :, -1].sum(axis=0, dtype=np.float64)
            gap_totals += (sorted_l1[:, :, :, -1] - sorted_l1[:, :, :, -2]).sum(axis=0, dtype=np.float64)
            neighborhood_voxel_min = np.minimum(neighborhood_voxel_min, voxel_counts.min(axis=0))
            neighborhood_voxel_max = np.maximum(neighborhood_voxel_max, voxel_counts.max(axis=0))
            if schema_version == 2:
                both_unique = unique_winner[:, :, 2] & unique_winner[:, :, 4]
                agree = both_unique & (winners[:, :, 2] == winners[:, :, 4])
                agreement_counts += np.stack((both_unique.sum(axis=0), agree.sum(axis=0),
                                              (both_unique & ~agree).sum(axis=0)), axis=1)
            min_signal = np.min(round_signal, axis=1)
            matched = code_indices > 0
            quality_count += int(quality.sum())
            matched_count += int(matched.sum())
            baseline_code_counts += np.bincount(code_indices[quality & matched] - 1, minlength=len(genes))
            extraction_intensity_count += int(evidence["intensity_pass"][0, start:end].astype(bool).sum())
            center_sums += intensities[:, :, 0].sum(axis=0)
            volume_sums += round_signal.sum(axis=0)
            mean_voxel_sums += (round_signal / selected_neighbors[:, None]).sum(axis=0)
            limiting_round_counts += (round_signal == min_signal[:, None]).sum(axis=0)
            neighbor_min = min(float(selected_neighbors.min()), neighbor_min) if neighbor_min is not None else float(selected_neighbors.min())
            neighbor_max = max(float(selected_neighbors.max()), neighbor_max) if neighbor_max is not None else float(selected_neighbors.max())
            quality_signal = np.where(quality, min_signal, -np.inf)
            decoded_signal = np.where(quality & matched, min_signal, -np.inf)
            unique.executemany(merge_xyz, ((float(point[0]), float(point[1]), float(point[2]),
                                         float(signal), float(q_signal), float(d_signal))
                                        for point, signal, q_signal, d_signal in
                                        zip(spots, min_signal, quality_signal, decoded_signal)))
            unique.commit()

            for index, (threshold, writer) in enumerate(zip(thresholds, writers)):
                failed = round_signal < threshold
                n_failed = failed.sum(axis=1)
                passes = n_failed == 0
                quality_passes = passes & quality
                final = quality_passes & matched
                stage_counts[index] += [int(passes.sum()), int(quality_passes.sum()), int(final.sum())]
                failed_round_counts[index] += failed.sum(axis=0)
                quality_failed_round_counts[index] += (failed & quality[:, None]).sum(axis=0)
                only_failed_round_counts[index] += (failed & (n_failed == 1)[:, None]).sum(axis=0)
                failure_distributions[index] += np.bincount(n_failed, minlength=rounds + 1)
                chosen = np.flatnonzero(final)
                count_arrays[index] += np.bincount(code_indices[chosen] - 1, minlength=len(genes))
                writer.writerows((int(candidate_ids[row]), *spots[row, :4].tolist(),
                                  float(spots[row, 5]), genes[code_indices[row] - 1]) for row in chosen)
                if schema_version == 2:
                    pass9 = np.all(plane9_signal >= mus[index] * 9 * 0.8, axis=1)
                    pass27 = np.all(volume27_signal >= mus[index] * 27 * 0.8, axis=1)
                    groups = (pass9 & pass27, pass9 & ~pass27, ~pass9 & pass27, ~pass9 & ~pass27)
                    for group_index, group in enumerate(groups):
                        same_mu_counts[index, group_index] += [int(group.sum()), int((group & quality).sum()),
                                                               int((group & quality & matched).sum())]
            print(f"READ: {end}/{n_candidates} candidate records", flush=True)

        n_unique = unique.execute("SELECT count(*) FROM xyz").fetchone()[0]
        summaries = []
        total_vectors = []
        common_metadata = {
            "schema_version": 2, "evidence_dir": str(evidence_dir),
            "source_evidence_mat": str(evidence_dir / "evidence.mat"),
            "source_evidence_metadata": str(evidence_dir / "metadata.json"),
            "evidence_metadata": metadata,
            "intensity_neighborhood": intensity_neighborhood,
            "nominal_voxels": nominal_voxels, "threshold_scale": 0.8,
            "intensity_criterion": "all rounds: selected-neighborhood max(ch1sum, ch2sum, ch3sum) >= threshold",
            "quality_criterion": "cache quality_pass; scores are not reinterpreted",
            "final_criterion": "intensity_pass & quality_pass & (codebook_index > 0)",
            "extraction_intensity_pass_used_as_filter": False,
            "record_policy": "preserve every candidate; uniqueXYZ diagnostics do not deduplicate counts",
            "gene_universe": "fixed codebook labels; totalRNA strips only terminal _rbRNA/_ntRNA",
            "neighbor_voxel_count_min": neighbor_min, "neighbor_voxel_count_max": neighbor_max,
            "center_intensity_usage": "diagnostic only",
            "minimum_round_ties": "each tied round counted, so totals may exceed candidate count",
            "neighborhood_statistics_available": list(available_neighborhoods),
            "ratio_summary_population": "all candidate records; L1/top1/gap means exclude zero signal; S/L2 means include zero signal",
            "winner_policy": "zero signal and positive ties reported separately; winner agreement requires both unique nonzero winners",
            "comparison_policy": "plane9 and volume27 at the same mu; fixed quality_pass and codebook_index",
            "same_mu_decoded_records_definition": "within each candidate group, quality_pass & (codebook_index > 0), before either intensity gate",
        }
        for index, threshold in enumerate(thresholds):
            folder = output_dir / threshold_label(threshold)
            unique_counts = unique.execute(
                "SELECT sum(signal>=?),sum(quality_signal>=?),sum(decoded_signal>=?) FROM xyz",
                (threshold, threshold, threshold)).fetchone()
            unique_counts = [int(value or 0) for value in unique_counts]
            intensity_n, quality_intensity_n, final_n = (int(value) for value in stage_counts[index])
            summary = {
                "sample": metadata["sample"], "position": metadata["position"], "threshold": threshold,
                "intensity_neighborhood": intensity_neighborhood, "nominal_voxels": nominal_voxels,
                "mu": mus[index],
                "n_candidate_records": n_candidates, "n_candidate_unique_xyz": n_unique,
                "n_quality_pass_records": quality_count, "n_codebook_matched_records": matched_count,
                "n_extraction_intensity_pass_records": extraction_intensity_count,
                "n_intensity_pass_records": intensity_n, "n_intensity_pass_unique_xyz": unique_counts[0],
                "n_quality_intensity_pass_records": quality_intensity_n,
                "n_quality_intensity_pass_unique_xyz": unique_counts[1],
                "n_final_records": final_n, "n_final_unique_xyz": unique_counts[2],
                "conditional_decode_rate": ratio(final_n, quality_intensity_n),
                "fixed_candidate_yield": ratio(final_n, n_candidates),
                "conditional_decode_rate_unique_xyz": ratio(unique_counts[2], unique_counts[1]),
                "fixed_candidate_yield_unique_xyz": ratio(unique_counts[2], n_unique),
            }
            summaries.append(summary)
            state_counts = np.zeros(len(state_genes), dtype=np.int64)
            total_counts = np.zeros(len(total_genes), dtype=np.int64)
            np.add.at(state_counts, code_to_state, count_arrays[index])
            np.add.at(total_counts, code_to_total, count_arrays[index])
            total_vectors.append(total_counts)
            write_table(folder / "gene_counts_by_state.csv",
                        ({"Gene": gene, "gene_counts": int(count)} for gene, count in zip(state_genes, state_counts)),
                        ["Gene", "gene_counts"])
            write_table(folder / "gene_counts_totalRNA.csv",
                        ({"gene_symbol": gene, "gene_counts": int(count)} for gene, count in zip(total_genes, total_counts)),
                        ["gene_symbol", "gene_counts"])
            round_rows = [{"round": number + 1,
                           "failed_candidate_records": int(failed_round_counts[index, number]),
                           "failed_quality_pass_records": int(quality_failed_round_counts[index, number]),
                           "only_failed_round_records": int(only_failed_round_counts[index, number]),
                           "minimum_signal_round_records_ties_included": int(limiting_round_counts[number]),
                           "mean_center_max": ratio(float(center_sums[number]), n_candidates),
                           "mean_max_channel_sum": ratio(float(volume_sums[number]), n_candidates),
                           "mean_max_channel_voxel_mean": ratio(float(mean_voxel_sums[number]), n_candidates)}
                          for number in range(rounds)]
            write_table(folder / "round_diagnostics.csv", round_rows, list(round_rows[0]))
            write_table(folder / "failed_round_count_distribution.csv",
                        ({"n_failed_rounds": number, "candidate_records": int(value)}
                         for number, value in enumerate(failure_distributions[index])),
                        ["n_failed_rounds", "candidate_records"])
            write_json(folder / "summary.json", summary)
            write_json(folder / "metadata.json", {**common_metadata, "threshold": threshold, "mu": mus[index]})
        write_table(output_dir / "summary.csv", summaries, list(summaries[0]))

        channel_rows = []
        neighborhood_rows = []
        for round_index in range(rounds):
            for neighborhood_index, neighborhood in enumerate(available_neighborhoods):
                positive_n = int(nonzero_counts[round_index, neighborhood_index])
                for channel in range(3):
                    channel_rows.append({
                        "round": round_index + 1, "neighborhood": neighborhood, "channel": channel + 1,
                        "n_candidate_records": n_candidates, "n_nonzero_records": positive_n,
                        "mean_channel_sum": ratio(float(sum_totals[round_index, neighborhood_index, channel]), n_candidates),
                        "mean_l1_nonzero": ratio(float(l1_totals[round_index, neighborhood_index, channel]), positive_n),
                        "mean_l2": ratio(float(l2_totals[round_index, neighborhood_index, channel]), n_candidates),
                    })
                neighborhood_rows.append({
                    "round": round_index + 1, "neighborhood": neighborhood,
                    "nominal_voxels": NOMINAL_VOXELS[NEIGHBORHOODS.index(neighborhood)],
                    "actual_voxels_min": int(neighborhood_voxel_min[neighborhood_index]) if n_candidates else None,
                    "actual_voxels_max": int(neighborhood_voxel_max[neighborhood_index]) if n_candidates else None,
                    "n_candidate_records": n_candidates, "n_nonzero_records": positive_n,
                    "n_zero_signal_records": int(zero_counts[round_index, neighborhood_index]),
                    "n_positive_tie_records": int(tie_counts[round_index, neighborhood_index]),
                    "n_unique_winner_ch1": int(winner_counts[round_index, neighborhood_index, 0]),
                    "n_unique_winner_ch2": int(winner_counts[round_index, neighborhood_index, 1]),
                    "n_unique_winner_ch3": int(winner_counts[round_index, neighborhood_index, 2]),
                    "mean_top1_l1_nonzero": ratio(float(top1_totals[round_index, neighborhood_index]), positive_n),
                    "mean_top1_minus_top2_l1_nonzero": ratio(float(gap_totals[round_index, neighborhood_index]), positive_n),
                })
        write_table(output_dir / "neighborhood_channel_summary.csv", channel_rows, list(channel_rows[0]))
        write_table(output_dir / "neighborhood_round_summary.csv", neighborhood_rows, list(neighborhood_rows[0]))
        if schema_version == 2:
            agreement_rows = [{
                "round": number + 1, "n_candidate_records": n_candidates,
                "n_both_unique_nonzero_winners": int(agreement_counts[number, 0]),
                "n_agree_unique_winners": int(agreement_counts[number, 1]),
                "n_disagree_unique_winners": int(agreement_counts[number, 2]),
                "winner_agreement_rate": ratio(int(agreement_counts[number, 1]), int(agreement_counts[number, 0])),
                **{f"mean_volume27_minus_plane9_ch{channel + 1}_sum": ratio(float(outer_layer_sums[number, channel]), n_candidates)
                   for channel in range(3)},
            } for number in range(rounds)]
            write_table(output_dir / "plane9_volume27_round_comparison.csv", agreement_rows, list(agreement_rows[0]))
            same_mu_rows = [{
                "mu": mu, "plane9_threshold": mu * 9 * 0.8, "volume27_threshold": mu * 27 * 0.8,
                "group": group, "n_candidate_records": int(same_mu_counts[index, group_index, 0]),
                "n_quality_pass_records": int(same_mu_counts[index, group_index, 1]),
                "n_decoded_records": int(same_mu_counts[index, group_index, 2]),
            } for index, mu in enumerate(mus)
                for group_index, group in enumerate(("both_pass", "plane9_only", "volume27_only", "neither_pass"))]
            write_table(output_dir / "same_mu_neighborhood_groups.csv", same_mu_rows, list(same_mu_rows[0]))

        comparisons = []
        baseline_total_counts = np.zeros(len(total_genes), dtype=np.int64)
        np.add.at(baseline_total_counts, code_to_total, baseline_code_counts)
        baseline = np.log2(baseline_total_counts + 1)
        for threshold, counts in zip(thresholds, total_vectors):
            values = np.log2(counts + 1)
            variable = len(values) >= 2 and np.ptp(baseline) > 0 and np.ptp(values) > 0
            for method, function in (("pearson", stats.pearsonr), ("spearman", stats.spearmanr)):
                correlation = float(function(baseline, values).statistic) if variable else None
                comparisons.append({"baseline_threshold": 0, "threshold": threshold,
                                    "intensity_neighborhood": intensity_neighborhood, "mu": threshold / (nominal_voxels * 0.8),
                                    "method": method, "n_genes": len(total_genes), "correlation": correlation,
                                    "transform": "log2(totalRNA_count+1)",
                                    "scope": "fixed codebook totalRNA genes including zeros"})
        write_table(output_dir / "gene_count_correlations.csv", comparisons, list(comparisons[0]))
        write_json(output_dir / "metadata.json", {**common_metadata, "thresholds": thresholds,
                                                 "chunk_size": chunk_size, "status": "complete"})
    # This database only supported exact duplicate-coordinate diagnostics.
    database_path.unlink()
    print(f"STATUS: SUCCESS | output_dir={output_dir}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence_dir", required=True, type=Path)
    parser.add_argument("--output_dir", required=True, type=Path)
    parser.add_argument("--thresholds", nargs="+", type=float, default=None,
                        help="Actual channel-sum thresholds; omitted uses mu=0/5/10/15/20/25 for the selected neighborhood")
    parser.add_argument("--intensity_neighborhood", choices=("plane9", "volume27"), default="plane9")
    parser.add_argument("--chunk_size", type=int, default=65536)
    args = parser.parse_args()
    evaluate(args.evidence_dir, args.output_dir, args.thresholds, args.chunk_size, args.intensity_neighborhood)
