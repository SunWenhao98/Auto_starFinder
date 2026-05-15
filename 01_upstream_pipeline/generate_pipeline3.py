import configparser
import sys
import math

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

    # 遍历所有 Job
    for i, section_name in enumerate(job_sections):
        job_counter = i + 1
        
        # p 会自动从 [DEFAULT] 继承，并被 [JOB_XXX] 覆盖
        p = config[section_name]
        
        job_prefix = f"ARRAY{job_counter:03d}"
        JOB_ID_VAR = f"{job_prefix}_JOB_ID"
        JOB_OUT_VAR = f"{job_prefix}_OUTPUT"
        
        # --- 关键: 动态依赖链 ---
        dependency_str = ""

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
            spf_array = f"1-{p['spf_array_tasks']}%%{p['spf_parallel_tasks']}"
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
            sd_array = f"1-{p['sd_array_tasks']}%%{p['sd_parallel_tasks']}"
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
            
            gr_array = f"1-{p['gr_array_tasks']}%%{p['gr_parallel_tasks']}"
            gr_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} {p['gr_norm_mode']} {p['gr_percen_max']} "
                f"{p['gr_hist_round']} {p['gr_hist_channel']} {p['gr_radius']} "
                f"{p['gr_mode']} {p['gr_align_basis']} {image_geom_args} {p['gr_offset']} \\\n"
                f"{p['gr_erode']} {p['gr_transform']} {p['gr_input_format']} {p['gr_norm_out_format']}"
            )
            
            # --- 【关键修正 1/3】 ---
            # 定义 LR 的 *基础* 参数，不包含 offset
            lr_array = f"1-{p['lr_array_tasks']}%%{p['lr_parallel_tasks']}"
            lr_args_base = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} {p['lr_align_basis']} {image_geom_args}"
            )

            ls_array = f"1-{p['ls_array_tasks']}%%{p['ls_parallel_tasks']}"
            ls_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} {image_geom_args} {p['ls_offset']}"
            )
            
            gd_array = f"1-{p['gd_array_tasks']}%%{p['gd_parallel_tasks']}"
            voxel_size = f"[{p['gd_voxelsize']}]"
            # print(voxel_size)
            gd_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} {image_geom_args} {p['gd_intensity_threshold']} {p['gd_spotfinding_method']} "
                f"{p['gd_decoding_mode']} {p['gd_codeMap_mode']} {p['gd_loading_mode']} {p['gd_intensityThresh_PR']} {voxel_size} {p['gd_decoding_rounds']} {p['gd_offset']}"
            )
            
            gspf_array = f"1-{p['gspf_array_tasks']}%%{p['gspf_parallel_tasks']}"
            gspf_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} {p['gspf_intensity_threshold']} {p['gspf_spotfinding_method']} "
                f"{p['gspf_loading_mode']} {image_geom_args} {p['gspf_offset']}"
            )

            if_reg_array = f"1-{p['if_reg_array_tasks']}%%{p['if_reg_parallel_tasks']}"
            if_reg_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} {p['if_reg_offset']} {image_geom_args} {p['if_reg_input_format']} {p['if_reg_norm_out_format']} {p['if_reg_protein_outdir']}"
            )
            
            # IF_stitch_config 参数
            if_stitch_config_output_dir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}/{p['if_reg_protein_outdir']}"
            if_stitch_config_args = (
                f"{p["if_stitch_config_input_dir"]} \\\n"
                f"{if_stitch_config_output_dir} {p["if_stitch_config_match_string"]} \\\n"
                f"{p["if_stitch_config_pixel_size_um"]} {p["if_stitch_config_image_xy"]} {p["if_stitch_config_overlap_ratio"]} {p["if_stitch_config_invert_y_flag"]} \\\n"
                f"{p["if_stitch_config_maf_file"]} {p["if_stitch_config_position_offset"]} {p["if_stitch_config_microscope"]} \\\n"
            )

            # IF_stitch 参数
            if_stitch_if_dir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}/{p['if_reg_protein_outdir']}"
            if_stitch_script_dir = f"{p['FovIntegration']}"
            if_stitch_args = (
                f"{if_stitch_if_dir} \\\n"
                f"{p['if_stitch_grid_x']} {p['if_stitch_grid_y']} {p['if_stitch_first_index']} \\\n"
                f"{if_stitch_script_dir} \\\n"
                f"{p['if_stitch_stitch_pattern']} \\\n"
            )

            # IF_stitch_VisualCheck 参数
            if_stitch_visualCheck_if_dir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}/{p['if_reg_protein_outdir']}"
            if_stitch_visualCheck_script_dir = f"{p['FovIntegration']}"
            if_stitch_visualCheck_args = (
                f"{if_stitch_visualCheck_if_dir} \\\n"
                f"{p['if_stitch_visualCheck_grid_x']} {p['if_stitch_visualCheck_grid_y']} {p['if_stitch_visualCheck_first_index']} \\\n"
                f"{if_stitch_visualCheck_script_dir} \\\n"
                f"{p['if_stitch_visualCheck_stitch_pattern']} \\\n"
            )


            dapi_cp_array = f"1-{p['dapi_cp_array_tasks']}%%{p['dapi_cp_parallel_tasks']}"
            dapi_cp_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} {p['ref_round']} {p['dapi_cp_diameter']} {p['dapi_cp_area_thresh']} {p['dapi_cp_offset']}"
            )

            cluMap_array = f"1-{p['cluMap_array_tasks']}%%{p['cluMap_parallel_tasks']}"
            cluMap_args = (
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix} {p['ref_round']} {p['cluMap_offset']} \\\n"
                f"{p['cluMap_cell_num_thresh']} {p['cluMap_dapi_grid']} {p['cluMap_cell_radius']} {p['cluMap_pct_filter']} {p['cluMap_rotation']} {p['cluMap_extra_preprocess']} {p['cluMap_sub_Span']} {p['cluMap_expected_workers']} {p['cluMap_reads_filters']} {p['cluMap_overlap_percent']} {p['cluMap_dapi_suffix']} {p['cluMap_spot_csv_name']}"
            )

            # rna_restore 参数
            rna_restore_input_dir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}"
            rna_restore_array = f"1-{p['rna_restore_array_tasks']}%%{p['rna_restore_parallel_tasks']}"
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
            et_array = f"1-{p['et_array_tasks']}%%{p['et_parallel_tasks']}"
            et_outdir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}/{p['et_prefix']}"   
            et_args =(
                f"{p['project_root']} \\\n"
                f"{p['project_name']} {reg_dir_suffix}"
                f" {p['et_spot_name']} {p['et_image_name']} {et_outdir} {p['et_process_rounds']} {p['et_extend_size']} {p['et_prefix']} {p['et_offset']}"
            )

            # plotback
            pb_input_dir = f"{p['project_root']}/{p['project_name']}/{reg_dir_suffix}/"
            pb_array = f"1-{p['pb_array_tasks']}%%{p['pb_parallel_tasks']}"
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

            pbv3_array = f"1-{p['pbv3_array_tasks']}%%{p['pbv3_parallel_tasks']}"
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
            ssim_array = f"1-{p['ssim_array_tasks']}%%{p['ssim_parallel_tasks']}"
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
                    array_string = f"--array={array_range}%%{parallel_limit}"
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
                    array_string = f"--array={array_range}%%{parallel_limit}"
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
                    array_string = f"--array={array_range}%%{parallel_limit}"
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



        if p.getboolean('run_IF_reg') or p.getboolean('run_IF_stitch') or p.getboolean('run_IF_stitch_config') or p.getboolean('run_IF_stitch_visualCheck'):
            print(f"\n# --- Job {job_counter}: {section_name} ({p['job_suffix']}) - Proteins Image registration && stitching ---")
            print(f"echo \"Starting Job {job_counter}: {p['job_suffix']} (Proteins Image registration && stitching)\"")
            print(f"mkdir -p {stitch_work_dir}")
            print(f"cd {stitch_work_dir} || {{ echo 'Failed to cd into {stitch_work_dir}'; exit 1; }}\n")

        if p.getboolean('run_IF_reg'):
            cmd_s6 = f"sbatch --array={if_reg_array} -p {p['if_reg_partition']} -c {p['if_reg_cpus']} {dependency_str} {p['script_IF_reg']} \\\n{if_reg_args}"
            print(f"# Submit step: IF Registration")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s6})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(IF Reg): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if p.getboolean('run_IF_stitch_config'):
            cmd_s7_0 = f"sbatch -p {p['if_stitch_config_partition']} -c {p['if_stitch_config_cpus']} --mem {p['if_stitch_config_mem']} {dependency_str} {p['script_IF_stitch_config']} \\\n{if_stitch_config_args}"
            print(f"# Submit step: IF Stitch Config")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s7_0})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(IF Stitch Config): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

        if p.getboolean('run_IF_stitch'):
            cmd_s7 = f"sbatch -p {p['if_stitch_partition']} -c {p['if_stitch_cpus']} --mem {p['if_stitch_mem']} {dependency_str} {p['script_IF_stitch']} \\\n{if_stitch_args}"
            print(f"# Submit step: IF Stitch")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s7})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(IF Stitch): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"
        
        if p.getboolean('run_IF_stitch_visualCheck'):
            cmd_s8 = f"sbatch -p {p['if_stitch_visualCheck_partition']} -c {p['if_stitch_visualCheck_cpus']} --mem {p['if_stitch_visualCheck_mem']} {dependency_str} {p['script_IF_stitch_visualCheck']} \\\n{if_stitch_visualCheck_args}"
            print(f"# Submit step: IF Stitch Visual Check")
            print(f"{JOB_OUT_VAR}=$(\\")
            print(f"{cmd_s8})")
            print(f"{JOB_ID_VAR}=$(echo ${JOB_OUT_VAR} | awk '{{print $4}}')")
            print(f"echo \"Submitted Step(IF Stitch Visual Check): ${{{JOB_ID_VAR}}}\"\n")
            dependency_str = f"--dependency=afterok:${{{JOB_ID_VAR}}}"

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

            
        print(f"# --- Submission of Job {job_counter} completed. ---")
        print("# ==================================================")
        print()


        
    print("\n# --- All jobs submitted. ---")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <config_file.ini>", file=sys.stderr)
        sys.exit(1)
    generate_shell_script(sys.argv[1])