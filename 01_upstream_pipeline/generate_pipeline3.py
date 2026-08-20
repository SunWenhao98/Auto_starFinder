import configparser
import sys
import math
import shlex


def build_array_spec(tasks, parallel_tasks):
    return f"1-{tasks}%{parallel_tasks}"


def build_array_option(array_range, parallel_tasks):
    return f"--array={array_range}%{parallel_tasks}"


def split_csv_value(value):
    return [item.strip() for item in str(value).split(',') if item.strip()]


def file_stem(value):
    name = str(value).rstrip('/').split('/')[-1]
    return name.rsplit('.', 1)[0]


def config_bool_string(section, key, fallback=False):
    return 'true' if section.getboolean(key, fallback=fallback) else 'false'


def format_named_args(pairs):
    return " \\\n".join(
        f"--{name} {shlex.quote(str(value))}" for name, value in pairs
    )


def generate_shell_script(config_file):
    
    config = configparser.ConfigParser(
        interpolation=configparser.BasicInterpolation(),
        inline_comment_prefixes=';'
    )
    
    try:
        config.read(config_file)
    except Exception as e:
        print(f"Error reading config file {config_file}: {e}", file=sys.stderr)
        sys.exit(1)

    print("#!/bin/bash")
    print(f"# Auto-generated script from {config_file}")
    print("# This script submits a batch of STARmap pipeline jobs.\n")

    # 筛选出所有 Job 节，并排序
    job_sections = sorted([s for s in config.sections() if s != 'DEFAULT'])
    
    if not job_sections:
        print(f"Error: No [JOB_...] sections found in {config_file}", file=sys.stderr)
        sys.exit(1)

    enable_job_array_dependency = config['DEFAULT'].getboolean(
        'enable_jobArray_dependency', fallback=False
    )
    previous_section_dependency_str = ""

    # 遍历所有 Job
    for i, section_name in enumerate(job_sections):
        job_counter = i + 1
        
        # p 会自动从 [DEFAULT] 继承，并被 [JOB_XXX] 覆盖
        p = config[section_name]
        
        job_prefix = f"ARRAY{job_counter:03d}"
        JOB_ID_VAR = f"{job_prefix}_JOB_ID"
        JOB_OUT_VAR = f"{job_prefix}_OUTPUT"
        
        # --- 关键: 动态依赖链 ---
        # enable_jobArray_dependency=true makes the first submitted step in this
        # section wait for the previous section's final step. The default false
        # keeps different samples/conditions as independent job chains.
        dependency_str = previous_section_dependency_str if enable_job_array_dependency else ""

        try:
            # --- 1. 定义目录和名称 ---
            job_dir_suffix = f"submit{p['job_suffix']}"
            reg_dir_suffix = f"02_registration{p['regDir_suffix']}"
            spf_work_dir = f"{p['spf_output']}/{job_dir_suffix}"
            spd_work_dir = f"{p['spd_output']}/{job_dir_suffix}"
            work_dir = f"{p['output_root']}/{job_dir_suffix}"
            seg_work_dir = f"{p['seg_output']}/{job_dir_suffix}"
            stitch_work_dir = f"{p['stitch_output']}/{job_dir_suffix}"
            integ_work_dir = f"{p['Integ_output']}/{job_dir_suffix}"
            plotback_work_dir = f"{p['plotback_output']}/{job_dir_suffix}"
            eval_work_dir = f"{p['Eva_out']}/{job_dir_suffix}"

            # --- 定义 spotiflow 的参数
            spf_reg_dir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}"
            if p['spf_mode'] == 'Original':
                spf_input_round_dir = f"{p['project_root']}/{p['project_name']}/01_data/round{int(p['ref_round']):03d}"
                spf_csv_pattern = "GBM_XMdc"
            elif p['spf_mode'] == 'LocalReg':
                spf_input_round_dir = f"{spf_reg_dir}"
                spf_csv_pattern = "local_registered"
            elif p['spf_mode'] == 'raw_preprocessed':
                spf_input_round_dir = f"{spf_reg_dir}"
                spf_csv_pattern = "rawMorphoRecon"
            filelist_path = f"{spf_work_dir}/filelist.txt"

            gl_args = (
                f"{spf_input_round_dir} \\\n"
                f"{spf_csv_pattern} {p['ref_round']} {p['gl_file_num']}"
            )

            # Spot Finding 参数 (基础，无array)
            spf_array = build_array_spec(p['spf_array_tasks'], p['spf_parallel_tasks'])
            spf_args_base = (
                f"{spf_input_round_dir} \\\n"
                f"{spf_reg_dir} \\\n"
                f"{filelist_path} \\\n"
                f"{p['spf_prob']}"
            )

            # Spot Concatenation 参数
            spf_concat_args = (
                f"{spf_reg_dir} \\\n"
                f"{p['image_depth']},{p['image_width']},{p['image_width']} {spf_csv_pattern}"
            )

            # 定义 sparse deconvolution 参数
            sd_input_dir = f"{p['sd_project_root']}/{p['project_name']}/01_data"
            sd_output_dir = f"{p['project_root']}/{p['project_name']}/01_data"
            sd_temp_dir = f"{p['project_root']}/{p['project_name']}/zz_TEMP"
            filelist_path = f"{spd_work_dir}/filelist.txt"
            sd_array = build_array_spec(p['sd_array_tasks'], p['sd_parallel_tasks'])
            sd_args_base = (
                f"{sd_input_dir} \\\n"
                f"{sd_output_dir} \\\n"
                f"{sd_temp_dir} \\\n"
                f"{filelist_path} \\\n"
                f"{p['sd_pixelsize']} {p['sd_sigma_gaussian']} \\\n"
                f"{p['sd_fidelity']} {p['sd_sparsity']} {p['sd_percennorm']} {p['sd_hessian_iter']} {p['sd_sparse_iter_total']} \\\n"
                f"{p['sd_resolution']} {p['sd_numerical_aperture']} {p['sd_wavelengthmode']} {p['sd_chunksize']} {p['sd_overlap']} {p['sd_decon_type']} {p['sd_continuity']} {p['sd_background']} \\\n"
                f"{p['sd_enable_refineResolution']} {p['sd_enable_Guassblur']} {p['sd_enable_upsample']} "
            )


            # --- 2. 定义通用参数 ---
            image_geom_args = (
                f"{p['image_width']} {p['image_depth']} {p['ref_round']} "
                f"{p['channel_num']} {p['round_num']}"
            )
            
#             gr_input_format = uint16
#               gr_norm_out_format = uint8
            # --- 3. 构建所有命令的 *参数* 部分 ---
            
            gr_array = build_array_spec(p['gr_array_tasks'], p['gr_parallel_tasks'])
            gr_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} {p['gr_norm_mode']} {p['gr_percen_max']} "
                f"{p['gr_hist_round']} {p['gr_hist_channel']} {p['gr_radius']} "
                f"{p['gr_mode']} {p['gr_align_basis']} {image_geom_args} {p['gr_offset']} \\\n"
                f"{p['gr_erode']} {p['gr_transform']} {p['gr_input_format']} {p['gr_norm_out_format']}"
            )
            
            # --- 【关键修正 1/3】 ---
            # 定义 LR 的 *基础* 参数，不包含 offset
            lr_array = build_array_spec(p['lr_array_tasks'], p['lr_parallel_tasks'])
            lr_args_base = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} {p['lr_align_basis']} {image_geom_args}"
            )

            ls_array = build_array_spec(p['ls_array_tasks'], p['ls_parallel_tasks'])
            ls_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} {image_geom_args} {p['ls_offset']}"
            )
            
            gd_array = build_array_spec(p['gd_array_tasks'], p['gd_parallel_tasks'])
            voxel_size = f"[{p['gd_voxelsize']}]"
            # print(voxel_size)
            gd_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} {image_geom_args} {p['gd_intensity_threshold']} {p['gd_spotfinding_method']} "
                f"{p['gd_decoding_mode']} {p['gd_codeMap_mode']} {p['gd_loading_mode']} {p['gd_intensityThresh_PR']} {voxel_size} {p['gd_decoding_rounds']} {p['gd_offset']}"
            )

            egc_target_file = p.get('egc_target_file', fallback='goodPoints_max3d_0.2_tri.csv')
            egc_output_subdir = p.get('egc_output_subdir', fallback='00_gene_counts')
            egc_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} "
                f"{egc_target_file} "
                f"{p.get('egc_gene_column', fallback='Gene')} "
                f"'{p.get('egc_suffix_regex', fallback='_(rbRNA|ntRNA)$')}' "
                f"{egc_output_subdir} "
                f"{p.get('egc_start_pos', fallback='none')} "
                f"{p.get('egc_end_pos', fallback='none')}"
            )

            atlas_gene_counts_file = p.get('atlas_gene_counts_file', fallback='auto')
            if atlas_gene_counts_file == 'auto':
                atlas_gene_counts_file = f"{egc_output_subdir}/{p['project_name']}_{file_stem(egc_target_file)}_gene_counts.csv"
            atlas_analysis_label = p.get('atlas_analysis_label', fallback='auto')
            if atlas_analysis_label == 'auto':
                atlas_analysis_label = file_stem(egc_target_file)
            atlas_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} "
                f"{atlas_gene_counts_file} "
                f"{p.get('atlas_dir', fallback='')} "
                f"{p.get('atlas_output_subdir', fallback='01_atlas_correlation')} "
                f"{p.get('atlas_sample_filter_column', fallback='structure_abbreviation')} "
                f"'{p.get('atlas_sample_filter_contains', fallback='histology')}' "
                f"{p.get('atlas_category_column', fallback='structure_abbreviation')} "
                f"{p.get('atlas_sample_id_column', fallback='rna_well_id')} "
                f"{atlas_analysis_label} "
                f"{config_bool_string(p, 'atlas_no_plots', fallback=False)}"
            )

            pairwise_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} "
                f"{p.get('pairwise_gene_counts_dir', fallback='00_gene_counts')} "
                f"'{p.get('pairwise_gene_counts_files', fallback='auto')}' "
                f"{p.get('pairwise_output_subdir', fallback='02_decode_pairwise_correlation')} "
                f"{p.get('pairwise_analysis_label', fallback='auto')} "
                f"{config_bool_string(p, 'pairwise_no_plots', fallback=False)}"
            )
            
            gspf_array = build_array_spec(p['gspf_array_tasks'], p['gspf_parallel_tasks'])
            gspf_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} {p['gspf_intensity_threshold']} {p['gspf_spotfinding_method']} "
                f"{p['gspf_loading_mode']} {image_geom_args} {p['gspf_offset']}"
            )

            nuclei_reg_array = build_array_spec(p['nuclei_reg_array_tasks'], p['nuclei_reg_parallel_tasks'])
            nuclei_reg_args = format_named_args((
                ('project_root', p['project_root']),
                ('project_name', p['project_name']),
                ('reg_dir_suffix', reg_dir_suffix),
                ('offset', p['nuclei_reg_offset']),
                ('image_width', p['image_width']),
                ('image_depth', p['image_depth']),
                ('ref_round', p['ref_round']),
                ('channel_num', p['channel_num']),
                ('round_num', p['round_num']),
                ('input_format', p['nuclei_reg_input_format']),
                ('norm_out_format', p['nuclei_reg_norm_out_format']),
                ('aligned_round_outdir', p['nuclei_reg_aligned_round_outdir']),
                ('moving_round', p['nuclei_reg_moving_round']),
                ('channel_panel', p['nuclei_reg_channel_panel']),
                ('core_matlab_dir', p['nuclei_reg_core_matlab_dir']),
            ))

            run_prepare_layout = p.getboolean('run_prepare_layout', fallback=False)
            run_prepare_tile_config = p.getboolean('run_prepare_tile_config', fallback=False)
            run_fiji_stitch = p.getboolean('run_fiji_stitch', fallback=False)
            run_ashlar_stitch = p.getboolean('run_ashlar_stitch', fallback=False)
            run_prepare_shifted_layout = p.getboolean('run_prepare_shifted_layout', fallback=False)
            run_ashlar_stitch_mosaic = p.getboolean('run_ashlar_stitch_mosaic', fallback=False)
            run_fiji_stitch_mosaic = p.getboolean('run_fiji_stitch_mosaic', fallback=False)
            run_make_rgb_tif = p.getboolean('run_make_rgb_tif', fallback=False)
            run_mosaic_registration_python = p.getboolean('run_mosaic_registration_python', fallback=False)
            run_mosaic_registration_matlab = p.getboolean('run_mosaic_registration_matlab', fallback=False)
            run_mosaic_registration_compare = p.getboolean('run_mosaic_registration_compare', fallback=False)
            fov_enabled = any((
                p.getboolean('run_nuclei_registration', fallback=False),
                run_prepare_layout,
                run_prepare_tile_config,
                run_fiji_stitch,
                run_ashlar_stitch,
                run_prepare_shifted_layout,
                run_ashlar_stitch_mosaic,
                run_fiji_stitch_mosaic,
                run_make_rgb_tif,
                run_mosaic_registration_python,
                run_mosaic_registration_matlab,
                run_mosaic_registration_compare,
            ))

            prepare_layout_args = format_named_args((
                ('project_root', p['project_root']),
                ('project_name', p['project_name']),
                ('reg_dir_suffix', reg_dir_suffix),
                ('rawdata_round', p['prepare_layout_rawdata_round']),
                ('stitching_workdir', p['prepare_layout_stitching_workdir']),
                ('channel_mode', p['prepare_layout_channel_mode']),
                ('manifest_name', p['prepare_layout_manifest_name']),
                ('link_mode', p['prepare_layout_link_mode']),
                ('output_format', p['prepare_layout_output_format']),
                ('script_dir', p['FovIntegration']),
                ('conda_env', p['prepare_layout_conda_env']),
            ))

            prepare_tile_config_args = format_named_args((
                ('project_root', p['project_root']),
                ('project_name', p['project_name']),
                ('reg_dir_suffix', reg_dir_suffix),
                ('stitching_workdir', p['prepare_tile_config_stitching_workdir']),
                ('source_channel_dir', p['prepare_tile_config_source_channel_dir']),
                ('match_string', p['prepare_tile_config_match_string']),
                ('pixel_size_um', p['prepare_tile_config_pixel_size_um']),
                ('image_xy', p['prepare_tile_config_image_xy']),
                ('overlap_ratio', p['prepare_tile_config_overlap_ratio']),
                ('invert_y', p['prepare_tile_config_invert_y']),
                ('maf_file', p['prepare_tile_config_maf_file']),
                ('position_offset', p['prepare_tile_config_position_offset']),
                ('microscope', p['prepare_tile_config_microscope']),
                ('initial_config_name', p['prepare_tile_config_initial_config_name']),
                ('script_dir', p['FovIntegration']),
                ('conda_env', p['prepare_tile_config_conda_env']),
                ('run_fiji_fusion_preflight', p['prepare_tile_config_run_fiji_fusion_preflight']),
                ('fiji_fusion_preflight_report', p['prepare_tile_config_fiji_fusion_preflight_report']),
            ))

            fiji_stitch_work_dir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}/{p['fiji_stitch_working_dir']}"
            fiji_stitch_args = format_named_args((
                ('work_dir', fiji_stitch_work_dir),
                ('source_channel', p['fiji_stitch_source_channel']),
                ('grid_x', p['fiji_stitch_grid_x']),
                ('grid_y', p['fiji_stitch_grid_y']),
                ('first_index', p['fiji_stitch_first_index']),
                ('stitch_pattern', p['fiji_stitch_stitch_pattern']),
                ('initial_config_name', p['fiji_stitch_initial_config_name']),
                ('layout_file', p['fiji_stitch_layout_file']),
                ('registered_config_name', p['fiji_stitch_registered_config_name']),
                ('run_fiji_fusion_preflight', p['fiji_stitch_run_fiji_fusion_preflight']),
                ('fiji_fusion_preflight_report', p['fiji_stitch_fiji_fusion_preflight_report']),
                ('output_name', p['fiji_stitch_output_name']),
                ('output_textfile_name', p['fiji_stitch_output_textfile_name']),
                ('regression_threshold', p['fiji_stitch_regression_threshold']),
                ('max_avg_displacement_threshold', p['fiji_stitch_max_avg_displacement_threshold']),
                ('absolute_displacement_threshold', p['fiji_stitch_absolute_displacement_threshold']),
                ('fusion_method', p['fiji_stitch_fusion_method']),
                ('compute_overlap', p['fiji_stitch_compute_overlap']),
                ('subpixel_accuracy', p['fiji_stitch_subpixel_accuracy']),
                ('computation_parameters', p['fiji_stitch_computation_parameters']),
                ('image_output', p['fiji_stitch_image_output']),
                ('save_format', p['fiji_stitch_save_format']),
                ('script_dir', p['FovIntegration']),
                ('fiji_executable', p['fiji_executable']),
                ('conda_env', p['fiji_conda_env']),
                ('dry_run', 'false'),
            ))

            ashlar_stitch_args = format_named_args((
                ('project_root', p['project_root']),
                ('project_name', p['project_name']),
                ('reg_dir_suffix', reg_dir_suffix),
                ('source_channel_dir', p['ashlar_stitch_source_channel_dir']),
                ('stitching_round', p['ashlar_stitch_stitching_round']),
                ('config_name', p['ashlar_stitch_config_name']),
                ('registered_config_name', p['ashlar_stitch_registered_config_name']),
                ('stitch_result_dirname', p['ashlar_stitch_result_dirname']),
                ('output_prefix', p['ashlar_stitch_output_prefix']),
                ('make_3d', p['ashlar_stitch_make_3d']),
                ('rotate90', p['ashlar_stitch_rotate90']),
                ('rotate_positions', p['ashlar_stitch_rotate_positions']),
                ('pixel_size_um', p['ashlar_stitch_pixel_size_um']),
                ('max_shift_px', p['ashlar_stitch_max_shift_px']),
                ('filter_sigma', p['ashlar_stitch_filter_sigma']),
                ('stitch_alpha', p['ashlar_stitch_alpha']),
                ('max_error', p['ashlar_stitch_max_error']),
                ('slice_indices', p['ashlar_stitch_slice_indices']),
                ('script_dir', p['FovIntegration']),
                ('conda_env', p['ashlar_conda_env']),
            ))

            prepare_shifted_layout_args = format_named_args((
                ('project_root', p['project_root']),
                ('project_name', p['project_name']),
                ('reg_dir_suffix', reg_dir_suffix),
                ('stitching_workdir', p['prepare_shifted_layout_stitching_workdir']),
                ('rawdata_round', p['prepare_shifted_layout_rawdata_round']),
                ('channel_mode', p['prepare_shifted_layout_channel_mode']),
                ('registered_config_name', p['prepare_shifted_layout_registered_config_name']),
                ('shifted_config_name', p['prepare_shifted_layout_shifted_config_name']),
                ('registration_log_name', p['prepare_shifted_layout_registration_log_name']),
                ('output_format', p['prepare_shifted_layout_output_format']),
                ('rotate_shifts', p['prepare_shifted_layout_rotate_shifts']),
                ('shift_sign', p['prepare_shifted_layout_shift_sign']),
                ('script_dir', p['FovIntegration']),
                ('conda_env', p['ashlar_conda_env']),
            ))

            ashlar_mosaic_args = format_named_args((
                ('project_root', p['project_root']),
                ('project_name', p['project_name']),
                ('reg_dir_suffix', reg_dir_suffix),
                ('stitching_workdir', p['ashlar_mosaic_stitching_workdir']),
                ('channel_mode', p['ashlar_mosaic_channel_mode']),
                ('config_for_mosaic_stitch', p['ashlar_mosaic_config_for_mosaic_stitch']),
                ('channel_dir_prefix', p['ashlar_mosaic_channel_dir_prefix']),
                ('stitch_result_dirname', p['ashlar_mosaic_stitch_result_dirname']),
                ('output_prefix', p['ashlar_mosaic_output_prefix']),
                ('output_format', p['ashlar_mosaic_output_format']),
                ('rotate_images', p['ashlar_mosaic_rotate_images']),
                ('make_3d', p['ashlar_mosaic_make_3d']),
                ('pixel_size_um', p['ashlar_mosaic_pixel_size_um']),
                ('slice_indices', p['ashlar_mosaic_slice_indices']),
                ('script_dir', p['FovIntegration']),
                ('conda_env', p['ashlar_conda_env']),
            ))

            fiji_mosaic_work_dir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}/{p['fiji_mosaic_stitching_workdir']}"
            fiji_mosaic_args = format_named_args((
                ('work_dir', fiji_mosaic_work_dir),
                ('config_file', p['fiji_mosaic_config_file']),
                ('channel_mode', p['fiji_mosaic_channel_mode']),
                ('channel_names', p['fiji_mosaic_channel_names']),
                ('channel_dir_prefix', p['fiji_mosaic_channel_dir_prefix']),
                ('output_prefix', p['fiji_mosaic_output_prefix']),
                ('stitch_pattern', p['fiji_mosaic_stitch_pattern']),
                ('layout_file', p['fiji_mosaic_layout_file']),
                ('fusion_method', p['fiji_mosaic_fusion_method']),
                ('subpixel_accuracy', p['fiji_mosaic_subpixel_accuracy']),
                ('image_output', p['fiji_mosaic_image_output']),
                ('save_format', p['fiji_mosaic_save_format']),
                ('script_dir', p['FovIntegration']),
                ('fiji_executable', p['fiji_executable']),
                ('conda_env', p['fiji_conda_env']),
                ('dry_run', 'false'),
            ))

            rgb_tif_args = format_named_args((
                ('red_image', p['rgb_tif_red_image']),
                ('green_image', p['rgb_tif_green_image']),
                ('output_image', p['rgb_tif_output_image']),
                ('rescale_to_uint8', p['rgb_tif_rescale_to_uint8']),
                ('percentile_min', p['rgb_tif_percentile_min']),
                ('percentile_max', p['rgb_tif_percentile_max']),
                ('script_dir', p['FovIntegration']),
                ('conda_env', p['ashlar_conda_env']),
            ))

            mosaic_registration_common_args = (
                ('fixed_mosaic', p['mosaic_registration_fixed_mosaic']),
                ('moving_mosaic', p['mosaic_registration_moving_mosaic']),
                ('output_prefix', p['mosaic_registration_output_prefix']),
                ('script_dir', p['FovIntegration']),
                ('conda_env', p['mosaic_registration_conda_env']),
                ('overview_downsample', p['mosaic_registration_overview_downsample']),
                ('overview_block_px', p['mosaic_registration_overview_block_px']),
                ('roi_size_px', p['mosaic_registration_roi_size_px']),
                ('roi_count', p['mosaic_registration_roi_count']),
                ('min_valid_rois', p['mosaic_registration_min_valid_rois']),
                ('min_overlap_ratio', p['mosaic_registration_min_overlap_ratio']),
                ('max_roi_spread_px', p['mosaic_registration_max_roi_spread_px']),
                ('tile_size_px', p['mosaic_registration_tile_size_px']),
                ('interpolation_order', p['mosaic_registration_interpolation_order']),
                ('preview_downsample', p['mosaic_registration_preview_downsample']),
                ('compression', p['mosaic_registration_compression']),
                ('overwrite', p['mosaic_registration_overwrite']),
                ('dry_run', 'false'),
            )
            mosaic_registration_python_args = format_named_args(
                mosaic_registration_common_args + (
                    ('upsample_factor', p['mosaic_registration_upsample_factor']),
                )
            )
            mosaic_registration_matlab_args = format_named_args(
                mosaic_registration_common_args + (
                    ('dft_helper_dir', p['mosaic_registration_dft_helper_dir']),
                )
            )
            mosaic_registration_compare_args = format_named_args((
                ('python_json', f"{p['mosaic_registration_output_prefix']}.python.transform.json"),
                ('matlab_json', f"{p['mosaic_registration_output_prefix']}.matlab.transform.json"),
                ('output_prefix', p['mosaic_registration_output_prefix']),
                ('agreement_tolerance_px', p['mosaic_registration_agreement_tolerance_px']),
                ('fail_on_disagreement', p['mosaic_registration_fail_on_disagreement']),
                ('script_dir', p['FovIntegration']),
                ('conda_env', p['mosaic_registration_conda_env']),
                ('overwrite', p['mosaic_registration_overwrite']),
                ('dry_run', 'false'),
            ))


            dapi_cp_array = build_array_spec(p['dapi_cp_array_tasks'], p['dapi_cp_parallel_tasks'])
            dapi_cp_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} {p['ref_round']} {p['dapi_cp_diameter']} {p['dapi_cp_area_thresh']} {p['dapi_cp_offset']}"
            )

            cluMap_array = build_array_spec(p['cluMap_array_tasks'], p['cluMap_parallel_tasks'])
            cluMap_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} {p['ref_round']} {p['cluMap_offset']} \\\n"
                f"{p['cluMap_cell_num_thresh']} {p['cluMap_dapi_grid']} {p['cluMap_cell_radius']} {p['cluMap_pct_filter']} {p['cluMap_rotation']} {p['cluMap_extra_preprocess']} {p['cluMap_sub_Span']} {p['cluMap_expected_workers']} {p['cluMap_reads_filters']} {p['cluMap_overlap_percent']} {p['cluMap_dapi_suffix']} {p['cluMap_spot_csv_name']}"
            )

            # rna_restore 参数
            rna_restore_input_dir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}"
            rna_restore_array = build_array_spec(p['rna_restore_array_tasks'], p['rna_restore_parallel_tasks'])
            rna_restore_args = (
                f"{rna_restore_input_dir} {p['rna_restore_segout_dir']} \\\n"
                f"{p['rna_restore_raw_csv']} \\\n"
                f"{p['rna_restore_remained_csv']} \\\n"
                f"{p['rna_restore_output_csv']} \\\n"
                f"{p['rna_restore_img_c']} {p['rna_restore_img_r']} {p['rna_restore_rotation_deg']} {p['rna_restore_tolerance']} {p['rna_restore_offset']}"
            )



            # cellreads_integration 参数
            cr_output_dir = f"{p['project_root']}/{p['project_name']}/03_integration{p['regDir_suffix']}/cr_integ_{p['cr_suffix']}"
            cr_input_dir = f"{p['project_root']}/{p['project_name']}/02_registration{p['regDir_suffix']}"
            cr_args = (
                f"{p['image_width']} \\\n"
                f"{cr_input_dir} \\\n"
                f"{cr_output_dir} \\\n"
                f"{p['cr_seg_method']} {p['cr_if_dirname']} {p['cr_suffix']} \\\n"
                f"{p['cr_core_script']}"
            )

            # csv2CountMatrix 参数
            c2cm_args = (
                f"{p['c2cm_core_script']} \\\n"
                f"{cr_output_dir} \\\n"
            )

            
            # entropyTest 参数
            et_array = build_array_spec(p['et_array_tasks'], p['et_parallel_tasks'])
            et_outdir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}/{p['et_prefix']}"   
            et_args =(
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix}"
                f" {p['et_spot_name']} {p['et_image_name']} {et_outdir} {p['et_process_rounds']} {p['et_extend_size']} {p['et_prefix']} {p['et_offset']}"
            )

            # plotback
            pb_input_dir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}/"
            pb_array = build_array_spec(p['pb_array_tasks'], p['pb_parallel_tasks'])
            pb_args = (
                f"{pb_input_dir} \\\n"
                f"{p['pb_csv_name']} {p['pb_offset']} {p['regDir_suffix']}"
            )

            # plotbackv3 参数
            if p['regDir_suffix'] == p['pbv3_r_dir']:
                pbv3_r_dir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}/"
            else:
                pbv3_r_dir = f"{p['project_root']}/{p['project_name']}/{p['pbv3_r_dir']}/"
            # pbv3_g_dir pbv3_b_dir
            if p['regDir_suffix'] == p['pbv3_g_dir']:
                pbv3_g_dir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}/"
            else:
                pbv3_g_dir = f"{p['project_root']}/{p['project_name']}/{p['pbv3_g_dir']}/"
            if p['regDir_suffix'] == p['pbv3_b_dir']:
                pbv3_b_dir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}/"
            else:
                pbv3_b_dir = f"{p['project_root']}/{p['project_name']}/{p['pbv3_b_dir']}/"
            pbv3_output_dir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}/"
            pbv3_prefix = p['regDir_suffix']

            pbv3_array = build_array_spec(p['pbv3_array_tasks'], p['pbv3_parallel_tasks'])
            pbv3_args = (
                f"{pbv3_r_dir} \\\n"
                f"{p['pbv3_r_file_suffix']} \\\n"
                f"{pbv3_g_dir} \\\n"
                f"{p['pbv3_g_file_suffix']} \\\n"
                f"{pbv3_b_dir} \\\n"
                f"{p['pbv3_b_file_suffix']} \\\n"
                f"{pbv3_output_dir} \\\n"
                f"{pbv3_prefix} \\\n"
                f"{p['pbv3_r_file_class']} {p['pbv3_g_file_class']} {p['pbv3_b_file_class']} \\\n"
                f"{p['ref_round']} {p['pbv3_offset']} \\\n"
            )

            # copymat 参数
            cpm_input_dir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}/"
            cpm_out_dirname = str(p['cpm_filename']).split('_')[0]
            cpm_args = (
                f"{cpm_input_dir} \\\n"
                f"{cpm_out_dirname} {p['cpm_filename']} \\\n"
            )

            # ssim 参数
            ssim_input_dir = f"{cpm_input_dir}/matDir/{cpm_out_dirname}/"
            ssim_array = build_array_spec(p['ssim_array_tasks'], p['ssim_parallel_tasks'])
            ssim_args = (
                f"{ssim_input_dir} {p['ssim_offset']} \\\n"
            )



        except KeyError as e:
            print(f"Error: 关键参数 {e} 在 [{section_name}] 或 [DEFAULT] 中没有找到。", file=sys.stderr)
            sys.exit(1)
        except configparser.InterpolationSyntaxError as e:
            print(f"Error: INI 文件插值错误: {e}", file=sys.stderr)
            print("请检查您的 %(...)s 变量是否都定义在了 [DEFAULT] 节中。", file=sys.stderr)
            sys.exit(1)

        # --- 4. 打印 Job 头部 ---

        if p.getboolean('run_sparse_deconv'):
            print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) - Sparse Deconvolution ---")
            print(f"echo \"Starting Job {job_counter}: {p['job_suffix']} (Sparse Deconvolution)\"")
            print(f"mkdir -p {spd_work_dir}")
            print(f"cd {spd_work_dir} || {{ echo 'Failed to cd into {spd_work_dir}'; exit 1; }}\n")
            
            # Step 0: 生成 filelist.txt
            print(f"find {sd_input_dir} \\")
            print(f"-type f \\( -name \"*ch00.tif\" -o -name \"*ch01.tif\" -o -name \"*ch02.tif\" -o -name \"*ch03.tif\" \\) \\")
            print(f"| sort -V > {filelist_path.split('/')[-1]}\n") # 只打印 filelist.txt

        if p.getboolean('run_sparse_deconv'):

            total_tasks = int(p['sd_array_tasks'])
            max_chunk_size = 1000
            sd_partition = p['sd_partition']


            if total_tasks <= max_chunk_size:
                # --- 逻辑 1: 任务数 <= 1000，使用 ini 中的静态 offset ---
                sd_args_simple = f"{sd_args_base} {p['sd_offset']}"
                cmd_sd = f"sbatch --array={sd_array} -p {sd_partition} {dependency_str} {p['script_sparse_deconv']} \\\n{sd_args_simple}"
                print(f"# Submit step: Sparse Deconvolution (Single Job)")
                print(f"{JOB_OUT_VAR}=$(\\")
                print(f"{cmd_sd})")
                print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
                print(f"echo \"Submitted Step(sd): ${{{JOB_ID_VAR}}}\"\n")
                dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"
            
            else:
                # --- 逻辑 2: 任务数 > 1000，分片提交并使用动态 offset ---
                parallel_limit = p['sd_parallel_tasks']
                
                # 构建不含 --array 和 offset 的基础 sbatch 命令
                cmd_sd_sbatch_base = f"sbatch {dependency_str} {p['script_sparse_deconv']} \\\n"
                
                print(f"# Submit step:  Sparse Deconvolution (Chunked for {total_tasks} tasks)")
                print(f"SPD_JOB_IDS=()") # 初始化 Bash 数组
                
                start = 1
                while start <= total_tasks:
                    end = min(start + max_chunk_size - 1, total_tasks)

                    
                    # 计算此分片专属的动态 offset
                    dynamic_offset = start - 1 + int(p['sd_offset'])
                    
                    # 将动态 offset 拼接到 sd_args_base
                    sd_args_chunk = f"{sd_args_base} {dynamic_offset}"


                    array_range = f"{start - dynamic_offset + int(p['sd_offset'])}-{end - dynamic_offset + int(p['sd_offset'])}"
                    array_string = build_array_option(array_range, parallel_limit)
                    # 构建此分片的完整 sbatch 命令
                    cmd_sd_chunk = f"""{cmd_sd_sbatch_base.replace('sbatch', f'sbatch {array_string} -p {p["sd_partition"]}', 1)}{sd_args_chunk}"""

                    print(f"# Submitting SPD Chunk {start}-{end} with offset {dynamic_offset}")
                    print(f"{JOB_OUT_VAR}=$(\\")
                    print(f"{cmd_sd_chunk})")
                    print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
                    print(f"echo \"Submitted Step(SPD) Chunk {start}-{end}: ${{{JOB_ID_VAR}}}\"")
                    print(f"SPD_JOB_IDS+=(${{{JOB_ID_VAR}}})") 
                    print("")
                    
                    start = end + 1
                
                # 循环结束后，在 Bash 中创建依赖列表
                print(f"# Create dependency list for all SPD chunks")
                print(f"SPD_DEP_LIST=$(IFS=:; echo \"${{SPD_JOB_IDS[*]}}\")")
                print(f"echo \"Waiting on all SPD chunks: ${{SPD_DEP_LIST}}\"\n")
                
                dependency_str = f"--dependency=afterok:${{SPD_DEP_LIST}}"

        # --- 上游分析流程
        if p.getboolean('run_global_reg') or p.getboolean('run_local_reg') or p.getboolean('run_stitch') or p.getboolean('run_global_spf'):
            print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) ---")
            print(f"echo \"Starting Job {job_counter}: {p['job_suffix']}\"")
            print(f"mkdir -p {work_dir}")
            print(f"cd {work_dir} || {{ echo 'Failed to cd into {work_dir}'; exit 1; }}\n")


        # --- 上游分析流程 GLobal Registration (run_global_reg) ---
        if p.getboolean('run_global_reg'):
            cmd_s1 = f"sbatch --array={gr_array} -p {p['gr_partition']} -c {p['gr_cpus']} {dependency_str} {p['script_global_reg']} \\\n{gr_args}"
            print(f"# Submit step: Global Registration")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s1})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(GR): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}" 

        # ======================================================
        # --- 【关键修正 2/3】 ---
        # --- 自动分片逻辑: Local Registration ---
        # ======================================================
        if p.getboolean('run_local_reg'):
            total_tasks = int(p['lr_array_tasks'])
            max_chunk_size = 1000
            
            if total_tasks <= max_chunk_size:
                # --- 逻辑 1: 任务数 <= 1000，使用 ini 中的静态 offset ---
                
                # 将静态 offset 拼接到 lr_args_base
                lr_args_simple = f"{lr_args_base} {p['lr_offset']}"
                
                cmd_s2 = f"sbatch --array={lr_array} -p {p['lr_partition']} -c {p['lr_cpus']} {dependency_str} {p['script_local_reg']} \\\n{lr_args_simple}"
                print(f"# Submit step: Local Registration (Single Job)")
                print(f"{JOB_OUT_VAR}=$(\\")
                print(f"{cmd_s2})")
                print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
                print(f"echo \"Submitted Step(LR): ${{{JOB_ID_VAR}}}\"\n")
                dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"
            
            else:
                # --- 逻辑 2: 任务数 > 1000，分片提交并使用动态 offset ---
                parallel_limit = p['lr_parallel_tasks']
                
                # 构建不含 --array 和 offset 的基础 sbatch 命令
                cmd_s2_sbatch_base = f"sbatch {dependency_str} {p['script_local_reg']} \\\n"
                
                print(f"# Submit step: Local Registration (Chunked for {total_tasks} tasks)")
                print(f"LR_JOB_IDS=()") # 初始化 Bash 数组
                
                start = 1
                while start <= total_tasks:
                    end = min(start + max_chunk_size - 1, total_tasks)

                    
                    # 计算此分片专属的动态 offset
                    dynamic_offset = start - 1 + int(p['lr_offset'])
                    
                    # 将动态 offset 拼接到 lr_args_base
                    lr_args_chunk = f"{lr_args_base} {dynamic_offset}"


                    array_range = f"{start - dynamic_offset + int(p['lr_offset'])}-{end - dynamic_offset + int(p['lr_offset'])}"
                    array_string = build_array_option(array_range, parallel_limit)
                    # 构建此分片的完整 sbatch 命令
                    cmd_s2_chunk = f"""{cmd_s2_sbatch_base.replace('sbatch', f'sbatch {array_string} -p {p["lr_partition"]} -c {p["lr_cpus"]}', 1)}{lr_args_chunk}"""

                    print(f"# Submitting LR Chunk {start}-{end} with offset {dynamic_offset}")
                    print(f"{JOB_OUT_VAR}=$(\\")
                    print(f"{cmd_s2_chunk})")
                    print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
                    print(f"echo \"Submitted Step(LR) Chunk {start}-{end}: ${{{JOB_ID_VAR}}}\"")
                    print(f"LR_JOB_IDS+=(${{{JOB_ID_VAR}}})")
                    print("")
                    
                    start = end + 1
                
                # 循环结束后，在 Bash 中创建依赖列表
                print(f"# Create dependency list for all LR chunks")
                print(f"LR_DEP_LIST=$(IFS=:; echo \"${{LR_JOB_IDS[*]}}\")")
                print(f"echo \"Waiting on all LR chunks: ${{LR_DEP_LIST}}\"\n")
                
                dependency_str = f"--dependency=afterok:${{LR_DEP_LIST}}"


        if p.getboolean('run_stitch'):
            cmd_s3 = f"sbatch --array={ls_array} -p {p['ls_partition']} -c {p['ls_cpus']} {dependency_str} {p['script_stitch']} \\\n{ls_args}"
            print(f"# Submit step: Local Stitch")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s3})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(LS): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if p.getboolean('run_global_spf'):
            cmd_s5 = f"sbatch --array={gspf_array} -p {p['gspf_partition']} -c {p['gspf_cpus']} {dependency_str} {p['script_global_spf']} \\\n{gspf_args}"
            print(f"# Submit step: Global Spotfinding (bak01)")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s5})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(Global SPF): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"



        # 仅当运行 Spot Finding 或 Concat 时才设置 spf_output 目录
        if p.getboolean('run_genelist') or p.getboolean('run_spotFinding') or p.getboolean('run_spotConcat'):
            print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) - Spot Finding ---")
            print(f"echo \"Starting Job {job_counter}: {p['job_suffix']} (Spot Finding)\"")
            print(f"mkdir -p {spf_work_dir}")
            print(f"cd {spf_work_dir} || {{ echo 'Failed to cd into {spf_work_dir}'; exit 1; }}\n")
            
        if p.getboolean('run_genelist'):
            cmd_s8 = f"sbatch {dependency_str} {p['script_genelist']} \\\n{gl_args}"
            print(f"# Submit step: Gene List Generation")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s8})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(GL): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"
        
        if p.getboolean('run_spotFinding'):

            total_tasks = int(p['spf_array_tasks'])
            max_chunk_size = 1000
            spf_partition = p['spf_partition']


            if total_tasks <= max_chunk_size:
                # --- 逻辑 1: 任务数 <= 1000，使用 ini 中的静态 offset ---
                spf_args_simple = f"{spf_args_base} {p['spf_offset']}"
                cmd_spf = f"sbatch --array={spf_array} -p {spf_partition} {dependency_str} {p['script_spotFinding']} \\\n{spf_args_simple}"
                print(f"# Submit step: Spotiflow-based spots Detection (Single Job)")
                print(f"{JOB_OUT_VAR}=$(\\")
                print(f"{cmd_spf})")
                print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
                print(f"echo \"Submitted Step(spf): ${{{JOB_ID_VAR}}}\"\n")
                dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"
            
            else:
                # --- 逻辑 2: 任务数 > 1000，分片提交并使用动态 offset ---
                parallel_limit = p['spf_parallel_tasks']
                
                # 构建不含 --array 和 offset 的基础 sbatch 命令
                cmd_spf_sbatch_base = f"sbatch {dependency_str} {p['script_spotFinding']} \\\n"
                
                print(f"# Submit step:  Spotiflow-based spots Detection (Chunked for {total_tasks} tasks)")
                print(f"SPF_JOB_IDS=()") # 初始化 Bash 数组
                
                start = 1
                while start <= total_tasks:
                    end = min(start + max_chunk_size - 1, total_tasks)

                    
                    # 计算此分片专属的动态 offset
                    dynamic_offset = start - 1 + int(p['spf_offset'])
                    
                    # 将动态 offset 拼接到 spf_args_base
                    spf_args_chunk = f"{spf_args_base} {dynamic_offset}"


                    array_range = f"{start - dynamic_offset + int(p['spf_offset'])}-{end - dynamic_offset + int(p['spf_offset'])}"
                    array_string = build_array_option(array_range, parallel_limit)
                    # 构建此分片的完整 sbatch 命令
                    # cmd_spf_chunk = f"{cmd_spf_sbatch_base.replace('sbatch', f'sbatch {array_string} -p {p['spf_partition']}', 1)}{spf_args_chunk}"
                    cmd_spf_chunk = f"""{cmd_spf_sbatch_base.replace('sbatch', f"sbatch {array_string} -p {p['spf_partition']}", 1)}{spf_args_chunk}"""

                    # # 1. 先提取变量
                    # partition = p['spf_partition']
                    # # 2. 构造替换字符串
                    # new_sbatch = f"sbatch {array_string} -p {partition}"
                    # # 3. 执行替换并拼接
                    # cmd_spf_chunk = cmd_spf_sbatch_base.replace('sbatch', new_sbatch, 1) + spf_args_chunk


                    print(f"# Submitting SPF Chunk {start}-{end} with offset {dynamic_offset}")
                    print(f"{JOB_OUT_VAR}=$(\\")
                    print(f"{cmd_spf_chunk})")
                    print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
                    print(f"echo \"Submitted Step(SPF) Chunk {start}-{end}: ${{{JOB_ID_VAR}}}\"")
                    print(f"SPF_JOB_IDS+=(${{{JOB_ID_VAR}}})") 
                    print("")
                    
                    start = end + 1
                
                # 循环结束后，在 Bash 中创建依赖列表
                print(f"# Create dependency list for all SPF chunks")
                print(f"SPF_DEP_LIST=$(IFS=:; echo \"${{SPF_JOB_IDS[*]}}\")")
                print(f"echo \"Waiting on all SPF chunks: ${{SPF_DEP_LIST}}\"\n")
                
                dependency_str = f"--dependency=afterok:${{SPF_DEP_LIST}}"
        
        # --- Spot Concat 流程 (run_spotConcat) ---
        if p.getboolean('run_spotConcat'):
            # Concat 是单步任务，依赖于 Spot Finding (如果 Spot Finding 运行了)
            cmd_concat = f"sbatch {dependency_str} {p['script_spotConcat']} \\\n{spf_concat_args}"
            
            print(f"# Submit step: Spot Concatenation")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_concat})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(Concat): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if p.getboolean('run_decoding'):
            print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) ---")
            print(f"echo \"Starting Job {job_counter}: {p['job_suffix']}\"")
            print(f"mkdir -p {work_dir}")
            print(f"cd {work_dir} || {{ echo 'Failed to cd into {work_dir}'; exit 1; }}\n")
        
        if p.getboolean('run_decoding'):
            cmd_s4 = f"sbatch --array={gd_array} -p {p['gd_partition']} -c {p['gd_cpus']} {dependency_str} {p['script_decoding']} \\\n{gd_args}"
            print(f"# Submit step: Global Decoding")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s4})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(GD): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if p.getboolean('run_extract_gene_counts', fallback=False):
            if not p.getboolean('run_decoding'):
                print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) - Extract Gene Counts ---")
                print(f"echo \"Starting Job {job_counter}: {p['job_suffix']} (Extract Gene Counts)\"")
                print(f"mkdir -p {work_dir}")
                print(f"cd {work_dir} || {{ echo 'Failed to cd into {work_dir}'; exit 1; }}\n")
            cmd_egc = f"sbatch -p {p.get('egc_partition', fallback='C64M512G')} -c {p.get('egc_cpus', fallback='4')} --mem {p.get('egc_mem', fallback='32G')} {dependency_str} {p['script_extract_gene_counts']} \\\n{egc_args}"
            print(f"# Submit step: Extract Gene Counts")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_egc})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(EGC): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if p.getboolean('run_atlas_correlation', fallback=False) or p.getboolean('run_decode_pairwise_correlation', fallback=False):
            if not p.getboolean('run_decoding') and not p.getboolean('run_extract_gene_counts', fallback=False):
                print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) - Correlation Analysis ---")
                print(f"echo \"Starting Job {job_counter}: {p['job_suffix']} (Correlation Analysis)\"")
                print(f"mkdir -p {work_dir}")
                print(f"cd {work_dir} || {{ echo 'Failed to cd into {work_dir}'; exit 1; }}\n")

            correlation_dependency_str = dependency_str
            if dependency_str == f"--dependency=afterok:${{{JOB_ID_VAR}}}":
                print(f"CORR_PARENT_JOB_ID=${{{JOB_ID_VAR}}}")
                correlation_dependency_str = "--dependency=afterok:${CORR_PARENT_JOB_ID}"

            if p.getboolean('run_atlas_correlation', fallback=False):
                cmd_atlas = f"sbatch -p {p.get('atlas_partition', fallback='C64M512G')} -c {p.get('atlas_cpus', fallback='4')} --mem {p.get('atlas_mem', fallback='32G')} {correlation_dependency_str} {p['script_atlas_correlation']} \\\n{atlas_args}"
                print(f"# Submit step: Atlas Correlation")
                print(f"{JOB_OUT_VAR}=$(\\")
                print(f"{cmd_atlas})")
                print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
                print(f"echo \"Submitted Step(Atlas Corr): ${{{JOB_ID_VAR}}}\"\n")

            if p.getboolean('run_decode_pairwise_correlation', fallback=False):
                cmd_pairwise = f"sbatch -p {p.get('pairwise_partition', fallback='C64M512G')} -c {p.get('pairwise_cpus', fallback='4')} --mem {p.get('pairwise_mem', fallback='32G')} {correlation_dependency_str} {p['script_decode_pairwise_correlation']} \\\n{pairwise_args}"
                print(f"# Submit step: Decode Pairwise Correlation")
                print(f"{JOB_OUT_VAR}=$(\\")
                print(f"{cmd_pairwise})")
                print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
                print(f"echo \"Submitted Step(Decode Pairwise Corr): ${{{JOB_ID_VAR}}}\"\n")


        if fov_enabled:
            print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) - FOV integration ---")
            print(f"echo \"Starting Job {job_counter}: {p['job_suffix']} (FOV integration)\"")
            print(f"mkdir -p {stitch_work_dir}")
            print(f"cd {stitch_work_dir} || {{ echo 'Failed to cd into {stitch_work_dir}'; exit 1; }}\n")

        if p.getboolean('run_nuclei_registration'):
            cmd_s6 = f"sbatch --parsable --array={nuclei_reg_array} -p {p['nuclei_reg_partition']} -c {p['nuclei_reg_cpus']} {dependency_str} {shlex.quote(p['script_nuclei_registration'])} \\\n{nuclei_reg_args}"
            print("# Submit step: Nuclei-based Registration")
            print(f"{JOB_ID_VAR}=$(\\")
            print(f"{cmd_s6})")
            print(f"{JOB_ID_VAR}=${{{JOB_ID_VAR}%%;*}}")
            print(f"echo \"Submitted Step(Nuclei-based Registration): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if run_prepare_layout:
            cmd_prepare_layout = f"sbatch --parsable -p {p['prepare_layout_partition']} -c {p['prepare_layout_cpus']} {dependency_str} {shlex.quote(p['script_prepare_layout'])} \\\n{prepare_layout_args}"
            print("# Submit step: Prepare Layout")
            print(f"{JOB_ID_VAR}=$(\\")
            print(f"{cmd_prepare_layout})")
            print(f"{JOB_ID_VAR}=${{{JOB_ID_VAR}%%;*}}")
            print(f"echo \"Submitted Step(Prepare Layout): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if run_prepare_tile_config:
            cmd_prepare_tile_config = f"sbatch --parsable -p {p['prepare_tile_config_partition']} -c {p['prepare_tile_config_cpus']} {dependency_str} {shlex.quote(p['script_prepare_tile_config'])} \\\n{prepare_tile_config_args}"
            print("# Submit step: Prepare TileConfiguration")
            print(f"{JOB_ID_VAR}=$(\\")
            print(f"{cmd_prepare_tile_config})")
            print(f"{JOB_ID_VAR}=${{{JOB_ID_VAR}%%;*}}")
            print(f"echo \"Submitted Step(Prepare TileConfiguration): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if run_fiji_stitch:
            cmd_fiji_stitch = f"sbatch --parsable -p {p['fiji_stitch_partition']} -c {p['fiji_stitch_cpus']} {dependency_str} {shlex.quote(p['script_fiji_stitch'])} \\\n{fiji_stitch_args}"
            print("# Submit step: Fiji Stitch")
            print(f"{JOB_ID_VAR}=$(\\")
            print(f"{cmd_fiji_stitch})")
            print(f"{JOB_ID_VAR}=${{{JOB_ID_VAR}%%;*}}")
            print(f"echo \"Submitted Step(Fiji Stitch): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if run_ashlar_stitch:
            cmd_ashlar_stitch = f"sbatch --parsable -p {p['ashlar_stitch_partition']} -c {p['ashlar_stitch_cpus']} {dependency_str} {shlex.quote(p['script_ashlar_stitch'])} \\\n{ashlar_stitch_args}"
            print("# Submit step: Ashlar Stitch")
            print(f"{JOB_ID_VAR}=$(\\")
            print(f"{cmd_ashlar_stitch})")
            print(f"{JOB_ID_VAR}=${{{JOB_ID_VAR}%%;*}}")
            print(f"echo \"Submitted Step(Ashlar Stitch): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if run_prepare_shifted_layout:
            cmd_prepare_shifted_layout = f"sbatch --parsable -p {p['prepare_shifted_layout_partition']} -c {p['prepare_shifted_layout_cpus']} {dependency_str} {shlex.quote(p['script_prepare_shifted_layout'])} \\\n{prepare_shifted_layout_args}"
            print("# Submit step: Prepare Shifted Layout")
            print(f"{JOB_ID_VAR}=$(\\")
            print(f"{cmd_prepare_shifted_layout})")
            print(f"{JOB_ID_VAR}=${{{JOB_ID_VAR}%%;*}}")
            print(f"echo \"Submitted Step(Prepare Shifted Layout): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if run_ashlar_stitch_mosaic:
            cmd_ashlar_mosaic = f"sbatch --parsable -p {p['ashlar_mosaic_partition']} -c {p['ashlar_mosaic_cpus']} {dependency_str} {shlex.quote(p['script_ashlar_stitch_mosaic'])} \\\n{ashlar_mosaic_args}"
            print("# Submit step: Ashlar Stitch Mosaic")
            print(f"{JOB_ID_VAR}=$(\\")
            print(f"{cmd_ashlar_mosaic})")
            print(f"{JOB_ID_VAR}=${{{JOB_ID_VAR}%%;*}}")
            print(f"echo \"Submitted Step(Ashlar Stitch Mosaic): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if run_fiji_stitch_mosaic:
            cmd_fiji_mosaic = f"sbatch --parsable -p {p['fiji_mosaic_partition']} -c {p['fiji_mosaic_cpus']} {dependency_str} {shlex.quote(p['script_fiji_stitch_mosaic'])} \\\n{fiji_mosaic_args}"
            print("# Submit step: Fiji Stitch Mosaic")
            print(f"{JOB_ID_VAR}=$(\\")
            print(f"{cmd_fiji_mosaic})")
            print(f"{JOB_ID_VAR}=${{{JOB_ID_VAR}%%;*}}")
            print(f"echo \"Submitted Step(Fiji Stitch Mosaic): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if run_make_rgb_tif:
            cmd_rgb_tif = f"sbatch --parsable -p {p['rgb_tif_partition']} -c {p['rgb_tif_cpus']} {dependency_str} {shlex.quote(p['script_make_rgb_tif'])} \\\n{rgb_tif_args}"
            print("# Submit step: Make RGB TIF")
            print(f"{JOB_ID_VAR}=$(\\")
            print(f"{cmd_rgb_tif})")
            print(f"{JOB_ID_VAR}=${{{JOB_ID_VAR}%%;*}}")
            print(f"echo \"Submitted Step(Make RGB TIF): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if run_mosaic_registration_python or run_mosaic_registration_matlab or run_mosaic_registration_compare:
            registration_log_dirs = []
            if run_mosaic_registration_python:
                registration_log_dirs.append('logs025_mosaic_registration')
            if run_mosaic_registration_matlab:
                registration_log_dirs.append('logs026_mosaic_registration')
            if run_mosaic_registration_compare:
                registration_log_dirs.append('logs028_mosaic_registration')
            print("mkdir -p " + " ".join(registration_log_dirs))
            registration_parent_dependency = dependency_str
            registration_job_vars = []

            if run_mosaic_registration_python:
                cmd_mosaic_python = f"sbatch --parsable -p {p['mosaic_registration_python_partition']} -c {p['mosaic_registration_python_cpus']} {registration_parent_dependency} {shlex.quote(p['script_mosaic_registration_python'])} \\\n{mosaic_registration_python_args}"
                print("# Submit step: Mosaic Registration Python")
                print("MOSAIC_PY_JOB_ID=$(\\")
                print(f"{cmd_mosaic_python})")
                print("MOSAIC_PY_JOB_ID=${MOSAIC_PY_JOB_ID%%;*}")
                print('echo "Submitted Step(Mosaic Registration Python): ${MOSAIC_PY_JOB_ID}"\n')
                registration_job_vars.append('MOSAIC_PY_JOB_ID')

            if run_mosaic_registration_matlab:
                cmd_mosaic_matlab = f"sbatch --parsable -p {p['mosaic_registration_matlab_partition']} -c {p['mosaic_registration_matlab_cpus']} {registration_parent_dependency} {shlex.quote(p['script_mosaic_registration_matlab'])} \\\n{mosaic_registration_matlab_args}"
                print("# Submit step: Mosaic Registration Matlab")
                print("MOSAIC_MATLAB_JOB_ID=$(\\")
                print(f"{cmd_mosaic_matlab})")
                print("MOSAIC_MATLAB_JOB_ID=${MOSAIC_MATLAB_JOB_ID%%;*}")
                print('echo "Submitted Step(Mosaic Registration Matlab): ${MOSAIC_MATLAB_JOB_ID}"\n')
                registration_job_vars.append('MOSAIC_MATLAB_JOB_ID')

            if registration_job_vars:
                registration_dependency = "--dependency=afterok:" + ":".join(
                    f"${{{name}}}" for name in registration_job_vars
                )
            else:
                registration_dependency = registration_parent_dependency

            if run_mosaic_registration_compare:
                cmd_mosaic_compare = f"sbatch --parsable -p {p['mosaic_registration_compare_partition']} -c {p['mosaic_registration_compare_cpus']} {registration_dependency} {shlex.quote(p['script_mosaic_registration_compare'])} \\\n{mosaic_registration_compare_args}"
                print("# Submit step: Compare Mosaic Registration")
                print("MOSAIC_COMPARE_JOB_ID=$(\\")
                print(f"{cmd_mosaic_compare})")
                print("MOSAIC_COMPARE_JOB_ID=${MOSAIC_COMPARE_JOB_ID%%;*}")
                print('echo "Submitted Step(Compare Mosaic Registration): ${MOSAIC_COMPARE_JOB_ID}"\n')
                dependency_str = "--dependency=afterok:${MOSAIC_COMPARE_JOB_ID}"
            elif registration_job_vars:
                dependency_str = registration_dependency

        if p.getboolean('run_dapi_cellpose'):
            print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) - DAPI Cellpose Segmentation ---")
            print(f"echo \"Starting Job {job_counter}: {p['job_suffix']} (DAPI Cellpose Segmentation)\"")
            print(f"mkdir -p {seg_work_dir}")
            print(f"cd {seg_work_dir} || {{ echo 'Failed to cd into {seg_work_dir}'; exit 1; }}\n")

            cmd_s8 = f"sbatch --array={dapi_cp_array} -p {p['dapi_cp_partition']} {dependency_str} {p['script_dapi_cellpose']} \\\n{dapi_cp_args}"
            print(f"# Submit step: DAPI Cellpose Segmentation")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s8})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(DAPI Cellpose): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if p.getboolean('run_clustermap'):
            print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) - ClusterMap Segmentation ---")
            print(f"echo \"Starting Job {job_counter}: {p['job_suffix']} (ClusterMap Segmentation)\"")
            print(f"mkdir -p {seg_work_dir}")
            print(f"cd {seg_work_dir} || {{ echo 'Failed to cd into {seg_work_dir}'; exit 1; }}\n")

            cmd_s9 = f"sbatch --array={cluMap_array} -p {p['cluMap_partition']} -c {p['cluMap_cpus']} {dependency_str} {p['script_clustermap']} \\\n{cluMap_args}"
            print(f"# Submit step: ClusterMap Segmentation")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s9})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(ClusterMap): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if p.getboolean('run_rna_restore'):
            print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) - RNA Restoration ---")
            print(f"echo \"Starting Job {job_counter}: {p['job_suffix']} (RNA Restoration)\"")
            print(f"mkdir -p {seg_work_dir}")
            print(f"cd {seg_work_dir} || {{ echo 'Failed to cd into {seg_work_dir}'; exit 1; }}\n")

            cmd_s10 = f"sbatch --array={rna_restore_array} -p {p['rna_restore_partition']} -c {p['rna_restore_cpus']} --mem {p['rna_restore_mem']} {dependency_str} {p['script_rna_restore']} \\\n{rna_restore_args}"
            print(f"# Submit step: RNA Restoration")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s10})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(RNA Restoration): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if p.getboolean('run_cellreads_integration') or p.getboolean('run_csv2CountMatrix'):
            print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) - CellReads Integration ---")
            print(f"echo \"Starting Job {job_counter}: {p['job_suffix']} (CellReads Integration)\"")
            print(f"mkdir -p {integ_work_dir}")
            print(f"cd {integ_work_dir} || {{ echo 'Failed to cd into {integ_work_dir}'; exit 1; }}\n")

        if p.getboolean('run_cellreads_integration'):
            cmd_s10 = f"sbatch -p {p['cr_partition']} -c {p['cr_cpus']} {dependency_str} {p['script_cellreads_integration']} \\\n{cr_args}"
            print(f"# Submit step: CellReads Integration")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s10})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(CellReads Integration): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"
        
        if p.getboolean('run_csv2CountMatrix'):
            cmd_s11 = f"sbatch -p {p['c2cm_partition']} -c {p['c2cm_cpus']} --mem {p['c2cm_mem']} {dependency_str} {p['script_csv2CountMatrix']} \\\n{c2cm_args}"
            print(f"# Submit step: CSV to Count Matrix")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s11})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(CSV to Count Matrix): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"


        # if p.getboolean('run_entropyTest'):
        #     print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) ---")
        #     print(f"echo \"Starting Job {job_counter}: {p['job_suffix']}\"")
        #     print(f"mkdir -p {work_dir}")
        #     print(f"cd {work_dir} || {{ echo 'Failed to cd into {work_dir}'; exit 1; }}\n")

        #     cmd_s10 = f"sbatch --array={et_array} -p {p['et_partition']} -c {p['et_cpus']} {dependency_str} {p['script_entropyTest']} \\\n{et_args}"
        #     print(f"# Submit step: Entropy Test")
        #     print(f"{JOB_OUT_VAR}=$(\\")
        #     print(f"{cmd_s10})")
        #     print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
        #     print(f"echo \"Submitted Step(Entropy Test): ${{{JOB_ID_VAR}}}\"\n")
        #     dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if p.getboolean('run_entropyTest'):
            print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) ---")
            print(f"echo \"Starting Job {job_counter}: {p['job_suffix']}\"")
            print(f"mkdir -p {work_dir}")
            print(f"cd {work_dir} || {{ echo 'Failed to cd into {work_dir}'; exit 1; }}\n")

            cmd_s10 = f"sbatch --array={et_array} -p {p['et_partition']} -c {p['et_cpus']} {dependency_str} {p['script_entropyTest']} \\\n{et_args}"
            print(f"# Submit step: Entropy Test")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s10})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(Entropy Test): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"
        
        if p.getboolean('run_plotback'):
            print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) ---")
            print(f"echo \"Starting Job {job_counter}: {p['job_suffix']}\"")
            print(f"mkdir -p {plotback_work_dir}")
            print(f"cd {plotback_work_dir} || {{ echo 'Failed to cd into {plotback_work_dir}'; exit 1; }}\n")

            cmd_s11 = f"sbatch --array={pb_array} -p {p['pb_partition']} -c {p['pb_cpus']} {dependency_str} {p['script_plotback']} \\\n{pb_args}"
            print(f"# Submit step: Plotback")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s11})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(Plotback): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if p.getboolean('run_plotbackv3'):
            print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) ---")
            print(f"echo \"Starting Job {job_counter}: {p['job_suffix']}\"")
            print(f"mkdir -p {plotback_work_dir}")
            print(f"cd {plotback_work_dir} || {{ echo 'Failed to cd into {plotback_work_dir}'; exit 1; }}\n")

            cmd_s12 = f"sbatch --array={pbv3_array} -p {p['pbv3_partition']} -c {p['pbv3_cpus']} {dependency_str} {p['script_plotbackv3']} \\\n{pbv3_args}"
            print(f"# Submit step: Plotback v3")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s12})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(Plotback v3): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if p.getboolean('run_copymat') or p.getboolean('run_ssim'):
            print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) ---")
            print(f"echo \"Starting Job {job_counter}: {p['job_suffix']}\"")
            print(f"mkdir -p {eval_work_dir}")
            print(f"cd {eval_work_dir} || {{ echo 'Failed to cd into {eval_work_dir}'; exit 1; }}\n")
        
        if p.getboolean('run_copymat'):
            cmd_s13 = f"sbatch -p {p['cpm_partition']} -c {p['cpm_cpus']} {dependency_str} {p['script_copymat']} \\\n{cpm_args}"
            print(f"# Submit step: Copy Matfiles")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s13})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(Copy Matfiles): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"
        
        if p.getboolean('run_ssim'):
            cmd_s14 = f"sbatch --array={ssim_array} -p {p['ssim_partition']} {dependency_str} {p['script_ssim']} \\\n{ssim_args}"
            print(f"# Submit step: SSIM")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s14})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(SSIM): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

            
        if enable_job_array_dependency:
            previous_section_dependency_str = dependency_str

        print(f"# --- Submission of Job {job_counter} completed. ---")
        print("# ==================================================")
        print()


        
    print("\n# --- All jobs submitted. ---")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <config_file.ini>", file=sys.stderr)
        sys.exit(1)
    generate_shell_script(sys.argv[1])
