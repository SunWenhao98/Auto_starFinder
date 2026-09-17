#!/usr/bin/env python3
from __future__ import annotations

import argparse
import configparser
import json
import os
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


ArgMap = tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class SampleMetadata:
    project_name: str
    fov_count: int
    position_offset: int


@dataclass(frozen=True, slots=True)
class LoadedConfig:
    parser: configparser.ConfigParser
    section_names: tuple[str, ...]
    samples_by_name: Mapping[str, SampleMetadata]
    sample_by_section: Mapping[str, SampleMetadata]


@dataclass(frozen=True)
class StepSpec:
    run_key: str
    wrapper_key: str
    job_name: str
    submission_type: str
    prefix: str
    log_dir: str
    args: ArgMap
    log_root_key: str = "decode_log"
    script_dir_from_wrapper: bool = False
    sample_position_offset_flag: str | None = None


COMMON_ARGS: ArgMap = (
    ("project_root", "--project_root"),
    ("project_name", "--project_name"),
    ("regDir_suffix", "--reg_dir_suffix"),
)
IMAGE_ARGS: ArgMap = (
    ("image_width", "--image_width"),
    ("image_depth", "--image_depth"),
    ("ref_round", "--ref_round"),
    ("channel_num", "--channel_num"),
    ("round_num", "--round_num"),
)
CORE_MATLAB_ARG: ArgMap = (("core_matlab_dir", "--core_matlab_dir"),)
CONDA_SH_ARG: ArgMap = (("conda_sh", "--conda_sh"),)
FIJI_DIR_ARG: ArgMap = (("fiji_dir", "--fiji_dir"),)


STEP_ORDER = (
    "gr", "lr_subtile", "lr_fov", "ls", "gspf", "grd", "egc", "atlas", "pairwise",
    "dapi_cp", "clumap", "rna_restore", "nuclei_reg", "prepare_layout",
    "prepare_tile_config", "fiji_stitch_initial", "ashlar_stitch_initial",
    "prepare_moveimages", "fiji_stitch_mosaic", "ashlar_stitch_mosaic",
    "pyreg", "matreg", "reg_compare", "transform_apply",
)
STEP_SPECS = {
    "gr": StepSpec("run_global_reg", "script_global_reg", "GR", "array", "gr", "logs001_global_registration", CORE_MATLAB_ARG + COMMON_ARGS + (
        ("gr_norm_mode", "--norm_mode"),
        ("gr_percen_max", "--percen_max"),
        ("gr_hist_round", "--hist_round"),
        ("gr_hist_channel", "--hist_channel"),
        ("gr_radius", "--radius"),
        ("gr_mode", "--mode"),
        ("gr_align_basis", "--align_basis"),
    ) + IMAGE_ARGS + (
        ("gr_offset", "--offset"),
        ("gr_erode", "--erode"),
        ("gr_transform", "--transform"),
        ("gr_input_format", "--input_format"),
        ("gr_norm_out_format", "--norm_out_format"),
    )),
    "lr_subtile": StepSpec(
        "run_local_reg_subtile", "script_local_reg_subtile", "LR_subtile", "array",
        "lr_subtile", "logs002_local_registration", CORE_MATLAB_ARG + COMMON_ARGS + (
            ("lr_subtile_align_basis", "--align_basis"),
        ) + IMAGE_ARGS + (("lr_subtile_offset", "--offset"),),
    ),
    "lr_fov": StepSpec(
        "run_local_reg_fov", "script_local_reg_fov", "LR_fov", "array",
        "lr_fov", "logs002_local_registration", CORE_MATLAB_ARG + COMMON_ARGS + (
            ("lr_fov_align_basis", "--align_basis"),
        ) + IMAGE_ARGS + (("lr_fov_offset", "--offset"),),
    ),
    "ls": StepSpec("run_stitch", "script_stitch", "LS", "array", "ls", "logs003_local_image_stitch", CORE_MATLAB_ARG + COMMON_ARGS + IMAGE_ARGS + (
        ("ls_offset", "--offset"),
    )),
    "gspf": StepSpec("run_global_spf", "script_global_spf", "gSPF", "array", "gspf", "logs004_global_spot_finding", CORE_MATLAB_ARG + COMMON_ARGS + (
        ("gspf_intensity_threshold", "--intensity_threshold"),
        ("gspf_spotfinding_method", "--spotfinding_method"),
        ("gspf_loading_mode", "--loading_mode"),
    ) + IMAGE_ARGS + (("gspf_offset", "--offset"),)),
    "grd": StepSpec("run_decoding", "script_decoding", "gRD", "array", "gd", "logs004_global_reads_decoding", CORE_MATLAB_ARG + COMMON_ARGS + IMAGE_ARGS + (
        ("gd_intensity_threshold", "--intensity_threshold"),
        ("gd_spotfinding_method", "--spotfinding_method"),
        ("gd_decoding_mode", "--decoding_mode"),
        ("gd_codeMap_mode", "--codeMap_mode"),
        ("gd_loading_mode", "--loading_mode"),
        ("gd_intensityThresh_PR", "--intensityThresh_PR"),
        ("gd_voxelsize", "--voxelsize"),
        ("gd_decoding_rounds", "--decoding_rounds"),
        ("gd_offset", "--offset"),
    )),
    "egc": StepSpec("run_extract_gene_counts", "script_extract_gene_counts", "extract_gene_counts", "single", "egc", "logs005_extract_gene_counts", CONDA_SH_ARG + COMMON_ARGS + (
        ("egc_target_file", "--target_file"),
        ("egc_gene_column", "--gene_column"),
        ("egc_suffix_regex", "--suffix_regex"),
        ("egc_output_subdir", "--output_subdir"),
        ("egc_start_pos", "--start_pos"),
        ("egc_end_pos", "--end_pos"),
    ), script_dir_from_wrapper=True),
    "atlas": StepSpec("run_atlas_correlation", "script_atlas_correlation", "atlas_correlation", "single", "atlas", "logs006_atlas_correlation", CONDA_SH_ARG + (("correlation_script_dir", "--script_dir"),) + COMMON_ARGS + (
        ("atlas_gene_counts_file", "--gene_counts_file"),
        ("atlas_dir", "--atlas_dir"),
        ("atlas_output_subdir", "--output_subdir"),
        ("atlas_sample_filter_column", "--sample_filter_column"),
        ("atlas_sample_filter_contains", "--sample_filter_contains"),
        ("atlas_category_column", "--category_column"),
        ("atlas_sample_id_column", "--sample_id_column"),
        ("atlas_analysis_label", "--analysis_label"),
        ("atlas_no_plots", "--no_plots"),
    )),
    "pairwise": StepSpec("run_decode_pairwise_correlation", "script_decode_pairwise_correlation", "decode_pairwise_correlation", "single", "pairwise", "logs007_decode_pairwise_correlation", CONDA_SH_ARG + (("correlation_script_dir", "--script_dir"),) + COMMON_ARGS + (
        ("pairwise_gene_counts_dir", "--gene_counts_dir"),
        ("pairwise_gene_counts_files", "--gene_counts_files"),
        ("pairwise_output_subdir", "--output_subdir"),
        ("pairwise_analysis_label", "--analysis_label"),
        ("pairwise_no_plots", "--no_plots"),
    )),
    "dapi_cp": StepSpec("run_dapi_cellpose", "script_dapi_cellpose", "dapi_segmentation", "array", "dapi_cp", "logs008_dapi_segmentation", CONDA_SH_ARG + COMMON_ARGS + (
        ("ref_round", "--ref_round"),
        ("dapi_cp_diameter", "--diameter"),
        ("dapi_cp_area_threshold", "--area_threshold"),
        ("dapi_cp_offset", "--offset"),
    ), log_root_key="seg_log", script_dir_from_wrapper=True),
    "clumap": StepSpec("run_clustermap", "script_clustermap", "clustermap_seg", "array", "clumap", "logs011_clustermap", CONDA_SH_ARG + COMMON_ARGS + (
        ("ref_round", "--ref_round"),
        ("clumap_cell_num_threshold", "--cell_num_threshold"),
        ("clumap_dapi_grid_interval", "--dapi_grid_interval"),
        ("clumap_cell_radius", "--cell_radius"),
        ("clumap_pct_filter", "--pct_filter"),
        ("clumap_rotation", "--rotation"),
        ("clumap_extra_preprocess", "--extra_preprocess"),
        ("clumap_sub_span", "--sub_span"),
        ("clumap_expected_workers", "--expected_workers"),
        ("clumap_reads_filter", "--reads_filter"),
        ("clumap_overlap_percent", "--overlap_percent"),
        ("clumap_dapi_suffix", "--dapi_suffix"),
        ("clumap_spot_csv_name", "--spot_csv_name"),
        ("clumap_output_label", "--output_label"),
        ("clumap_offset", "--offset"),
    ), log_root_key="seg_log", script_dir_from_wrapper=True),
    "rna_restore": StepSpec("run_rna_restore", "script_rna_restore", "RNA_restore_suffix", "array", "rna_restore", "logs021_RNA_restore_suffix", CONDA_SH_ARG + COMMON_ARGS + (
        ("rna_restore_raw_csv", "--raw_csv"),
        ("rna_restore_processed_csv", "--processed_csv"),
        ("rna_restore_output_csv", "--output_csv"),
        ("image_width", "--img_c"),
        ("image_width", "--img_r"),
        ("rna_restore_rotation_deg", "--rotation_deg"),
        ("rna_restore_tolerance", "--tolerance"),
        ("clumap_output_label", "--output_label"),
        ("rna_restore_offset", "--offset"),
    ), log_root_key="seg_log", script_dir_from_wrapper=True),
    "nuclei_reg": StepSpec(
        "run_nuclei_registration", "script_nuclei_registration",
        "nuclei_registration", "array", "nuclei_reg", "logs011_nuclei_registration",
        CORE_MATLAB_ARG + COMMON_ARGS + IMAGE_ARGS + (
            ("nuclei_reg_input_format", "--input_format"),
            ("nuclei_reg_norm_out_format", "--norm_out_format"),
            ("nuclei_reg_aligned_round_outdir", "--aligned_round_outdir"),
            ("nuclei_reg_moving_round", "--moving_round"),
            ("nuclei_reg_channel_panel", "--channel_panel"),
            ("nuclei_reg_offset", "--offset"),
        ),
        log_root_key="stitch_log",
    ),
    "prepare_layout": StepSpec(
        "run_prepare_layout", "script_prepare_layout", "prepare_layout", "single",
        "prepare_layout", "logs021_prepare_layout", CONDA_SH_ARG + COMMON_ARGS + (
            ("prepare_layout_rawdata_round", "--rawdata_round"),
            ("prepare_layout_stitching_workdir", "--stitching_workdir"),
            ("prepare_layout_channel_mode", "--channel_mode"),
            ("prepare_layout_output_format", "--output_format"),
        ),
        log_root_key="stitch_log",
        script_dir_from_wrapper=True,
    ),
    "prepare_tile_config": StepSpec(
        "run_prepare_tile_config", "script_prepare_tile_config", "prepare_tile_config",
        "single", "prepare_tile_config", "logs012_prepare_tile_config", CONDA_SH_ARG + COMMON_ARGS + (
            ("prepare_tile_config_stitching_workdir", "--stitching_workdir"),
            ("prepare_tile_config_source_channel_dir", "--source_channel_dir"),
            ("prepare_tile_config_match_string", "--match_string"),
            ("prepare_tile_config_pixel_size_um", "--pixel_size_um"),
            ("prepare_tile_config_image_xy", "--image_xy"),
            ("prepare_tile_config_overlap_ratio", "--overlap_ratio"),
            ("prepare_tile_config_output_config", "--output_config"),
            ("prepare_tile_config_invert_y", "--invert_y"),
            ("prepare_tile_config_maf_file", "--maf_file"),
            ("prepare_tile_config_microscope", "--microscope"),
            ("prepare_tile_config_run_fiji_fusion_preflight", "--run_fiji_fusion_preflight"),
            ("prepare_tile_config_fiji_fusion_preflight_report", "--fiji_fusion_preflight_report"),
        ),
        log_root_key="stitch_log",
        script_dir_from_wrapper=True,
        sample_position_offset_flag="--position_offset",
    ),
    "fiji_stitch_initial": StepSpec(
        "run_fiji_stitch_initial", "script_fiji_stitch_initial", "fiji_stitch_initial",
        "single", "fiji_stitch_initial", "logs015_fiji_stitch_initial", FIJI_DIR_ARG + COMMON_ARGS + (
            ("fiji_stitch_initial_stitching_workdir", "--stitching_workdir"),
            ("fiji_stitch_initial_source_channel", "--source_channel"),
            ("fiji_stitch_initial_input_config", "--input_config"),
            ("fiji_stitch_initial_output_config", "--output_config"),
            ("fiji_stitch_initial_output_name", "--output_name"),
            ("fiji_stitch_initial_regression_threshold", "--regression_threshold"),
            ("fiji_stitch_initial_max_avg_displacement_threshold", "--max_avg_displacement_threshold"),
            ("fiji_stitch_initial_absolute_displacement_threshold", "--absolute_displacement_threshold"),
            ("fiji_stitch_initial_fusion_method", "--fusion_method"),
            ("fiji_stitch_initial_compute_overlap", "--compute_overlap"),
            ("fiji_stitch_initial_subpixel_accuracy", "--subpixel_accuracy"),
            ("fiji_stitch_initial_computation_parameters", "--computation_parameters"),
            ("fiji_stitch_initial_image_output", "--image_output"),
            ("fiji_stitch_initial_save_format", "--save_format"),
        ),
        log_root_key="stitch_log",
        script_dir_from_wrapper=True,
    ),
    "ashlar_stitch_initial": StepSpec(
        "run_ashlar_stitch_initial", "script_ashlar_stitch_initial",
        "ashlar_stitch_initial", "single", "ashlar_stitch_initial",
        "logs022_ashlar_stitch_initial", CONDA_SH_ARG + COMMON_ARGS + (
            ("ashlar_stitch_initial_stitching_workdir", "--stitching_workdir"),
            ("ashlar_stitch_initial_source_channel_dir", "--source_channel_dir"),
            ("ashlar_stitch_initial_input_config", "--input_config"),
            ("ashlar_stitch_initial_output_config", "--output_config"),
            ("ashlar_stitch_initial_stitch_result_dirname", "--stitch_result_dirname"),
            ("ashlar_stitch_initial_output_prefix", "--output_prefix"),
            ("ashlar_stitch_initial_make_3d", "--make_3d"),
            ("ashlar_stitch_initial_rotate90", "--rotate90"),
            ("ashlar_stitch_initial_rotate_positions", "--rotate_positions"),
            ("ashlar_stitch_initial_pixel_size_um", "--pixel_size_um"),
            ("ashlar_stitch_initial_max_shift_px", "--max_shift_px"),
            ("ashlar_stitch_initial_filter_sigma", "--filter_sigma"),
            ("ashlar_stitch_initial_stitch_alpha", "--stitch_alpha"),
            ("ashlar_stitch_initial_max_error", "--max_error"),
            ("ashlar_stitch_initial_slice_indices", "--slice_indices"),
        ),
        log_root_key="stitch_log",
        script_dir_from_wrapper=True,
    ),
    "prepare_moveimages": StepSpec(
        "run_prepare_moveimages", "script_prepare_moveimages", "prepare_moveimages",
        "single", "prepare_moveimages", "logs023_prepare_moveimages", CONDA_SH_ARG + COMMON_ARGS + (
            ("prepare_moveimages_stitching_workdir", "--stitching_workdir"),
            ("prepare_moveimages_rawdata_round", "--rawdata_round"),
            ("prepare_moveimages_channel_mode", "--channel_mode"),
            ("prepare_moveimages_input_config", "--input_config"),
            ("prepare_moveimages_output_config", "--output_config"),
            ("prepare_moveimages_output_format", "--output_format"),
            ("prepare_moveimages_rotate_shifts", "--rotate_shifts"),
            ("prepare_moveimages_shift_sign", "--shift_sign"),
        ),
        log_root_key="stitch_log",
        script_dir_from_wrapper=True,
    ),
    "fiji_stitch_mosaic": StepSpec(
        "run_fiji_stitch_mosaic", "script_fiji_stitch_mosaic", "fiji_stitch_mosaic",
        "single", "fiji_stitch_mosaic", "logs016_fiji_stitch_mosaic", FIJI_DIR_ARG + COMMON_ARGS + (
            ("fiji_stitch_mosaic_stitching_workdir", "--stitching_workdir"),
            ("fiji_stitch_mosaic_input_config", "--input_config"),
            ("fiji_stitch_mosaic_channel_mode", "--channel_mode"),
            ("fiji_stitch_mosaic_channel_dir_prefix", "--channel_dir_prefix"),
            ("fiji_stitch_mosaic_output_prefix", "--output_prefix"),
            ("fiji_stitch_mosaic_fusion_method", "--fusion_method"),
            ("fiji_stitch_mosaic_image_output", "--image_output"),
            ("fiji_stitch_mosaic_save_format", "--save_format"),
        ),
        log_root_key="stitch_log",
        script_dir_from_wrapper=True,
    ),
    "ashlar_stitch_mosaic": StepSpec(
        "run_ashlar_stitch_mosaic", "script_ashlar_stitch_mosaic",
        "ashlar_stitch_mosaic", "single", "ashlar_stitch_mosaic",
        "logs024_ashlar_stitch_mosaic", CONDA_SH_ARG + COMMON_ARGS + (
            ("ashlar_stitch_mosaic_stitching_workdir", "--stitching_workdir"),
            ("ashlar_stitch_mosaic_channel_mode", "--channel_mode"),
            ("ashlar_stitch_mosaic_input_config", "--input_config"),
            ("ashlar_stitch_mosaic_channel_dir_prefix", "--channel_dir_prefix"),
            ("ashlar_stitch_mosaic_stitch_result_dirname", "--stitch_result_dirname"),
            ("ashlar_stitch_mosaic_output_prefix", "--output_prefix"),
            ("ashlar_stitch_mosaic_output_format", "--output_format"),
            ("ashlar_stitch_mosaic_rotate_images", "--rotate_images"),
            ("ashlar_stitch_mosaic_make_3d", "--make_3d"),
            ("ashlar_stitch_mosaic_pixel_size_um", "--pixel_size_um"),
            ("ashlar_stitch_mosaic_slice_indices", "--slice_indices"),
        ),
        log_root_key="stitch_log",
        script_dir_from_wrapper=True,
    ),
    "pyreg": StepSpec(
        "run_mosaic_registration_python", "script_register_mosaic_python", "mosaic_reg_python",
        "single", "pyreg", "logs025_mosaic_registration", CONDA_SH_ARG + COMMON_ARGS + (
            ("pyreg_fixed_path", "--fixed_path"),
            ("pyreg_moving_path", "--moving_path"),
            ("pyreg_output_workdir", "--output_workdir"),
            ("pyreg_output_label", "--output_label"),
            ("pyreg_overview_downsample", "--overview_downsample"),
            ("pyreg_overview_block_px", "--overview_block_px"),
            ("pyreg_roi_size_px", "--roi_size_px"),
            ("pyreg_roi_count", "--roi_count"),
            ("pyreg_min_valid_rois", "--min_valid_rois"),
            ("pyreg_upsample_factor", "--upsample_factor"),
            ("pyreg_min_overlap_ratio", "--min_overlap_ratio"),
            ("pyreg_max_roi_spread_px", "--max_roi_spread_px"),
            ("pyreg_tile_size_px", "--tile_size_px"),
            ("pyreg_interpolation_order", "--interpolation_order"),
            ("pyreg_preview_downsample", "--preview_downsample"),
            ("pyreg_compression", "--compression"),
            ("pyreg_overwrite", "--overwrite"),
        ),
        log_root_key="stitch_log",
        script_dir_from_wrapper=True,
    ),
    "matreg": StepSpec(
        "run_mosaic_registration_matlab", "script_register_mosaic_matlab", "mosaic_reg_matlab",
        "single", "matreg", "logs026_mosaic_registration", CORE_MATLAB_ARG + CONDA_SH_ARG + COMMON_ARGS + (
            ("matreg_fixed_path", "--fixed_path"),
            ("matreg_moving_path", "--moving_path"),
            ("matreg_output_workdir", "--output_workdir"),
            ("matreg_output_label", "--output_label"),
            ("matreg_overview_downsample", "--overview_downsample"),
            ("matreg_overview_block_px", "--overview_block_px"),
            ("matreg_roi_size_px", "--roi_size_px"),
            ("matreg_roi_count", "--roi_count"),
            ("matreg_min_valid_rois", "--min_valid_rois"),
            ("matreg_min_overlap_ratio", "--min_overlap_ratio"),
            ("matreg_max_roi_spread_px", "--max_roi_spread_px"),
            ("matreg_tile_size_px", "--tile_size_px"),
            ("matreg_interpolation_order", "--interpolation_order"),
            ("matreg_preview_downsample", "--preview_downsample"),
            ("matreg_compression", "--compression"),
            ("matreg_overwrite", "--overwrite"),
        ),
        log_root_key="stitch_log",
        script_dir_from_wrapper=True,
    ),
    "reg_compare": StepSpec(
        "run_mosaic_registration_compare", "script_compare_mosaic_registration",
        "mosaic_reg_compare", "single", "reg_compare", "logs028_mosaic_registration",
        CONDA_SH_ARG + COMMON_ARGS + (
            ("reg_compare_python_json", "--python_json"),
            ("reg_compare_matlab_json", "--matlab_json"),
            ("reg_compare_output_workdir", "--output_workdir"),
            ("reg_compare_output_label", "--output_label"),
            ("reg_compare_agreement_tolerance_px", "--agreement_tolerance_px"),
            ("reg_compare_fail_on_disagreement", "--fail_on_disagreement"),
            ("reg_compare_overwrite", "--overwrite"),
        ),
        log_root_key="stitch_log",
        script_dir_from_wrapper=True,
    ),
    "transform_apply": StepSpec(
        "run_apply_mosaic_transform", "script_apply_mosaic_transform",
        "mosaic_apply_transform", "single", "transform_apply", "logs029_mosaic_registration",
        CONDA_SH_ARG + COMMON_ARGS + (
            ("transform_apply_transform_json", "--transform_json"),
            ("transform_apply_fixed_path", "--fixed_path"),
            ("transform_apply_moving_path", "--moving_path"),
            ("transform_apply_output_workdir", "--output_workdir"),
            ("transform_apply_output_label", "--output_label"),
            ("transform_apply_tile_size_px", "--tile_size_px"),
            ("transform_apply_interpolation_order", "--interpolation_order"),
            ("transform_apply_preview_downsample", "--preview_downsample"),
            ("transform_apply_overview_block_px", "--overview_block_px"),
            ("transform_apply_compression", "--compression"),
            ("transform_apply_overwrite", "--overwrite"),
        ),
        log_root_key="stitch_log",
        script_dir_from_wrapper=True,
    ),
}


def _parse_samples_registry(raw: str) -> tuple[SampleMetadata, ...]:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        parsed: dict[str, object] = {}
        for name, count in pairs:
            if name in parsed:
                raise ValueError(f"Duplicate sample name: {name}")
            parsed[name] = count
        return parsed

    try:
        registry: object = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError("samples must be a strict JSON object with unique keys") from error
    if not isinstance(registry, dict) or not registry:
        raise ValueError("samples must be a non-empty JSON object")

    samples: list[SampleMetadata] = []
    position_offset = 0
    for project_name, fov_count in registry.items():
        if not project_name:
            raise ValueError("sample names must not be empty")
        if type(fov_count) is not int or fov_count <= 0:
            raise ValueError(f"sample count for {project_name} must be a positive integer")
        samples.append(SampleMetadata(project_name, fov_count, position_offset))
        position_offset += fov_count
    return tuple(samples)


def load_config(config_path: Path) -> LoadedConfig:
    parser = configparser.ConfigParser(
        interpolation=configparser.BasicInterpolation(),
        inline_comment_prefixes=(";",),
    )
    with config_path.open(encoding="utf-8") as handle:
        parser.read_file(handle)
    sections = tuple(sorted(name for name in parser.sections() if name.startswith("JOB_")))
    if not sections:
        raise ValueError("No [JOB_*] sections found")
    raw_samples = parser.defaults().get("samples")
    if raw_samples is None:
        raise ValueError("Missing required [DEFAULT].samples registry")
    samples = _parse_samples_registry(raw_samples)
    samples_by_name = MappingProxyType({sample.project_name: sample for sample in samples})
    sample_by_section: dict[str, SampleMetadata] = {}
    for section_name in sections:
        project_name = parser[section_name]["project_name"]
        try:
            sample_by_section[section_name] = samples_by_name[project_name]
        except KeyError as error:
            raise ValueError(
                f"Unknown project_name for {section_name}: {project_name}"
            ) from error
    return LoadedConfig(
        parser,
        sections,
        samples_by_name,
        MappingProxyType(sample_by_section),
    )


def _quote(token: str) -> str:
    return shlex.quote(str(token))


def _step_log_work_dir(
    section: configparser.SectionProxy,
    spec: StepSpec,
) -> Path:
    return Path(section[spec.log_root_key]) / f"submit{section['job_suffix']}"


def render_submission_controller(parser: configparser.ConfigParser) -> str:
    template = r'''USER_TASK_LIMIT=__USER_TASK_LIMIT__
SYSTEM_TASK_LIMIT=__SYSTEM_TASK_LIMIT__
CURRENT_USER=$(id -un)
declare -A ACTIVE_PARENT_IDS=()

read_scheduler_snapshot() {
    local queue_output
    local task_id
    local parent_id
    local owner
    local state
    declare -A seen_task_ids=()

    if ! queue_output=$(squeue -h --array -o "%i|%A|%u|%T"); then
        printf 'ERROR: squeue query failed\n' >&2
        return 1
    fi

    ACTIVE_PARENT_IDS=()
    USER_ACTIVE_TASKS=0
    SYSTEM_ACTIVE_TASKS=0
    while IFS='|' read -r task_id parent_id owner state; do
        task_id="${task_id//[[:space:]]/}"
        parent_id="${parent_id//[[:space:]]/}"
        owner="${owner//[[:space:]]/}"
        state="${state//[[:space:]]/}"
        if [[ -n "$parent_id" && -n "$state" ]]; then
            ACTIVE_PARENT_IDS["$parent_id"]=1
        fi
        if [[ "$state" != "PENDING" && "$state" != "RUNNING" ]]; then
            continue
        fi
        if [[ -z "$task_id" || -n "${seen_task_ids[$task_id]+x}" ]]; then
            continue
        fi
        seen_task_ids["$task_id"]=1
        SYSTEM_ACTIVE_TASKS=$((SYSTEM_ACTIVE_TASKS + 1))
        if [[ "$owner" == "$CURRENT_USER" ]]; then
            USER_ACTIVE_TASKS=$((USER_ACTIVE_TASKS + 1))
        fi
    done <<< "$queue_output"

    USER_REMAINING_TASKS=$((USER_TASK_LIMIT - USER_ACTIVE_TASKS))
    SYSTEM_REMAINING_TASKS=$((SYSTEM_TASK_LIMIT - SYSTEM_ACTIVE_TASKS))
}

reconcile_dependencies() {
    local original_dependencies="$1"
    local parent_id
    local accounting_output
    local accounting_job_id
    local state
    local exit_code
    local matched
    local -a parent_ids=()
    local -a active_dependencies=()

    RECONCILED_DEPENDENCIES=""
    if [[ -z "$original_dependencies" ]]; then
        return 0
    fi

    IFS=':' read -r -a parent_ids <<< "$original_dependencies"
    for parent_id in "${parent_ids[@]}"; do
        if [[ -n "${ACTIVE_PARENT_IDS[$parent_id]+x}" ]]; then
            active_dependencies+=("$parent_id")
            continue
        fi
        if ! accounting_output=$(sacct -X -n -P -j "$parent_id" --format=JobIDRaw,State,ExitCode); then
            printf 'ERROR: dependency accounting query failed | JOB_ID=%s\n' "$parent_id" >&2
            return 1
        fi
        matched=0
        while IFS='|' read -r accounting_job_id state exit_code; do
            accounting_job_id="${accounting_job_id//[[:space:]]/}"
            state="${state//[[:space:]]/}"
            exit_code="${exit_code//[[:space:]]/}"
            if [[ "$accounting_job_id" != "$parent_id" ]]; then
                continue
            fi
            matched=1
            if [[ "$state" == "COMPLETED" && "$exit_code" == "0:0" ]]; then
                break
            fi
            printf 'ERROR: dependency is not successful | JOB_ID=%s | STATE=%s | EXIT_CODE=%s\n' \
                "$parent_id" "${state:-UNKNOWN}" "${exit_code:-UNKNOWN}" >&2
            return 1
        done <<< "$accounting_output"
        if (( matched == 0 )); then
            printf 'ERROR: dependency state is unknown | JOB_ID=%s\n' "$parent_id" >&2
            return 1
        fi
    done

    if (( ${#active_dependencies[@]} > 0 )); then
        RECONCILED_DEPENDENCIES=$(IFS=:; echo "${active_dependencies[*]}")
    fi
}

filter_device_iv_banner() {
    local raw_output="$1"
    local -a output_lines=()
    local title_index=-1
    local completion_index=-1
    local closing_index=-1
    local line
    local index

    mapfile -t output_lines <<< "$raw_output"
    for (( index=0; index<${#output_lines[@]}; index++ )); do
        line="${output_lines[$index]}"
        if (( title_index < 0 )) && \
            [[ "$line" == *"装置四 - 参数检查脚本"* || \
               "$line" == *"Device IV - Parameter Checking Script"* ]]; then
            title_index=$index
        fi
        if (( title_index >= 0 )) && [[ "$line" == *"All Checks Passed"* ]]; then
            completion_index=$index
            break
        fi
    done

    if (( title_index < 0 || title_index > 1 || completion_index < title_index )); then
        printf '%s\n' "$raw_output"
        return 0
    fi
    if (( title_index == 1 )) && [[ "${output_lines[0]}" != *"╔"* ]]; then
        printf '%s\n' "$raw_output"
        return 0
    fi

    closing_index=$((completion_index + 1))
    if (( closing_index >= ${#output_lines[@]} )) || \
        [[ "${output_lines[$closing_index]}" != *"╚"* ]]; then
        printf '%s\n' "$raw_output"
        return 0
    fi

    for (( index=closing_index + 1; index<${#output_lines[@]}; index++ )); do
        printf '%s\n' "${output_lines[$index]}"
    done
}

submit_when_ready() {
    local required_tasks="$1"
    local stage_name="$2"
    local initial_wait_seconds="$3"
    local poll_seconds="$4"
    local original_dependencies="$5"
    local submission_id="${SUBMISSION_CONTEXT:-UNKNOWN}:${stage_name}"
    local submission_start_seconds=$SECONDS
    local initial_wait_done=0
    local wait_phase
    local wait_seconds
    local submit_output
    local submit_status
    local filtered_output
    local parsable_output
    local submitted_job_id
    local submission_wait_seconds
    local line
    local -a base_command=()
    local -a submit_command=()
    shift 5
    base_command=("$@")

    while true; do
        if ! read_scheduler_snapshot; then
            return 1
        fi
        if ! reconcile_dependencies "$original_dependencies"; then
            return 1
        fi
        if (( USER_REMAINING_TASKS < required_tasks || SYSTEM_REMAINING_TASKS < required_tasks )); then
            if (( initial_wait_done == 0 )); then
                wait_phase=INITIAL
                wait_seconds="$initial_wait_seconds"
                initial_wait_done=1
            else
                wait_phase=POLL
                wait_seconds="$poll_seconds"
            fi
            printf 'STATUS: WAITING\n' >&2
            printf 'JOB_NAME=%s\n' "$submission_id" >&2
            printf 'SLURM_JOB_NAME=%s\n' "$stage_name" >&2
            printf 'REQUIRED_TASKS=%s\n' "$required_tasks" >&2
            printf 'USER_ACTIVE_TASKS=%s\n' "$USER_ACTIVE_TASKS" >&2
            printf 'USER_TASK_LIMIT=%s\n' "$USER_TASK_LIMIT" >&2
            printf 'USER_REMAINING_TASKS=%s\n' "$USER_REMAINING_TASKS" >&2
            printf 'SYSTEM_ACTIVE_TASKS=%s\n' "$SYSTEM_ACTIVE_TASKS" >&2
            printf 'SYSTEM_TASK_LIMIT=%s\n' "$SYSTEM_TASK_LIMIT" >&2
            printf 'SYSTEM_REMAINING_TASKS=%s\n' "$SYSTEM_REMAINING_TASKS" >&2
            printf 'WAIT_PHASE=%s\n' "$wait_phase" >&2
            printf 'NEXT_CHECK_SECONDS=%s\n' "$wait_seconds" >&2
            sleep "$wait_seconds"
            continue
        fi

        if ! read_scheduler_snapshot; then
            return 1
        fi
        if ! reconcile_dependencies "$original_dependencies"; then
            return 1
        fi
        if (( USER_REMAINING_TASKS < required_tasks || SYSTEM_REMAINING_TASKS < required_tasks )); then
            printf 'STATUS: CAPACITY_CHANGED\n' >&2
            printf 'JOB_NAME=%s\n' "$submission_id" >&2
            printf 'SLURM_JOB_NAME=%s\n' "$stage_name" >&2
            printf 'REQUIRED_TASKS=%s\n' "$required_tasks" >&2
            printf 'USER_REMAINING_TASKS=%s\n' "$USER_REMAINING_TASKS" >&2
            printf 'SYSTEM_REMAINING_TASKS=%s\n' "$SYSTEM_REMAINING_TASKS" >&2
            printf 'NEXT_CHECK_SECONDS=%s\n' "$poll_seconds" >&2
            initial_wait_done=1
            sleep "$poll_seconds"
            continue
        fi

        printf 'STATUS: CAPACITY_AVAILABLE\n' >&2
        printf 'JOB_NAME=%s\n' "$submission_id" >&2
        printf 'SLURM_JOB_NAME=%s\n' "$stage_name" >&2
        printf 'REQUIRED_TASKS=%s\n' "$required_tasks" >&2
        printf 'USER_ACTIVE_TASKS=%s\n' "$USER_ACTIVE_TASKS" >&2
        printf 'USER_TASK_LIMIT=%s\n' "$USER_TASK_LIMIT" >&2
        printf 'USER_REMAINING_TASKS=%s\n' "$USER_REMAINING_TASKS" >&2
        printf 'SYSTEM_ACTIVE_TASKS=%s\n' "$SYSTEM_ACTIVE_TASKS" >&2
        printf 'SYSTEM_TASK_LIMIT=%s\n' "$SYSTEM_TASK_LIMIT" >&2
        printf 'SYSTEM_REMAINING_TASKS=%s\n' "$SYSTEM_REMAINING_TASKS" >&2
        submit_command=("${base_command[@]}")
        if [[ -n "$RECONCILED_DEPENDENCIES" ]]; then
            submit_command=(
                "${base_command[0]}"
                "--dependency=afterok:${RECONCILED_DEPENDENCIES}"
                "${base_command[@]:1}"
            )
        fi
        submit_status=0
        submit_output=$("${submit_command[@]}" 2>&1) || submit_status=$?
        if (( submit_status == 0 )); then
            filtered_output=$(filter_device_iv_banner "$submit_output")
            parsable_output=""
            while IFS= read -r line; do
                if [[ "$line" =~ ^[0-9]+(\;[^[:space:]]+)?$ ]]; then
                    parsable_output="$line"
                elif [[ -n "$line" ]]; then
                    printf '%s\n' "$line" >&2
                fi
            done <<< "$filtered_output"
            if [[ -z "$parsable_output" ]]; then
                printf 'ERROR: sbatch returned no parsable Job ID for %s\n' "$submission_id" >&2
                return 1
            fi
            submitted_job_id="${parsable_output%%;*}"
            submission_wait_seconds=$((SECONDS - submission_start_seconds))
            printf 'STATUS: SUBMITTED\n' >&2
            printf 'JOB_NAME=%s\n' "$submission_id" >&2
            printf 'SLURM_JOB_NAME=%s\n' "$stage_name" >&2
            printf 'SLURM_JOB_ID=%s\n' "$submitted_job_id" >&2
            printf 'ARRAY_TASKS=%s\n' "$required_tasks" >&2
            printf 'SUBMISSION_WAIT_SECONDS=%s\n' "$submission_wait_seconds" >&2
            printf '%s\n' '==================' >&2
            printf '%s\n' "$parsable_output"
            return 0
        fi

        if ! read_scheduler_snapshot; then
            return 1
        fi
        if (( USER_REMAINING_TASKS < required_tasks || SYSTEM_REMAINING_TASKS < required_tasks )); then
            printf 'STATUS: SUBMIT_RACE | JOB_NAME=%s | NEXT_CHECK_SECONDS=%s\n' \
                "$submission_id" "$poll_seconds" >&2
            initial_wait_done=1
            sleep "$poll_seconds"
            continue
        fi

        printf 'STATUS: FAILED | JOB_NAME=%s\n' "$submission_id" >&2
        filtered_output=$(filter_device_iv_banner "$submit_output")
        if [[ -n "$filtered_output" ]]; then
            printf '%s\n' "$filtered_output" >&2
        fi
        return "$submit_status"
    done
}'''
    return template.replace(
        "__USER_TASK_LIMIT__", parser.defaults()["submit_user_task_limit"]
    ).replace(
        "__SYSTEM_TASK_LIMIT__", parser.defaults()["submit_system_task_limit"]
    )


def _render_command(
    variable: str,
    command: list[str],
    dependency: str | None,
    required_tasks: int,
    section: configparser.SectionProxy,
    spec: StepSpec,
) -> list[str]:
    user_limit = section.getint("submit_user_task_limit")
    system_limit = section.getint("submit_system_task_limit")
    if required_tasks > user_limit or required_tasks > system_limit:
        raise ValueError(
            f"{spec.job_name} requires {required_tasks} tasks, exceeding submission quota"
        )
    scheduler = command[:]
    parts: list[str] = []
    index = 1
    while index < len(scheduler):
        token = scheduler[index]
        if token.startswith("--array=") or token == "--parsable":
            parts.append(_quote(token))
            index += 1
        elif token.startswith("-"):
            parts.append(f"{_quote(token)} {_quote(scheduler[index + 1])}")
            index += 2
        else:
            parts.append(_quote(token))
            index += 1
    initial_wait = section[f"{spec.prefix}_submit_initial_wait_seconds"]
    poll_wait = section[f"{spec.prefix}_submit_poll_seconds"]
    rendered_dependency = f'"{dependency}"' if dependency else "''"
    rendered = [
        f"{variable}_OUTPUT=$(submit_when_ready {required_tasks} "
        f"{_quote(spec.job_name)} {_quote(initial_wait)} {_quote(poll_wait)} "
        f"{rendered_dependency} {_quote(scheduler[0])} \\"
    ]
    rendered.extend(f"    {part} \\" for part in parts[:-1])
    rendered.append(f"    {parts[-1]})")
    rendered.append(f"{variable}_JOB_ID=${{{variable}_OUTPUT%%;*}}")
    return rendered


def _base_command(
    section: configparser.SectionProxy,
    spec: StepSpec,
    sample: SampleMetadata,
) -> list[str]:
    wrapper_path = Path(section[spec.wrapper_key])
    command = [
        "sbatch",
        "--parsable",
        "-J", spec.job_name,
        "-p", section[f"{spec.prefix}_partition"],
        "-c", section[f"{spec.prefix}_cpus"],
        str(wrapper_path),
    ]
    if spec.script_dir_from_wrapper:
        command.extend(("--script_dir", str(wrapper_path.parent)))
    for config_key, wrapper_flag in spec.args:
        command.extend((wrapper_flag, section[config_key]))
    if spec.sample_position_offset_flag is not None:
        command.extend((spec.sample_position_offset_flag, str(sample.position_offset)))
    return command


def render_single_submission(
    section: configparser.SectionProxy,
    spec: StepSpec,
    sample: SampleMetadata,
    dependency: str | None,
) -> tuple[list[str], str]:
    variable = spec.prefix.upper()
    return _render_command(
        variable, _base_command(section, spec, sample), dependency, 1, section, spec
    ), f"${{{variable}_JOB_ID}}"


def render_array_submissions(
    section: configparser.SectionProxy,
    spec: StepSpec,
    sample: SampleMetadata,
    dependency: str | None,
) -> tuple[list[str], str]:
    tasks_per_fov = section.getint(f"{spec.prefix}_array_tasks")
    if tasks_per_fov <= 0:
        raise ValueError(f"{spec.prefix}_array_tasks must be greater than zero")
    total = sample.fov_count * tasks_per_fov
    parallel = section.getint(f"{spec.prefix}_parallel_tasks")
    chunk_limit = section.getint(f"{spec.prefix}_chunk_tasks")
    base_offset = section.getint(f"{spec.prefix}_offset")
    variable = spec.prefix.upper()
    lines = [f"{variable}_JOB_IDS=()"]
    for start in range(1, total + 1, chunk_limit):
        size = min(chunk_limit, total - start + 1)
        command = _base_command(section, spec, sample)
        command[8:8] = [f"--array=1-{size}%{parallel}"]
        offset_flag = next(index for index, token in enumerate(command) if token == "--offset")
        command[offset_flag + 1] = str(base_offset + start - 1)
        lines.extend(_render_command(variable, command, dependency, size, section, spec))
        lines.append(f'{variable}_JOB_IDS+=("${{{variable}_JOB_ID}}")')
    lines.append(f'{variable}_DEPENDENCY=$(IFS=:; echo "${{{variable}_JOB_IDS[*]}}")')
    return lines, f"${{{variable}_DEPENDENCY}}"


def render_submission_script(config: LoadedConfig) -> str:
    parser = config.parser
    section_names = config.section_names
    for section_name in section_names:
        section = parser[section_name]
        sample = config.sample_by_section[section_name]
        if section.getboolean("run_local_reg_subtile", fallback=False) and section.getboolean(
            "run_local_reg_fov", fallback=False
        ):
            raise ValueError(
                f"{section_name} cannot enable both run_local_reg_subtile and run_local_reg_fov"
            )
    lines = [
        "#!/bin/bash",
        "#SBATCH -J must_give_specific_job_name",
        "#SBATCH -o %x_%A.log",
        "#SBATCH -e %x_%A.err",
        "#SBATCH -p C64M256G",
        "#SBATCH -N 1",
        "#SBATCH -c 2",
        "#SBATCH --time=25-00:00:0",
        "# Submit with: sbatch -J <specific_job_name> <generated_script.sh>",
        "set -euo pipefail",
        "",
        render_submission_controller(parser),
        "",
        "# Submit configured jobs",
    ]
    for job_index, section_name in enumerate(section_names, start=1):
        section = parser[section_name]
        enabled = [(name, STEP_SPECS[name]) for name in STEP_ORDER if section.getboolean(STEP_SPECS[name].run_key, fallback=False)]
        if not enabled:
            continue
        submission_context = f"{section_name}:{section['project_name']}"
        lines.extend((
            "",
            f"# Job {job_index}: {section_name} ({section['project_name']})",
            f'echo "Starting job {job_index}: {section["project_name"]}"',
            f"SUBMISSION_CONTEXT={_quote(submission_context)}",
        ))
        dependency: str | None = None
        for _, spec in enabled:
            log_work_dir = _step_log_work_dir(section, spec)
            lines.extend(
                (
                    "",
                    f"# Submit {spec.job_name}",
                    f"mkdir -p {_quote(str(log_work_dir / spec.log_dir))}",
                    f"cd {_quote(str(log_work_dir))} || exit 1",
                )
            )
            match spec.submission_type:
                case "array":
                    submission, dependency = render_array_submissions(
                        section, spec, sample, dependency
                    )
                case "single":
                    submission, dependency = render_single_submission(
                        section, spec, sample, dependency
                    )
                case unexpected:
                    raise ValueError(f"Unsupported submission type: {unexpected}")
            lines.extend(submission)
    return "\n".join(lines) + "\n"


def write_output(output_path: Path, content: str, *, overwrite: bool) -> None:
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path}")
    output_path.write_text(content, encoding="utf-8")
    output_path.chmod(output_path.stat().st_mode | 0o111)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the SpotDecoding SLURM submission script.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    write_output(args.output, render_submission_script(load_config(args.config)), overwrite=args.overwrite)


if __name__ == "__main__":
    main()
