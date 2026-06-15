% This function takes parameters from config.yaml, passed by the rsf.py script as arguments 
% Depending on the parameters, the logic will route to one of 5 chunks:
    % 1 global_registration: performs global reg over a whole tile
    % 2 split: splits globally registered rounds into subtiles to parallelize following steps 
    % 3 local_registration: performs local reg over one subtile and performs spot-finding and filtering
    % 4 stitch: aggregates spot-finding results across subtiles and "re-stitches" the full tile
    % 5 nuclei_protein_registration: 

function out = core_matlab_new( sample, mode, tile, xy, z, ref_round, n_chs, n_rounds, ...
                            user_dir, source_data_dir, registration_dir, log_dir, ...
                            varargin )
    
    
    %% Select GPU
    %gpuDevice(2)

    %% Input parser
    p = inputParser;

    % Required parameters necessary for all modes
    addRequired(p, 'sample');
    addRequired(p, 'mode');
    %addRequired(p, 'run_id');
    addRequired(p, 'tile');
    addRequired(p, 'xy');
    addRequired(p, 'z');
    addRequired(p, 'ref_round');
    addRequired(p, 'n_chs');
    addRequired(p, 'n_rounds');

    addRequired(p, 'user_dir');
    addRequired(p, 'source_data_dir');
    addRequired(p, 'registration_dir');
    addRequired(p, 'log_dir');

    disp("required parameters parsed")
    
    % "Parameter" parameters are mode-specific
    % These may not be included in function call, so dummy values are defaults
    defaultSubtile = 0;
    defaultendBases = [];
    defaultbarcodeMode = "";
    defaultsplitLoc = [5,11];
    defaultvoxelSize = [];
    defaultsqrtPieces = 0;
    defaultMethod = "";
    defaultintensityThreshold = 0.2;
    defaultqScoreThers = 0;
    defaultproteinRound = "";
    defaultproteinStains = [];
    % protein_outdir
    defaultprotein_outdir = "IF";

    % defaultinput_format = "uint8";
    % defaultnorm_outformat = "uint8";
    defaultinput_format = "uint16";
    defaultnorm_outformat = "uint8";

    defaultloadFormat = "tif";
    defaultNorm_Mode = "percentile";
    defaultpercen_max = 99.999;

    defaultalign_basis = "maxProjection";       % "maxProjection"
    % defaultalign_basis = "dapi";              % "dapi"

    defaultalign_basis_LR = "maxProjection";    % "maxProjection"
    % defaultalign_basis_LR = "dapi";           % "dapi"
    % codeMap_mode=${7:-'Olympus'} 
    defaultcodeMap_mode = "Olympus";            % "Olympus" / "Leica_rj"

    % defaultfixedMax = 1500; % for fixed-range normalization
    % defaultfixedMin = 100; % for fixed-range normalization
    defaulthist_channel = 2;
    defaulthist_round = 0;
    defaultradius = 8;
    defaultGlobalRegistrationMode = 1;
    defaultLoadingMode = "local_registration";
    defaultIntensityThresh_perRound = 270;  % intensity threshold per round for spot filtering
    defaulterode = 1;
    defaulttransform = 1;
    defaultfsize = [5 5 3];
    defaultfsigma = 1;
    defaultdecoding_rounds = 11;

    addParameter(p, 'subtile', defaultSubtile);
    addParameter(p, 'end_bases', defaultendBases);
    addParameter(p, 'barcode_mode', defaultbarcodeMode);
    addParameter(p, 'split_loc', defaultsplitLoc);
    addParameter(p, 'voxel_size', defaultvoxelSize);
    addParameter(p, 'sqrt_pieces', defaultsqrtPieces);
    addParameter(p, 'spotfinding_method', defaultMethod);
    addParameter(p, 'intensity_threshold', defaultintensityThreshold);
    % addParameter(p, 'q_score_thers', defaultqScoreThers);
    addParameter(p, 'protein_round', defaultproteinRound);
    addParameter(p, 'protein_stains', defaultproteinStains);
    addParameter(p, 'protein_outdir', defaultprotein_outdir);
    
    addParameter(p, 'input_format', defaultinput_format);
    addParameter(p, 'norm_out_format', defaultnorm_outformat);

    addParameter(p, 'loadFormat', defaultloadFormat); % 'tif' or 'mat'
    addParameter(p, 'norm_mode', defaultNorm_Mode);
    addParameter(p, 'percen_max', defaultpercen_max);

    addParameter(p, 'align_basis', defaultalign_basis);
    addParameter(p, 'align_basis_LR', defaultalign_basis_LR);
    addParameter(p, 'codeMap_mode', defaultcodeMap_mode);

    % fixedMax and fixedMin are used for fixed-range normalization
    % addParameter(p, 'fixedMax', defaultfixedMax);
    % addParameter(p, 'fixedMin', defaultfixedMin);
    addParameter(p, 'hist_channel', defaulthist_channel);
    addParameter(p, 'hist_round', defaulthist_round);
    addParameter(p, 'radius', defaultradius);

    % loading_mode
    addParameter(p, 'global_registration_mode', defaultGlobalRegistrationMode);
    addParameter(p, 'loading_mode', defaultLoadingMode);
    addParameter(p, 'IntensityThresh_perRound', defaultIntensityThresh_perRound);
    addParameter(p,'erode',defaulterode);
    addParameter(p,'transform',defaulttransform);
    addParameter(p, 'fsize', defaultfsize);
    addParameter(p, 'fsigma', defaultfsigma);
    addParameter(p, 'decoding_rounds', defaultdecoding_rounds);

    disp("additional parameters added");
 
    parse(p, sample, mode, tile, xy, z, ref_round, n_chs, n_rounds, ...
            user_dir, source_data_dir, registration_dir, log_dir, ...
            varargin{:}); 

    % Parse dimensions
    input_dim = [p.Results.xy p.Results.xy p.Results.z p.Results.n_chs p.Results.n_rounds];
    if p.Results.n_chs == 4
        spot_channels = 3;
    else
        spot_channels = p.Results.n_chs;
    end
    disp(strcat("input_dim: ", num2str(input_dim)));
    disp(strcat("spot_channels: ", num2str(spot_channels)));

    % File I/O
    input_path = fullfile(p.Results.user_dir, p.Results.sample, p.Results.source_data_dir);
    output_path = fullfile(p.Results.user_dir, p.Results.sample, p.Results.registration_dir); %, p.Results.run_id);
    %
    % addpath(fullfile('/home/huzeng_pkuhpc/gpfs3/yly/STATES-matlab-cellline'));
    matlab_src = getenv('CORE_MATLAB_DIR');
    % addpath(fullfile(matlab_src));
    addpath(genpath(fullfile(matlab_src)));

    % tile directory
    curr_out_path = fullfile(output_path, p.Results.tile);
    if ~exist(curr_out_path, 'dir')
        mkdir(curr_out_path);
        fileattrib(curr_out_path, '+w', 'g'); % allows write permlogissions for group of users (755)
    end
    % log directory within tile
    curr_out_path_log = fullfile(curr_out_path, p.Results.log_dir);
    if ~exist(curr_out_path_log, 'dir')
        mkdir(curr_out_path_log);
        fileattrib(curr_out_path_log, '+w', 'g'); % allows write permissions for group of users (755)
    end
    % intermediary output directory within tile (includes registered image mat files, subtile outputs, and r1max)      
    interm_output_dir = fullfile(curr_out_path, 'interm');
    if ~exist(interm_output_dir, 'dir')
        mkdir(interm_output_dir);
        fileattrib(interm_output_dir, '+w', 'g'); % allows write permissions for group of users (755)
    end

    % Loading data and save as raw mat
    if strcmp(p.Results.mode, 'load_save_rawData')

        sdata = new_STARMapDataset_zf(input_path, output_path, 'useGPU', false);
        sdata.log = fopen(fullfile(curr_out_path_log, 'log_load_save_rawData.txt'), 'w');

        % load tiff stack 
        sdata = sdata.LoadRawImages('sub_dir', p.Results.tile, ...
                                    'input_dim', input_dim, ...
                                    'input_format', p.Results.input_format);

        disp(strcat("current datatype of images matrix in mat:", class(sdata.rawImages)));
        % 





        % Save registeredImages as a complete mat file
        rawImages_matfile = fullfile(curr_out_path, strcat('rawImages_complete.mat'));
        rawImages = sdata.rawImages;
        
        save(rawImages_matfile, 'rawImages', '-v7.3');
        disp(strcat("Raw images saved as mat file: ", rawImages_matfile));
        
        fclose(sdata.log);
    end


    % Global Registration
    if strcmp(p.Results.mode,'global_registration')
        %gpuDevice(2)
        

        sdata = new_STARMapDataset_zf(input_path, output_path, 'useGPU', false);
        sdata.log = fopen(fullfile(curr_out_path_log, 'log_global.txt'), 'w');

        %%% preprocess
        if p.Results.loadFormat == 'tif'
            % load rawImages from tiff stack files
            sdata = sdata.LoadRawImages('sub_dir', p.Results.tile, ...
                                        'input_dim', input_dim, ...
                                        'input_format', p.Results.input_format);
            fprintf('Raw images loaded from tiff stack.\n')

        elseif p.Results.loadFormat =='mat'
            % load rawImages from mat file            
            fprintf('Loading raw image from mat ...\n');
            load(fullfile(curr_out_path, strcat('rawImages_complete.mat')));
            sdata_t.rawImages = rawImages;
            rawImages = [];
            fprintf('preprocessed rawImages have been loaded from matfile.\n')
        end

        % %% Save raw input images for each round
        % for r = 1:size(sdata.rawImages, 5) % 遍历每个 round
        %     % if ismember(r, [1, 5, 7, 9])  % 只保存特定轮次

        %     for c = 1:size(sdata.rawImages, 4) % 遍历每个 channel
        %         rawImage_img_name = fullfile(interm_output_dir, ...
        %             strcat(p.Results.tile, "_rawImage_round_", num2str(r), "_channel_", num2str(c), ".tif"));
        
        %         if exist(rawImage_img_name, 'file') == 2
        %             delete(rawImage_img_name);
        %         end
        
        %         for j = 1:size(sdata.rawImages, 3) % 遍历每个 z-slice
        %             img_slice = squeeze(sdata.rawImages(:, :, j, c, r)); % 获取单个 z-slice
        %             if j == 1
        %                 imwrite(img_slice, rawImage_img_name, 'WriteMode', 'overwrite');
        %             else
        %                 imwrite(img_slice, rawImage_img_name, 'WriteMode', 'append');
        %             end
        %         end
        
        %         disp(strcat("Wrote ", rawImage_img_name, " to file"));
        %     end
        %     % end
        % end

        % % Save rawImages as a complete mat file
        % rawImages_mat_file = fullfile(curr_out_path, strcat('rawComplete_image.mat'));
        % rawImages = sdata.rawImages;
        % % save(rawImages_mat_file, 'rawImages');
        % save(rawImages_mat_file, 'rawImages', '-v7.3');
        % disp(strcat("raw images saved as mat file: ", rawImages_mat_file));


        % sdata = sdata.SwapChannels; % !!

        if strcmp(p.Results.norm_mode, 'percentile')
            sdata = sdata.PercenNormalize('output_format', p.Results.norm_out_format, 'maxper', p.Results.percen_max);
        elseif strcmp(p.Results.norm_mode, 'fixed')
            sdata = sdata.fixedScaleNormalize('output_format', p.Results.norm_out_format, 'fixedMin', p.Results.fixedMin, 'fixedMax', p.Results.fixedMax);
        elseif strcmp(p.Results.norm_mode, 'minMax')
            sdata = sdata.MinMaxNormalize('output_format', p.Results.norm_out_format);
        end

        disp(strcat("current datatype of images matrix in mat:", class(sdata.rawImages)));

        % Save raw input images for each round
        % for r = 1:size(sdata.rawImages, 5) % 遍历每个 round
        %     % if ismember(r, [1, 5, 7, 9])  % 只保存特定轮次

        %     for c = 1:size(sdata.rawImages, 4) % 遍历每个 channel
        %         rawNorm_img_name = fullfile(interm_output_dir, ...
        %             strcat(p.Results.tile, "_rawNorm_round_", num2str(r), "_channel_", num2str(c), ".tif"));
        
        %         if exist(rawNorm_img_name, 'file') == 2
        %             delete(rawNorm_img_name);
        %         end
        
        %         for j = 1:size(sdata.rawImages, 3) % 遍历每个 z-slice
        %             img_slice = squeeze(sdata.rawImages(:, :, j, c, r)); % 获取单个 z-slice
        %             if j == 1
        %                 imwrite(img_slice, rawNorm_img_name, 'WriteMode', 'overwrite');
        %             else
        %                 imwrite(img_slice, rawNorm_img_name, 'WriteMode', 'append');
        %             end
        %         end
        
        %         disp(strcat("Wrote ", rawNorm_img_name, " to file"));
        %     end
        %     % end
        % end

        if p.Results.hist_round > 0
            sdata = sdata.HistEqualize('Method', "inter_round", 'hist_round', p.Results.hist_round);
        elseif p.Results.hist_channel == 0
            disp('No histogram equalization between rounds performed.')
        end
        
        if p.Results.hist_channel > 0
            sdata = sdata.HistEqualize('Method', "intra_round", 'hist_channel', p.Results.hist_channel);
        elseif p.Results.hist_channel == 0
            disp('No histogram equalization within rounds performed.')
        end


        % %% Save raw input images for each round
        % for r = 1:size(sdata.rawImages, 5) % 遍历每个 round
        %     % if ismember(r, [1, 5, 7, 9])  % 只保存特定轮次

        %     for c = 1:size(sdata.rawImages, 4) % 遍历每个 channel
        %         rawHistEq_img_name = fullfile(interm_output_dir, ...
        %             strcat(p.Results.tile, "_rawHistEq_round_", num2str(r), "_channel_", num2str(c), ".tif"));
        
        %         if exist(rawHistEq_img_name, 'file') == 2
        %             delete(rawHistEq_img_name);
        %         end
        
        %         for j = 1:size(sdata.rawImages, 3) % 遍历每个 z-slice
        %             img_slice = squeeze(sdata.rawImages(:, :, j, c, r)); % 获取单个 z-slice
        %             if j == 1
        %                 imwrite(img_slice, rawHistEq_img_name, 'WriteMode', 'overwrite');
        %             else
        %                 imwrite(img_slice, rawHistEq_img_name, 'WriteMode', 'append');
        %             end
        %         end
        
        %         disp(strcat("Wrote ", rawHistEq_img_name, " to file"));
        %     end
        %     % end
        % end
        


        % Enhancing Signal & Removing Background Noise
        if p.Results.radius > 0
            sdata = sdata.MorphoRecon('Method', "2d", 'radius', p.Results.radius, ...
                                      'erode', p.Results.erode, 'transform', p.Results.transform);
        elseif p.Results.radius == 0
            disp('No morphological reconstruction performed.')
        end

        % % Save rawImages as a complete mat file
        % rawImages_mat_file = fullfile(curr_out_path, strcat('rawPreprocessed_image.mat'));
        % full_image = sdata.rawImages;
        % % save(rawImages_mat_file, 'rawImages');
        % save(rawImages_mat_file, 'full_image', '-v7.3');
        % disp(strcat("raw images saved as mat file: ", rawImages_mat_file));
        
        % %% Save raw input images for each round
        % for r = 1:size(sdata.rawImages, 5) % 遍历每个 round
        %     % if ismember(r, [1, 5, 7, 9])  % 只保存特定轮次

        %     for c = 1:size(sdata.rawImages, 4) % 遍历每个 channel
        %         rawMorphoRecon_img_name = fullfile(interm_output_dir, ...
        %             strcat(p.Results.tile, "_rawMorphoRecon_round_", num2str(r), "_channel_", num2str(c), ".tif"));
        
        %         if exist(rawMorphoRecon_img_name, 'file') == 2
        %             delete(rawMorphoRecon_img_name);
        %         end
        
        %         for j = 1:size(sdata.rawImages, 3) % 遍历每个 z-slice
        %             img_slice = squeeze(sdata.rawImages(:, :, j, c, r)); % 获取单个 z-slice
        %             if j == 1
        %                 imwrite(img_slice, rawMorphoRecon_img_name, 'WriteMode', 'overwrite');
        %             else
        %                 imwrite(img_slice, rawMorphoRecon_img_name, 'WriteMode', 'append');
        %             end
        %         end
        
        %         disp(strcat("Wrote ", rawMorphoRecon_img_name, " to file"));
        %     end
        %     % end
        % end


        if p.Results.global_registration_mode == 1
            % register rounds to reference round
            % sdata = sdata.test_GlobalRegistration('useGPU', false, 'ref_round', p.Results.ref_round);
            sdata = sdata.test_GlobalRegistration('useGPU', false, ...
                                                  'ref_round', p.Results.ref_round, ...
                                                  'alignBasis', p.Results.align_basis);

            % Save global registered images for each round
            for r = 1:size(sdata.registeredImages, 5) % 遍历每个 round
                % if ismember(r, [1, 3, 5, 7, 9])  % 只保存特定轮次

                for c = 1:size(sdata.registeredImages, 4) % 遍历每个 channel
                    global_registered_img_name = fullfile(interm_output_dir, ...
                        strcat(p.Results.tile, "_global_registered_round_", num2str(r), "_channel_", num2str(c), ".tif"));
                
                    if exist(global_registered_img_name, 'file') == 2
                        delete(global_registered_img_name);
                    end
                
                    for j = 1:size(sdata.registeredImages, 3) % 遍历每个 z-slice
                        img_slice = squeeze(sdata.registeredImages(:, :, j, c, r)); % 获取单个 z-slice
                        if j == 1
                            imwrite(img_slice, global_registered_img_name, 'WriteMode', 'overwrite');
                        else
                            imwrite(img_slice, global_registered_img_name, 'WriteMode', 'append');
                        end
                    end
                
                    disp(strcat("Wrote ", global_registered_img_name, " to file"));
                end

                % end
            end

            % Save registeredImages as a complete mat file
            registeredImages_mat_file = fullfile(curr_out_path, strcat('globalRegistered_image.mat'));
            full_image = sdata.registeredImages;
            save(registeredImages_mat_file, 'full_image', '-v7.3');
            disp(strcat("Registered images saved as mat file: ", registeredImages_mat_file));


            % %%% save round 1 merged tif and registered whole image
            % try % round 1 merged
            %     r1_img = max(sdata.registeredImages(:,:,:,:,p.Results.ref_round), [], 4);
            %     r1_img_name = fullfile(interm_output_dir, "r1merged.tif");
            %     SaveSingleTiff(r1_img, r1_img_name);
            %     clear r1_img;
            %     disp(strcat("Wrote ", r1_img_name, " to file"))
            % catch
            %     disp('Did not write round1 merged tif. Probably already exists, but double-check');
            % end

            % save every round channel-merged registered image
            % Save global registered images for each round
            for r = 1:size(sdata.registeredImages, 5) % 遍历每个 round
                % if ismember(r, [1, 3, 5, 7, 9])  % 只保存特定轮次


                global_registered_img_name = fullfile(interm_output_dir, ...
                    strcat(p.Results.tile, "_global_registered_round", num2str(r), "channel-merged",".tif"));
            
                if exist(global_registered_img_name, 'file') == 2
                    delete(global_registered_img_name);
                end
            
                for j = 1:size(sdata.registeredImages, 3) % 遍历每个 z-slice
                    img_slice = squeeze(sdata.registeredImages(:, :, j, 1:spot_channels, r)); % 获取斑点通道的单个 z-slice
                    img_slice = squeeze(max(img_slice, [], 3)); % 合并 channel

                    if j == 1
                        imwrite(img_slice, global_registered_img_name, 'WriteMode', 'overwrite');
                    else
                        imwrite(img_slice, global_registered_img_name, 'WriteMode', 'append');
                    end
                end
            
                disp(strcat("Wrote ", global_registered_img_name, " to file"));


                % end
            end

            fclose(sdata.log);
            

            % Split into subtiles for local registration and spot-finding
            coords_mat = table([],[],[],[],[],[],[],[],[],[],[],'VariableNames',{'t','ind_x','ind_y','scoords_x','scoords_y','ecoords_x','ecoords_y','upperleft_x','upperleft_y','inputdim_x','inputdim_y'});

            sub_order = [];
            for i = 0:(p.Results.sqrt_pieces-1)
                for j = 0:(p.Results.sqrt_pieces-1)
                    sub_order = [sub_order;[i,j]];
                end
            end

            tile_size = floor(p.Results.xy / p.Results.sqrt_pieces);
            overlap_half = floor(tile_size * 0.1);
            upper_left = [0,0];
            for t=1:size(sub_order,1)
                tile_idx = sub_order(t,:);
                start_coords_x = tile_idx(1) * tile_size - overlap_half + 1;
                end_coords_x = (tile_idx(1)+1) * tile_size + overlap_half;
                start_coords_y = tile_idx(2) * tile_size - overlap_half + 1;
                end_coords_y = (tile_idx(2)+1) * tile_size + overlap_half;
                %% compensate in edge
                if tile_idx(1) == 0
                    start_coords_x = start_coords_x + overlap_half;
                end
                if tile_idx(2) == 0
                    start_coords_y = start_coords_y + overlap_half;
                end
                %% compensate in edge
                if tile_idx(1) == p.Results.sqrt_pieces - 1
                    end_coords_x = input_dim(1);
                end
                if tile_idx(2) == p.Results.sqrt_pieces - 1
                    end_coords_y = input_dim(2);
                end
                upper_left(1) = tile_idx(1) * tile_size;
                upper_left(2) = tile_idx(2) * tile_size;    
        
                input_dim_t = input_dim;
                input_dim_t(1:2) = [end_coords_x - start_coords_x + 1,end_coords_y - start_coords_y + 1];
                disp([tile_idx,start_coords_x,end_coords_x,start_coords_y,end_coords_y,upper_left(1:2),input_dim_t(1:2)]);

                coords_mat_t = table(t,tile_idx(1),tile_idx(2),start_coords_x,start_coords_y,end_coords_x,end_coords_y,upper_left(1),upper_left(2),input_dim_t(1),input_dim_t(2),'VariableNames',{'t','ind_x','ind_y','scoords_x','scoords_y','ecoords_x','ecoords_y','upperleft_x','upperleft_y','inputdim_x','inputdim_y'});

                coords_mat = [coords_mat;coords_mat_t];
                t_output = sdata.registeredImages(start_coords_y:end_coords_y,start_coords_x:end_coords_x,:,:,:); %% row - y , col - x [row, col, z, :,:]

                %%% save each subtile registered images in following format: registeredImages_t{subtile}_{total_subtiles}.mat
                save(fullfile(interm_output_dir, strcat('registeredImages_t',num2str(t),'_',num2str(p.Results.sqrt_pieces^2),'.mat')), "t_output");
            end
            
            writetable(coords_mat, fullfile(interm_output_dir,strcat('coords_mat_',num2str(p.Results.sqrt_pieces^2),'.csv')),'Delimiter',',','QuoteStrings',false);

            disp('Global registration and subtile splitting done!!!')
        
        elseif p.Results.global_registration_mode == 0
            % sdata.registeredImages = sdata.rawImages;

            % Save rawImages as a complete mat file
            rawImages_mat_file = fullfile(curr_out_path, strcat('rawPreprocessed_image.mat'));
            full_image = sdata.rawImages;
            % save(rawImages_mat_file, 'rawImages');
            save(rawImages_mat_file, 'full_image', '-v7.3');
            disp(strcat("raw images saved as mat file: ", rawImages_mat_file));

            disp('No global registration performed and the registered images are the same as the raw images.');
        end


    end
    

    % 2025-08-13: Local Registration, sperating out
    if strcmp(p.Results.mode,'local_registration')
        %gpuDevice(2)
        %if isempty(gcp('nocreate'))
        %    parpool('local', 5);
        %end

        %%% get subtile coordinate position data
        coords_mat =readtable(fullfile(interm_output_dir,strcat('coords_mat_',num2str(p.Results.sqrt_pieces^2),'.csv')),'ReadVariableNames',true,'TextType','string');
        goodSpots = table([],[],[],[],'VariableNames',{'x','y','z','Gene'});
        
        t = p.Results.subtile;
        input_dim_t = input_dim;
        tile_idx = table2array(coords_mat(t,2:3));
        start_coords_x = table2array(coords_mat(t,4));
        start_coords_y = table2array(coords_mat(t,5));
        upper_left = table2array(coords_mat(t,8:9));
        input_dim_t(1:2) = table2array(coords_mat(t,10:11));
    
        %%% initialize and load registered subtile 
        sdata_t = new_STARMapDataset_zf(input_path, output_path, 'useGPU', false);
        sdata_t.log = fopen(fullfile(curr_out_path_log, strcat('log_t',num2str(p.Results.subtile),'_',num2str(p.Results.sqrt_pieces^2),'.txt')), 'w');
        fprintf(sdata_t.log, strcat('log_t',num2str(p.Results.subtile),'_',num2str(p.Results.sqrt_pieces^2),':\n'));
        
        % load t_output, name is defined in global registration
        load(fullfile(interm_output_dir, strcat('registeredImages_','t',num2str(p.Results.subtile),'_',num2str(p.Results.sqrt_pieces^2),'.mat')));
        sdata_t.registeredImages = t_output;
        t_output = [];

        sdata_t.dims = input_dim_t;
        sdata_t.dimX = input_dim_t(1);
        sdata_t.dimY = input_dim_t(2);
        sdata_t.dimZ = input_dim_t(3);
        sdata_t.Nchannel = p.Results.n_chs;
        sdata_t.Nround = p.Results.n_rounds;
    
        %%% locally register across rounds    
        sdata_t = sdata_t.xxx_LocalRegistration('Iterations', 50, 'AccumulatedFieldSmoothing', 1, ...
                                                'ref_round',p.Results.ref_round, ...
                                                'alignBasis', p.Results.align_basis_LR);
   
        % Save local registered images
        local_registered_img_name = fullfile(interm_output_dir, strcat('local_registeredImages_t', num2str(p.Results.subtile), '_', num2str(p.Results.sqrt_pieces^2), '.mat'));
        local_reg_out = sdata_t.registeredImages;
        save(local_registered_img_name, 'local_reg_out');
        disp(strcat("Wrote ", local_registered_img_name, " to file"))

        fclose(sdata_t.log);
    end

    % 2025-08-13: Stitching subtiles of local registered images
    if strcmp(p.Results.mode,'local_image_stitch')

        coords_mat = readtable(fullfile(interm_output_dir,strcat('coords_mat_',num2str(p.Results.sqrt_pieces^2),'.csv')),...
                               'ReadVariableNames',true,...
                               'TextType','string');
        
        total_subtiles = size(coords_mat,1);
        full_tile_dim = [p.Results.xy, p.Results.xy, p.Results.z, p.Results.n_chs, p.Results.n_rounds];
        disp(full_tile_dim);
        full_image = zeros(full_tile_dim, p.Results.norm_out_format);
        

        %%% iteratively aggregate subtile images
        for t=1:total_subtiles
            fprintf('>>> stitching subtile %d / %d...\n', t, total_subtiles);

            % load subtile
            load(fullfile(interm_output_dir, strcat('local_registeredImages_t', num2str(t), '_', num2str(p.Results.sqrt_pieces^2), '.mat')));
            
            subtile_image = local_reg_out;
            local_reg_out = [];

            tile_info = coords_mat(t,:);
            dest_y_start = tile_info.upperleft_y + 1;       % mosaic start-coor of subtile in full tile
            dest_x_start = tile_info.upperleft_x + 1;

            dest_y_end = tile_info.ecoords_y;               % overlapped end-coor and covered by diagonal neighbor subtiles
            dest_x_end = tile_info.ecoords_x;

            % calculate source coordinates in subtile
            src_y_start = dest_y_start - tile_info.scoords_y + 1;   % relative coor in full tile >> real coor in subtile
            src_x_start = dest_x_start - tile_info.scoords_x + 1;
            src_y_end = dest_y_end - tile_info.scoords_y + 1;
            src_x_end = dest_x_end - tile_info.scoords_x + 1;

            % stitch subtile into full tile
            full_image(dest_y_start:dest_y_end, dest_x_start:dest_x_end, :, :, :) = ...
                subtile_image(src_y_start:src_y_end, src_x_start:src_x_end, :, :, :);
        end


        % save stitched image
        stitched_image_path = fullfile(curr_out_path, 'localRegistered_image.mat');
        save(stitched_image_path, 'full_image', '-v7.3');
        disp(strcat("Locally Registered images saved as mat file: ", stitched_image_path));


        % Save local registered images for each round
        for r = 1:size(full_image, 5) % 遍历每个 round
            % if ismember(r, [1, 3, 5, 7, 9])  % 只保存特定轮次

            for c = 1:size(full_image, 4) % 遍历每个 channel
                local_registered_img_name = fullfile(interm_output_dir, ...
                    strcat(p.Results.tile, "_local_registered_round_", num2str(r), "_channel_", num2str(c), ".tif"));
            
                if exist(local_registered_img_name, 'file') == 2
                    delete(local_registered_img_name);
                end
            
                for j = 1:size(full_image, 3) % 遍历每个 z-slice
                    img_slice = squeeze(full_image(:, :, j, c, r)); % 获取单个 z-slice
                    if j == 1
                        imwrite(img_slice, local_registered_img_name, 'WriteMode', 'overwrite');
                    else
                        imwrite(img_slice, local_registered_img_name, 'WriteMode', 'append');
                    end
                end
            
                disp(strcat("Wrote ", local_registered_img_name, " to file"));
            end

            % end
        end

        for r = 1:size(full_image, 5) % 遍历每个 round
            % if ismember(r, [1, 3, 5, 7, 9])  % 只保存特定轮次


            local_registered_img_name = fullfile(interm_output_dir, ...
                strcat(p.Results.tile, "_local_registered_round", num2str(r), "channel-merged",".tif"));
        
            if exist(local_registered_img_name, 'file') == 2
                delete(local_registered_img_name);
            end
        
            for j = 1:size(full_image, 3) % 遍历每个 z-slice
                % img_slice = squeeze(full_image(:, :, j, :, r)); % 获取单个 z-slice
                img_slice = squeeze(full_image(:, :, j, 1:spot_channels, r)); % 获取斑点通道的单个 z-slice
                % disp(size(img_slice));
                img_slice = squeeze(max(img_slice, [], 3)); % 合并 channel

                if j == 1
                    imwrite(img_slice, local_registered_img_name, 'WriteMode', 'overwrite');
                else
                    imwrite(img_slice, local_registered_img_name, 'WriteMode', 'append');
                end
            end
        
            disp(strcat("Wrote ", local_registered_img_name, " to file"));


            % end
        end

        fprintf('Image stitch finished: %s\n', stitched_image_path);
    end


    % 2025-08-13: Global Reads extraction and filtration
    if strcmp(p.Results.mode,'global_reads_decoding')

        % initialize and create new_STARMapDataset_zf
        sdata_t = new_STARMapDataset_zf(input_path, output_path, 'useGPU', false);
        sdata_t.log = fopen(fullfile(curr_out_path_log, ...
                            strcat('log_globalDecode_', num2str(p.Results.tile), '_', p.Results.spotfinding_method, '_', num2str(p.Results.intensity_threshold), '.txt')), 'w');
        fprintf(sdata_t.log, strcat('log_globalDecode_', num2str(p.Results.tile), '_', p.Results.spotfinding_method, '_', num2str(p.Results.intensity_threshold), ':\n'));
        % intensity_threshold of "external tools" is probability 
        % intensity_threshold of "in-house methods" is intensity ratio


        % load local stitched image
        fprintf('Loading stitched image...\n');
        if strcmp(p.Results.loading_mode, 'local_registration')
            load(fullfile(curr_out_path, 'localRegistered_image.mat'));
        elseif strcmp(p.Results.loading_mode, 'global_registration')
            ;
        elseif strcmp(p.Results.loading_mode, 'raw_preprocessed')
            load(fullfile(curr_out_path, strcat('rawPreprocessed_image.mat')));
        end

        sdata_t.registeredImages = full_image;
        full_image = [];
        fprintf('Stitched image loaded.\n')
        
        if strcmp(p.Results.spotfinding_method, 'SpotFlow')
            % load spots finding results of external tools, such as spotflows.
            fprintf('Loading spots finding results of external tools...\n');

            allSpots_t = readtable(fullfile(curr_out_path, 'allSpots_spotiflow.csv'),...
                                'ReadVariableNames',true,...
                                'TextType','string');

            if istable(allSpots_t)
                allSpots_t = table2array(allSpots_t);
            end
            sdata_t.allSpots = allSpots_t;
            sdata_t.allSpots(:, 1:5) = double(sdata_t.allSpots(:, 1:5));
            fprintf('allSpots from spotiflow are loaded.\n');

        elseif strcmp(p.Results.spotfinding_method, 'max3d')
            % 2025-08-25: Global Spot Finding by in-house methods and Decoding
            % 2026-04-27: update max3d spot finding by detecting existing results avoiding re-running
            target_file = fullfile(curr_out_path, strcat('allSpots_', p.Results.spotfinding_method, '_', num2str(p.Results.intensity_threshold), '.csv'));

            if isfile(target_file)
                % 如果文件存在，直接加载
                fprintf('Detected existing results for max3d, loading: %s\n', target_file);
                allSpots_t = readtable(target_file, 'ReadVariableNames', true);
                
                % 将 table 转回 array 并赋给 sdata_t.allSpots
                % 注意：这里需要确保 table 列的顺序与内部 allSpots 格式一致
                sdata_t.allSpots = table2array(allSpots_t);

                % 排除行名计算有多少行，以反映 斑点检测的结果
                fprintf('Loaded allSpots with %d detected spots.\n', size(sdata_t.allSpots, 1));
            else
                % 如果文件不存在，运行原始的 SpotFinding 函数
                fprintf('No existing results found. Running SpotFinding (max3d)...\n');
                sdata_t = sdata_t.SpotFinding('Method', p.Results.spotfinding_method, ...
                    'intensityThreshold', p.Results.intensity_threshold, 'ref_index', p.Results.ref_round, 'showPlots', false);
            
                % adjust coordinates for subtile offset and save cooordinates informations
                if size(sdata_t.allSpots,1) > 0
                    allSpots_t = [table(sdata_t.allSpots(:,1), sdata_t.allSpots(:,2), sdata_t.allSpots(:,3), ...
                                        sdata_t.allSpots(:,4), sdata_t.allSpots(:,5), sdata_t.allSpots(:,6), ...
                                        'VariableNames',{'x','y','z','intensity', 'addition', 'channel'})]
                else
                    allSpots_t = table([],[],[],[],[],'VariableNames',{'x','y','z','intensity', 'addition', 'channel'});
                end
        
                writetable(allSpots_t, fullfile(curr_out_path, strcat('allSpots_', p.Results.spotfinding_method, '_', num2str(p.Results.intensity_threshold), '.csv')),'Delimiter',',','QuoteStrings',false);
                fprintf('allSpots saved.\n');
            end

        elseif strcmp(p.Results.spotfinding_method, 'log3d')
            % 2025-08-25: Global Spot Finding by in-house methods and Decoding
            sdata_t = sdata_t.SpotFinding('Method', p.Results.spotfinding_method, ...
                'intensityThreshold', p.Results.intensity_threshold, 'ref_index', p.Results.ref_round, ...
                'fsize', p.Results.fsize, 'fsigma', p.Results.sigma, 'showPlots', false);
            % adjust coordinates for subtile offset and save cooordinates informations
            if size(sdata_t.allSpots,1) > 0
                allSpots_t = [table(sdata_t.allSpots(:,1), sdata_t.allSpots(:,2), sdata_t.allSpots(:,3), ...
                                    sdata_t.allSpots(:,4), sdata_t.allSpots(:,5), sdata_t.allSpots(:,6), ...
                                    'VariableNames',{'x','y','z','intensity', 'addition', 'channel'})]
            else
                allSpots_t = table([],'VariableNames',{'x','y','z','intensity', 'addition', 'channel'});
            end
            writetable(allSpots_t, fullfile(curr_out_path, strcat('allSpots_', p.Results.spotfinding_method, '_', num2str(p.Results.intensity_threshold), '.csv')),'Delimiter',',','QuoteStrings',false);
            fprintf('allSpots saved.\n');
        end


        
        % decode color information to barcode sequences
        sdata_t = sdata_t.ReadsExtraction('voxelSize', p.Results.voxel_size, ...
                                          'interm_outpath', interm_output_dir, ...
                                          'IntensityThresh_perRound', p.Results.IntensityThresh_perRound, ...
                                          'ref_index', p.Results.ref_round, 'decoding_rounds', p.Results.decoding_rounds);

        if strcmp(p.Results.barcode_mode, "double")
            sdata_t = sdata_t.LoadCodebook('mode', "double", 'remove_index', p.Results.split_loc, 'codeMap_mode', p.Results.codeMap_mode);
            sdata_t = sdata_t.ReadsFiltration('mode', "double", 'endBases', p.Results.end_bases, 'split_loc', p.Results.split_loc, ...
                                              'showPlots', false, 'codeMap_mode', p.Results.codeMap_mode);
        elseif strcmp(p.Results.barcode_mode, "regular")  
            sdata_t = sdata_t.LoadCodebook('mode', "regular", 'codeMap_mode', p.Results.codeMap_mode);
            sdata_t = sdata_t.ReadsFiltration('mode', "regular", 'endBases', p.Results.end_bases, ...
                                              'showPlots', false, 'codeMap_mode', p.Results.codeMap_mode);
        elseif strcmp(p.Results.barcode_mode, "tri")
            sdata_t = sdata_t.LoadCodebook('mode', "tri",'remove_index', p.Results.split_loc, 'codeMap_mode', p.Results.codeMap_mode);
            sdata_t = sdata_t.ReadsFiltration('mode', "tri", 'endBases', p.Results.end_bases, 'split_loc', p.Results.split_loc, ...
                                              'showPlots', false, 'codeMap_mode', p.Results.codeMap_mode);
        elseif strcmp(p.Results.barcode_mode, "duo")        % 针对出问题的成像批次：缺少某些轮次
            sdata_t = sdata_t.LoadCodebook('mode', "duo", 'remove_index', p.Results.split_loc, 'codeMap_mode', p.Results.codeMap_mode);
            sdata_t = sdata_t.ReadsFiltration('mode', "duo", 'endBases', p.Results.end_bases, ...
                                              'showPlots', false, 'codeMap_mode', p.Results.codeMap_mode);
        elseif strcmp(p.Results.barcode_mode, "single_nc")
            sdata_t = sdata_t.LoadCodebook('mode', "single_nc", 'remove_index', p.Results.split_loc, ...
                                            'codeMap_mode', p.Results.codeMap_mode);
            sdata_t = sdata_t.ReadsFiltration('mode', "single_nc", 'showPlots', false, 'codeMap_mode', p.Results.codeMap_mode);
        else
            fprintf(sdata_t.log, "Reads filtration incomplete: invalid mode entered (valid options include 'regular', 'duo', and 'tri'");
        end
        
        disp('Reads filtration is done!')


        % save results .1: goodSpots = [x,y,z,Gene,(probability)]
        if size(sdata_t.goodSpots,1) > 0
            
            xyz_table = table(sdata_t.goodSpots(:,1), sdata_t.goodSpots(:,2), ...
                              sdata_t.goodSpots(:,3), sdata_t.goodSpots(:,4), ...
                              sdata_t.goodSpots(:,6), ...
                              'VariableNames', {'x', 'y', 'z', 'intensity', 'channel'});
            gene_cell = cellfun(@(x) sdata_t.seqToGene(x), sdata_t.goodReads, 'UniformOutput', false);
            gene_table = cell2table(gene_cell, 'VariableNames', {'Gene'});
            
            if strcmp(p.Results.spotfinding_method, 'SpotFlow')
                prob_table = table(sdata_t.goodSpots(:,5),'VariableNames',{'probability'});
                goodSpots = [xyz_table, gene_table, prob_table];
            elseif strcmp(p.Results.spotfinding_method, 'max3d')
                goodSpots = [xyz_table, gene_table];
            end

        else
            goodSpots = table([],[],[],[],'VariableNames',{'x','y','z','Gene'});
        end
        
        goodSpotsPath = fullfile(curr_out_path, strcat('goodPoints_', p.Results.spotfinding_method, '_', num2str(p.Results.intensity_threshold), ...
        '_', p.Results.barcode_mode, '.csv'));
        writetable(goodSpots, goodSpotsPath, 'Delimiter', ',', 'QuoteStrings', false);
        fprintf('goodPoints saved in %s.\n', goodSpotsPath);


        % obj.allSpots_raw, obj.allScores_raw, obj.allReads_raw, obj.allIntensity_raw, obj.goodAllIntensity 
        % Part 1.1 处理坐标数据 (Spots)
        if size(sdata_t.allSpots_raw, 1) > 0
            allSpots_raw = table(sdata_t.allSpots_raw(:, 1), sdata_t.allSpots_raw(:, 2), ...
                                 sdata_t.allSpots_raw(:, 3), sdata_t.allSpots_raw(:, 4), ...
                                 sdata_t.allSpots_raw(:, 6), ...
                                'VariableNames', {'x', 'y', 'z', 'intensity', 'channel'});

            if strcmp(p.Results.spotfinding_method, 'SpotFlow')
                prob_table = table(sdata_t.allSpots_raw(:,5),'VariableNames',{'probability'});
                allSpots_raw = [allSpots_raw, prob_table];
            end

        else
            allSpots_raw = table([], [], [], 'VariableNames', {'x', 'y', 'z', 'intensity'});
        end

        % --- Part 1.2: 处理质量分数数据 (Scores) ---
        if size(sdata_t.allScores_raw, 1) > 0
            data_matrix = sdata_t.allScores_raw;
            num_rounds = size(data_matrix, 2);
            fprintf('Number of rounds in allScores_raw: %d\n', num_rounds);
            varNames = compose("round%03d", 1:num_rounds);
            allScores_raw = array2table(data_matrix, 'VariableNames', varNames);
            disp('allScores_raw is done!')

        else
            disp('allScores_raw is empty!')
            allScores_raw = table([], [], [], [], [], [], [], [], [], ...
                                'VariableNames', {'round001', 'round002', 'round003', 'round004', 'round005', 'round006', ...
                                                'round007', 'round008', 'round009'});
        end

        % --- Part 1.3: 处理序列数据 (color seq -> color index str) ---
        if size(sdata_t.allReads_raw, 1) > 0
            allReads_raw = table(sdata_t.allReads_raw(:, 1), 'VariableNames', {'colorseq'});
            disp('allReads_raw is done!')
        else
            allReads_raw = table([], 'VariableNames', {'colorseq'});
            disp('allReads_raw is empty!')
        end

        % --- Part 1.4: 处理灰度强度数据
        expected_rounds = p.Results.n_rounds;
        num_cols_per_round = 5;
        if size(sdata_t.allIntensity_raw, 1) > 0
            data_matrix = sdata_t.allIntensity_raw;
            num_rounds = size(data_matrix, 2) / num_cols_per_round;
            fprintf('Number of rounds in allIntensity_raw: %d\n', num_rounds);
        else
            num_rounds = expected_rounds;
            data_matrix = zeros(0, num_rounds * num_cols_per_round);
            disp('allIntensity_raw is empty, initializing placeholder...')
        end

        suffixes = ["centerMax", "NeighborSum_ch1", "NeighborSum_ch2", "NeighborSum_ch3", "NeighborSum_chMax"];
        varNames = compose("round%03d_", (1:num_rounds)') + suffixes;
        varNames = varNames';
        varNames = varNames(:)'; % 转置并展开为行向量

        allIntensity_raw = array2table(data_matrix, 'VariableNames', varNames);
        disp('allIntensity_raw processing is done!')

        % Part 1.5: 处理灰度强度数据 (good intensity)
        expected_rounds = p.Results.n_rounds;
        num_cols_per_round = 5;
        if size(sdata_t.goodAllIntensity, 1) > 0
            data_matrix = sdata_t.goodAllIntensity;
            num_rounds = size(data_matrix, 2) / num_cols_per_round;
            fprintf('Number of rounds in goodAllIntensity: %d\n', num_rounds);
        else
            num_rounds = expected_rounds;
            data_matrix = zeros(0, num_rounds * num_cols_per_round);
            disp('goodAllIntensity is empty, initializing placeholder...')
        end
        suffixes = ["centerMax", "NeighborSum_ch1", "NeighborSum_ch2", "NeighborSum_ch3", "NeighborSum_chMax"];
        varNames = compose("round%03d_", (1:num_rounds)') + suffixes;
        varNames = varNames';
        varNames = varNames(:)'; % 转置并展开为行向量
        goodAllIntensity = array2table(data_matrix, 'VariableNames', varNames);
        disp('goodAllIntensity processing is done!')
        


        % --- Part 2 : 合并原始数据表格 (Spots, Scores, Reads) ---
        nRows_spots = size(allSpots_raw, 1);
        nRows_scores = size(allScores_raw, 1);
        nRows_reads = size(allReads_raw, 1);
        nRows_Intensity = size(allIntensity_raw, 1);
        nRows_goodIntensity = size(goodAllIntensity, 1);
        nRows_goodSpots = size(goodSpots, 1);

        fprintf('Check the number of rows in each part of the table:\n');
        fprintf('  - Number of rows of coordinates (Spots): %d\n', nRows_spots);
        fprintf('  - Number of rows of scores (Scores): %d\n', nRows_scores);
        fprintf('  - Number of rows of reads (Reads): %d\n', nRows_reads);
        fprintf('  - Number of rows of allIntensity: %d\n', nRows_Intensity);
        fprintf('  - Number of rows of goodAllIntensity: %d\n', nRows_goodIntensity);

        % 2.1 : 合并原始数据表格 (Spots, Scores)
        if (nRows_spots == nRows_scores)
            fprintf('Row numbers match, proceeding to table concatenation.\n');
            try
                global_rawTable_Spots_Scores = [allSpots_raw, allScores_raw];
                fprintf('concating tables successfully.\n');
            catch ME
                warning('Row numbers are the same but concatenation failed! Error message: %s', ME.message);
                fprintf('Create an empty table as a substitute.\n');
                global_rawTable_Spots_Scores = table();
            end
            
        else
            warning('Rowbnumbers are not the same! Skip concatenation.\n');
            fprintf('Create an empty table as a substitute to ensure program continues running.\n');
            global_rawTable_Spots_Scores = table();
        end

        % 2.2 : 合并原始数据表格 (Spots, Intensity)
        if (nRows_spots == nRows_Intensity)
            fprintf('Row numbers match for Spots, and allIntensity.\n');
            try
                global_rawTable_Spots_Intensity = [allSpots_raw, allIntensity_raw];
                fprintf('Added allIntensity to global_rawTable_Spots_Scores successfully.\n');
            catch ME
                warning('Row numbers are the same but concatenation with allIntensity failed! Error message: %s', ME.message);
                fprintf('Skip adding allIntensity to global_rawTable_Spots_Scores.\n');
                global_rawTable_Spots_Intensity = table();
            end
        else
            warning('Row numbers do not match among Spots and allIntensity! Skip concatenation. \n');
            global_rawTable_Spots_Intensity = table();
            fprintf('Create an empty table as a substitute to ensure program continues running.\n');
        end

        % 2.3 : 合并解码数据表格 (goodSpots, goodAllIntensity)
        if (nRows_goodSpots == nRows_goodIntensity)
            fprintf('Row numbers match for goodSpots, and goodAllIntensity.\n');
            try
                global_goodTable_Spots_Intensity = [goodSpots, goodAllIntensity];
                fprintf('Added goodAllIntensity to global_goodTable_Spots successfully.\n');
            catch ME
                warning('Row numbers are the same but concatenation with goodAllIntensity failed! Error message: %s', ME.message);
                fprintf('Skip adding goodAllIntensity to global_goodTable_Spots.\n');
                global_goodTable_Spots_Intensity = table();
            end
        else
            warning('Row numbers do not match among goodSpots and goodAllIntensity! Skip concatenation. \n');
            global_goodTable_Spots_Intensity = table();
            fprintf('Create an empty table as a substitute to ensure program continues running.\n');
        end

        % --- Part 3: 保存序列数据 (Reads) ---
        writetable(global_rawTable_Spots_Scores, fullfile(curr_out_path, strcat('global_rawSpots_Scores_', p.Results.spotfinding_method, '_', num2str(p.Results.intensity_threshold),'_', p.Results.barcode_mode, '.csv')),'Delimiter',',','QuoteStrings',false);
        writetable(allReads_raw, fullfile(curr_out_path, strcat('global_rawReads_', p.Results.spotfinding_method, '_', num2str(p.Results.intensity_threshold), '_', p.Results.barcode_mode, '.csv')),'Delimiter',',','QuoteStrings',false)
        writetable(global_rawTable_Spots_Intensity, fullfile(curr_out_path, strcat('global_rawSpots_allIntensity_', p.Results.spotfinding_method, '_', num2str(p.Results.intensity_threshold),'_', p.Results.barcode_mode, '.csv')),'Delimiter',',','QuoteStrings',false);
        writetable(global_goodTable_Spots_Intensity, fullfile(curr_out_path, strcat('global_goodSpots_goodAllIntensity_', p.Results.spotfinding_method, '_', num2str(p.Results.intensity_threshold), '_NeThresh', num2str(p.Results.IntensityThresh_perRound), '_', p.Results.barcode_mode, '.csv')),'Delimiter',',','QuoteStrings',false);
        fprintf('Global reads extraction and filtration results saved.\n');

        fclose(sdata_t.log);

    end



    % Nuclei Protein Registration
    if strcmp(p.Results.mode, 'nuclei_protein_registration')
        %gpuDevice(2)

        % initialize
        sdata = new_STARMapDataset_zf(input_path, output_path, 'useGPU', false);
        sdata.log = fopen(fullfile(curr_out_path_log, 'log_protein_registration.txt'), 'w');
        sub_dirs = string(p.Results.protein_stains);
        fprintf(sdata.log, 'log_protein_registration:\n');
        fprintf(sdata.log, 'protein_stains: %s\n', sub_dirs);

        % perform DAPI-based registration of amplicon signal and protein rounds 
        % output_format = p.Results.norm_out_format;
        num_stains = length(sub_dirs);
        if num_stains < 4
            dapi_channel = 1;       % if number of stains is less than 4, dapi would be the first channel
        else
            dapi_channel = 4;       % during convert of vsi format, dapi would be changed to the 4th channel
        end
        
        reference_round = sprintf('round%03d', p.Results.ref_round);
        sdata = sdata.NucleiRegistrationProtein(p.Results.protein_round, reference_round, p.Results.tile, dapi_channel, ...
                                                p.Results.input_format, p.Results.norm_out_format);

        % create a specalized path to save cell images;
        protein_output_dir = fullfile(output_path, p.Results.protein_outdir);
        if ~exist(protein_output_dir, 'dir')
            mkdir(protein_output_dir);
        end
        
        sub_dirs(end+1) = "ref-DAPI";
        % sub_dirs(end+1) = "ref-DAPI_MIP" 
        SaveCellImg(protein_output_dir, sdata.proteinImages, p.Results.tile, sub_dirs);
        % 1. 输出目录
        % 2. 配准图像
        % 3. fov 编号
        % 4. 蛋白质标记物
        fprintf(sdata.log, 'protein images saved.\n');
        fclose(sdata.log);
        fprintf('Nuclei-protein registration is done!\n');
        
    end



    %% 2025-09-14: global spot Finding
    if strcmp(p.Results.mode, 'global_spot_finding')

        % initialize and create new_STARMapDataset_zf
        sdata_t = new_STARMapDataset_zf(input_path, output_path, 'useGPU', false);
        sdata_t.log = fopen(fullfile(curr_out_path_log, ...
                            strcat('log_globalspf_', num2str(p.Results.tile), '_', p.Results.spotfinding_method, '_', num2str(p.Results.intensity_threshold), '.txt')), 'w');
        fprintf(sdata_t.log, strcat('log_globalspf_', num2str(p.Results.tile), '_', p.Results.spotfinding_method, '_', num2str(p.Results.intensity_threshold), ':\n'));
        % intensity_threshold of "external tools" is probability 
        % intensity_threshold of "in-house methods" is intensity ratio


        % load local stitched image
        fprintf('Loading stitched image...\n');
        if strcmp(p.Results.loading_mode, 'local_registration')
            load(fullfile(curr_out_path, 'localRegistered_image.mat'));
        elseif strcmp(p.Results.loading_mode, 'global_registration')
            load(fullfile(curr_out_path, 'globalRegistered_image.mat'));
        elseif strcmp(p.Results.loading_mode, 'raw_preprocessed')
            load(fullfile(curr_out_path, strcat('rawPreprocessed_image.mat')));
        end


        % adjust input image matrix for spot finding
        sdata_t.registeredImages = full_image;
        % sdata_t.registeredImages = full_image(:, :, :, 2, :); % only use the second channel (actual spot channel)
        full_image = [];
        fprintf('Stitched image loaded.\n')

        % 2025-08-25: Global Spot Finding by in-house methods and Decoding
        sdata_t = sdata_t.SpotFinding('Method', p.Results.spotfinding_method, 'ref_index', p.Results.ref_round, 'intensityThreshold', p.Results.intensity_threshold, 'showPlots', false);
    
        % adjust coordinates for subtile offset and save cooordinates informations
        if size(sdata_t.allSpots,1) > 0
            % sdata_t.allSpots(:,1) = sdata_t.allSpots(:,1) + start_coords_x - 1;
            % sdata_t.allSpots(:,2) = sdata_t.allSpots(:,2) + start_coords_y - 1;   
            allSpots_t = [table(sdata_t.allSpots(:,1), sdata_t.allSpots(:,2), sdata_t.allSpots(:,3), ...
                                sdata_t.allSpots(:,4), sdata_t.allSpots(:,6), ...
                                'VariableNames',{'x','y','z','intensity','channel'})]
        else
            allSpots_t = table([],[],[],[],[],'VariableNames',{'x','y','z','intensity','channel'});
        end

        writetable(allSpots_t, fullfile(curr_out_path, strcat('allSpots_', p.Results.spotfinding_method, '_', num2str(p.Results.intensity_threshold), '.csv')),'Delimiter',',','QuoteStrings',false);
        fprintf('allSpots saved.\n');
        fclose(sdata_t.log);

    end



    % 2025-08-13: Spot Finding
    if strcmp(p.Results.mode,'local_spot_finding')

        coords_mat =readtable(fullfile(interm_output_dir,strcat('coords_mat_',num2str(p.Results.sqrt_pieces^2),'.csv')),'ReadVariableNames',true,'TextType','string');
        % goodSpots = table([],[],[],[],'VariableNames',{'x','y','z','Gene'});
        
        t = p.Results.subtile;
        input_dim_t = input_dim;
        tile_idx = table2array(coords_mat(t,2:3));
        start_coords_x = table2array(coords_mat(t,4));
        start_coords_y = table2array(coords_mat(t,5));
        upper_left = table2array(coords_mat(t,8:9));
        input_dim_t(1:2) = table2array(coords_mat(t,10:11));

        % initialize and load local registered subtile 
        sdata_t = new_STARMapDataset_zf(input_path, output_path, 'useGPU', false);
        sdata_t.log = fopen(fullfile(curr_out_path_log, strcat('log_t',num2str(p.Results.subtile),'_',num2str(p.Results.sqrt_pieces^2),'.txt')), 'w');
        fprintf(sdata_t.log, strcat('log_t',num2str(p.Results.subtile),'_',num2str(p.Results.sqrt_pieces^2),':\n'));
        
        % load local registration data
        load(fullfile(interm_output_dir, strcat('local_registeredImages_t', num2str(p.Results.subtile), '_', num2str(p.Results.sqrt_pieces^2), '.mat')));
        sdata_t.registeredImages = local_reg_out;
        local_reg_out = [];

        sdata_t.dims = input_dim_t;
        sdata_t.dimX = input_dim_t(1);
        sdata_t.dimY = input_dim_t(2);
        sdata_t.dimZ = input_dim_t(3);
        sdata_t.Nchannel = p.Results.n_chs;
        sdata_t.Nround = p.Results.n_rounds;

        % spot finding
        sdata_t = sdata_t.SpotFinding('Method', p.Results.spotfinding_method, 'ref_index', p.Results.ref_round, 'intensityThreshold', p.Results.intensity_threshold, 'showPlots', false);
        
        % adjust coordinates for subtile offset and save cooordinates informations
        if size(sdata_t.allSpots,1) > 0
            sdata_t.allSpots(:,1) = sdata_t.allSpots(:,1) + start_coords_x - 1;
            sdata_t.allSpots(:,2) = sdata_t.allSpots(:,2) + start_coords_y - 1;   
            allSpots_t = [table(sdata_t.allSpots(:,1),sdata_t.allSpots(:,2),sdata_t.allSpots(:,3),sdata_t.allSpots(:,4),'VariableNames',{'x','y','z','intensity'})]
        else
            allSpots_t = table([],[],[],[],'VariableNames',{'x','y','z','intensity'});
        end

        writetable(allSpots_t, fullfile(interm_output_dir, strcat('allSpots_', p.Results.spotfinding_method, '_t',num2str(p.Results.subtile),'_',num2str(p.Results.sqrt_pieces^2),'.csv')),'Delimiter',',','QuoteStrings',false);

        fclose(sdata_t.log);
    end







    % 2025-08-13: Local Reads extraction and filtration
    if strcmp(p.Results.mode,'local_reads_decoding')

        % get subtile coordinate position data
        coords_mat =readtable(fullfile(interm_output_dir,strcat('coords_mat_',num2str(p.Results.sqrt_pieces^2),'.csv')),'ReadVariableNames',true,'TextType','string');
        
        t = p.Results.subtile; % subtile index
        input_dim_t = input_dim; % [X, Y, Z, C, R] -> [X_t, Y_t, Z, C, R]
        tile_idx = table2array(coords_mat(t,2:3));              % 2D index of subtile
        start_coords_x = table2array(coords_mat(t,4));
        start_coords_y = table2array(coords_mat(t,5));          % start coordinates of subtile
        upper_left = table2array(coords_mat(t,8:9));            % mosaic coordinates of subtile
        input_dim_t(1:2) = table2array(coords_mat(t,10:11));    % real dimensions of overlapped subtile
    
        % initialize and load local_registered subtile 
        sdata_t = new_STARMapDataset_zf(input_path, output_path, 'useGPU', false);
        sdata_t.log = fopen(fullfile(curr_out_path_log, ...
                            strcat('log_decode', num2str(p.Results.subtile), '_', num2str(p.Results.sqrt_pieces^2),'.txt')), 'w');
        fprintf(sdata_t.log, strcat('log_decode',num2str(p.Results.subtile),'_',num2str(p.Results.sqrt_pieces^2),':\n'));

        % load local registered images of corresponding subtile into sdata_t (matlab obj)
        % load(fullfile(interm_output_dir, strcat('registeredImages_','t',num2str(p.Results.subtile),'_',num2str(p.Results.sqrt_pieces^2),'.mat')));
        load(fullfile(interm_output_dir, strcat('local_registeredImages_t', num2str(p.Results.subtile), '_', num2str(p.Results.sqrt_pieces^2), '.mat')));
        sdata_t.registeredImages = local_reg_out;
        local_reg_out = [];

        % load dimensions and other parameters into sdata_t (matlab obj)
        sdata_t.dims = input_dim_t;
        sdata_t.dimX = input_dim_t(1);
        sdata_t.dimY = input_dim_t(2);
        sdata_t.dimZ = input_dim_t(3);
        sdata_t.Nchannel = p.Results.n_chs;
        sdata_t.Nround = p.Results.n_rounds;
        

        % load spots finding results of corresponding subtile into sdata_t (matlab obj)
        allSpots_t = readtable(fullfile(interm_output_dir, strcat('allSpots_', p.Results.spotfinding_method, '_t',num2str(p.Results.subtile),'_',num2str(p.Results.sqrt_pieces^2),'.csv')));
        if istable(allSpots_t)
            allSpots_t = table2array(allSpots_t);
        end
        sdata_t.allSpots = allSpots_t;

        % decode color information to barcode sequences
        sdata_t = sdata_t.ReadsExtraction('voxelSize', p.Results.voxel_size, 'interm_outpath', interm_output_dir);

        if strcmp(p.Results.barcode_mode, "duo")
            sdata_t = sdata_t.LoadCodebook('remove_index', p.Results.split_loc);
            sdata_t = sdata_t.ReadsFiltration('mode', "duo", 'endBases', p.Results.end_bases, 'split_loc', p.Results.split_loc, 'showPlots', false);
        elseif strcmp(p.Results.barcode_mode, "regular")
            % sdata_t = sdata_t.LoadCodebook();
            sdata_t = sdata_t.LoadCodebook('remove_index', p.Results.split_loc);
            sdata_t = sdata_t.ReadsFiltration('mode', "regular", 'endBases', p.Results.end_bases, 'showPlots', false);
        elseif strcmp(p.Results.barcode_mode, "tri")
            sdata_t = sdata_t.LoadCodebook('remove_index', p.Results.split_loc);
            sdata_t = sdata_t.ReadsFiltration('mode', "tri", 'endBases', p.Results.end_bases, 'split_loc', p.Results.split_loc, 'showPlots', false);
        elseif strcmp(p.Results.barcode_mode, "double")
            sdata_t = sdata_t.LoadCodebook('mode', "regular", 'remove_index', p.Results.split_loc);
            sdata_t = sdata_t.ReadsFiltration('mode', "duo", 'endBases', p.Results.end_bases, 'showPlots', false);
        else
            fprintf(sdata_t.log, "Reads filtration incomplete: invalid mode entered (valid options include 'regular', 'duo', and 'tri'");
        end
        

        %%% Save results
        if size(sdata_t.goodSpots, 1) > 0
            sdata_t.goodSpots(:,1) = sdata_t.goodSpots(:,1) + start_coords_x - 1;
            sdata_t.goodSpots(:,2) = sdata_t.goodSpots(:,2) + start_coords_y - 1;

            coords_table = table( ...
                sdata_t.goodSpots(:,1), ...
                sdata_t.goodSpots(:,2), ...
                sdata_t.goodSpots(:,3), ...
                'VariableNames', {'x', 'y', 'z'} ...
            );

            gene_table = cell2table( ...
                cellfun(@(x) sdata_t.seqToGene(x), sdata_t.goodReads, 'UniformOutput', false), ...
                'VariableNames', {'Gene'} ...
            );

            goodSpots_t = [coords_table, gene_table];

        else
            goodSpots_t = table([], [], [], [], 'VariableNames', {'x','y','z','Gene'});
        end


        writetable(goodSpots_t,fullfile(interm_output_dir, strcat('goodPoints_', p.Results.spotfinding_method, '_t',num2str(p.Results.subtile),'_',num2str(p.Results.sqrt_pieces^2),'.csv')),'Delimiter',',','QuoteStrings',false);

        % obj.allSpots_raw, obj.allScores_raw, obj.allReads_raw, obj.basecsMat_raw
        % --- Part 1: 处理坐标数据 (Spots) ---
        if size(sdata_t.allSpots_raw, 1) > 0
            % 根据起始坐标调整 spot 的全局位置
            sdata_t.allSpots_raw(:, 1) = sdata_t.allSpots_raw(:, 1) + start_coords_x - 1;
            sdata_t.allSpots_raw(:, 2) = sdata_t.allSpots_raw(:, 2) + start_coords_y - 1;
            
            % 创建坐标表格
            allSpots_raw_t = table(sdata_t.allSpots_raw(:, 1), sdata_t.allSpots_raw(:, 2), sdata_t.allSpots_raw(:, 3), ...
                                'VariableNames', {'x', 'y', 'z'});
        else
            % 如果没有 spot 数据，则创建一个空的坐标表
            allSpots_raw_t = table([], [], [], 'VariableNames', {'x', 'y', 'z'});
        end

        % --- Part 2: 处理分数数据 (Scores) ---
        if size(sdata_t.allScores_raw, 1) > 0
            % 创建分数表格
            allScores_raw_t = table(sdata_t.allScores_raw(:, 1), sdata_t.allScores_raw(:, 2), sdata_t.allScores_raw(:, 3), ...
                                sdata_t.allScores_raw(:, 4), sdata_t.allScores_raw(:, 5), sdata_t.allScores_raw(:, 6), ...
                                sdata_t.allScores_raw(:, 7), sdata_t.allScores_raw(:, 8), sdata_t.allScores_raw(:, 9), ...
                                'VariableNames', {'round001', 'round002', 'round003', 'round004', 'round005', 'round006', ...
                                                    'round007', 'round008', 'round009'});
        else
            % 如果没有 score 数据，则创建一个空的分数表
            allScores_raw_t = table([], [], [], [], [], [], [], [], [], ...
                                'VariableNames', {'round001', 'round002', 'round003', 'round004', 'round005', 'round006', ...
                                                    'round007', 'round008', 'round009'});
        end

        % --- Part 3: 处理序列数据 (Reads) ---
        if size(sdata_t.allReads_raw, 1) > 0
            % 创建序列颜色表格
            allReads_raw_t = table(sdata_t.allReads_raw(:, 1), 'VariableNames', {'colorseq'});
            disp('allReads_raw_t is done!')
        else
            % 如果没有 read 数据，则创建一个空的序列颜色表
            allReads_raw_t = table([], 'VariableNames', {'colorseq'});
            disp('allReads_raw_t is empty!')
        end 

        % =========================================================================
        % --- Part 4: 水平拼接所有表格 ---
        % =========================================================================
        % subtiled_raw_data_t = [allSpots_raw_t, allScores_raw_t, allReads_raw_t];

        % 4.1: 首先获取并打印每个表格的行数，用于日志追溯
        nRows_spots = size(allSpots_raw_t, 1);
        nRows_scores = size(allScores_raw_t, 1);
        nRows_reads = size(allReads_raw_t, 1);

        fprintf('即将拼接表格，各部分行数检查:\n');
        fprintf('  - 坐标 (Spots)  行数: %d\n', nRows_spots);
        fprintf('  - 分数 (Scores) 行数: %d\n', nRows_scores);
        fprintf('  - 序列 (Reads)  行数: %d\n', nRows_reads);

        % 4.2: 检查所有表格的行数是否都相等
        % if (nRows_spots == nRows_scores) && (nRows_scores == nRows_reads)
        if (nRows_spots == nRows_scores)
            
            fprintf('行数匹配，执行表格拼接操作。\n');
            try
                subtiled_raw_data_t = [allSpots_raw_t, allScores_raw_t];
                fprintf('表格拼接成功。\n');
            catch ME % ME 是一个包含错误信息的对象
                % 这种情况很少发生，但作为保险措施存在
                warning('表格行数相同但拼接失败！错误信息: %s', ME.message);
                fprintf('将创建一个空的 table 作为替代。\n');
                subtiled_raw_data_t = table();
            end
            
        else
            % 如果行数不匹配，则发出警告并跳过拼接
            warning('表格行数不匹配！无法进行拼接。');
            fprintf('将创建一个空的 table 作为替代，以保证程序继续运行。\n');

            subtiled_raw_data_t = table();
        end

        writetable(subtiled_raw_data_t,fullfile(interm_output_dir, strcat('subtiled_rawFinding_', p.Results.spotfinding_method, '_t',num2str(p.Results.subtile),'_',num2str(p.Results.sqrt_pieces^2),'.csv')),'Delimiter',',','QuoteStrings',false);
        
        writetable(allReads_raw_t, fullfile(interm_output_dir, strcat("subtiled_rawReads_", p.Results.spotfinding_method, "_t", num2str(p.Results.subtile), "_", num2str(p.Results.sqrt_pieces^2), ".csv")),'Delimiter',',','QuoteStrings',false);

        fclose(sdata_t.log);
    end
    

    % Stitch
    if strcmp(p.Results.mode,'stitch')
        %%% get subtile configuration
        coords_mat = readtable(fullfile(interm_output_dir,strcat('coords_mat_',num2str(p.Results.sqrt_pieces^2),'.csv')),'ReadVariableNames',true,'TextType','string');
        goodSpots = table([],[],[],[],'VariableNames',{'x','y','z','Gene'});
        % goodSpots = table([],[],[],'VariableNames',{'x','y','z'});
        subtiled_rawFinding_table = table([],[],[],[],[],[],[],[],[],[],[],[],'VariableNames',{'x','y','z','round001','round002','round003','round004','round005','round006','round007','round008','round009'});
        
        
        %%% iteratively aggregate subtile spots
        for t=1:size(coords_mat,1)
            start_coords_x = table2array(coords_mat(t,4));      % overlap start coordinates
            start_coords_y = table2array(coords_mat(t,5));
            upper_left = table2array(coords_mat(t,8:9));        % mosaic start coordinates

            disp(fullfile(interm_output_dir, strcat('goodPoints_', p.Results.spotfinding_method, '_t', num2str(t), '_', num2str(p.Results.sqrt_pieces^2), '.csv')))

            goodSpots_t = readtable(fullfile(interm_output_dir,strcat('goodPoints_',p.Results.spotfinding_method,'_t',num2str(t),'_',num2str(p.Results.sqrt_pieces^2),'.csv')),'ReadVariableNames',true,'TextType','string');

            subtiled_raw_data_t = readtable(fullfile(interm_output_dir, strcat('subtiled_rawFinding_', p.Results.spotfinding_method, '_t',num2str(t),'_',num2str(p.Results.sqrt_pieces^2),'.csv')),'ReadVariableNames',true,'TextType','string');

        
            % filter based on overlap region
            if size(goodSpots,1) > 0
                goodSpots = goodSpots((table2array(goodSpots(:,1)) <= upper_left(1)) | (table2array(goodSpots(:,2)) <= upper_left(2)),:);
            end

            if size(goodSpots_t,1) > 0
                goodSpots_t = goodSpots_t((table2array(goodSpots_t(:,1)) > upper_left(1)) & (table2array(goodSpots_t(:,2)) > upper_left(2)),:);
            else
                goodSpots_t = table([],[],[],[],'VariableNames',{'x','y','z','Gene'});
            end
            goodSpots = [goodSpots;goodSpots_t];

            % filter based on overlap region
            if size(subtiled_rawFinding_table,1) > 0
                subtiled_rawFinding_table = subtiled_rawFinding_table((table2array(subtiled_rawFinding_table(:,1)) <= upper_left(1)) | (table2array(subtiled_rawFinding_table(:,2)) <= upper_left(2)),:);
            end

            if size(subtiled_raw_data_t,1) > 0
                subtiled_raw_data_t = subtiled_raw_data_t((table2array(subtiled_raw_data_t(:,1)) > upper_left(1)) & (table2array(subtiled_raw_data_t(:,2)) > upper_left(2)),:);
            else
                subtiled_raw_data_t = table([],[],[],[],[],[],[],[],[],[],[],[],'VariableNames',{'x','y','z','round001','round002','round003','round004','round005','round006','round007','round008','round009'});
            end
            subtiled_rawFinding_table = [subtiled_rawFinding_table;subtiled_raw_data_t];

        end
        
        % textout the number of lines of goodSpots and subtiled_rawFinding_table
        disp(strcat('Number of goodSpots: ',num2str(size(goodSpots,1))));
        disp(strcat('Number of allSpots: ',num2str(size(subtiled_rawFinding_table,1))));

        writetable(goodSpots,fullfile(curr_out_path, strcat('goodPoints_',p.Results.spotfinding_method,'.csv')),'Delimiter',',','QuoteStrings',false);
        writetable(subtiled_rawFinding_table, fullfile(curr_out_path, strcat('subtiled_rawFinding_',p.Results.spotfinding_method,'.csv')),'Delimiter',',','QuoteStrings',false);
        disp(strcat(input_path,"  Work Finished!!!!!"))
    end


    if strcmp(p.Results.mode,'plot_back')
        pass
    end