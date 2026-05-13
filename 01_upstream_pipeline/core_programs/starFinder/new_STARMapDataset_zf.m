    classdef new_STARMapDataset_zf
	% Morgan comment
    % STARMapDataset, the primary class for the STARMap imaging analysis pipeline
    % ====Properties====
    % *IO*
    % inputPath: primary path of the input folder
    % outputPath: primary path of the input folder, usually inputPath/output
    
    % *GPU*
    % useGPU: state of GPU utilization
    
    % *Images*
    % rawImages: 5-D array raw cDNA amplicon images of multiple rounds 
    % registeredImages: 5-D array registered images
    % gpuImages: 5-D array registered images on GPU
    % cellImages
    % labelImages
    % dims: dimension of the rawImages
    % Nround: number of imaging round
    % Nchannel: number of channel of image
    % dimX
    % dimY
    % dimZ
    % Ncells
    
    % *Spots*
    % allSpots: all spots/points found in the image
    % goodSpots: spots/points left after filtration

    % allSpots_raw
    
    % *Reads*
    % allReads: all reads extracted from all spots/points
    % goodReads: reads left after filtration 
    % goodReadsLoc: locations of good reads
    % allScores: scores of all reads
    % goodScores: scores of good reads
    % FilterScores

    % allReads_raw
    % allScores_raw
    % basecsMat_raw

    % Codebook
    % seqToGene: map(dictionary) color sequence --> gene
    % geneToSeq: map(dictionary) gene --> color sequence
    % barcodeMat:
    % barcodeNames:
    % barcodeSeqs:
    % basecsMat:

    % Expression
    % allCounts:
    % geneByCells:

    % Metadata
    % jobFinished:
    
    % ====Methods====
    % ...
    
    properties
        
        % IO
        inputPath;
        outputPath;
        
        % GPU
        useGPU;
        
        % Images 
        rawImages;
        registeredImages;
        gpuImages;
        cellImages;
        labelImages;
        proteinImages;
        dims;
        Nround;
        Nchannel;
        dimX;
        dimY;
        dimZ;
        Ncells;
        
        % Spots
        allSpots;
        goodSpots;
        allIntensity;
        maxIntensity;
        goodAllIntensity;
        goodMaxIntensity;

        allSpots_raw;
        allIntensity_raw;
        maxIntensity_raw;
        
        % Reads
        allReads;
        goodReads;
        goodReadsLoc;
        allScores;
        goodScores;
        FilterScores;

        allReads_raw
        allScores_raw
        basecsMat_raw
        
        % Codebook
        seqToGene;
        geneToSeq;
        barcodeMat;
        barcodeNames;
        barcodeSeqs;
        basecsMat;
        
        % Expression
        allCounts;
        geneByCells;
        
        % Metadata
        jobFinished;
        log;
        
    end
    
    methods
        
        % 1.Construction method of Pipeline object
        function obj = new_STARMapDataset_zf( inputPath, outputPath, varargin )
            % the construction method of pipeline object, use this to create
            % an object to start analysis by providing an inputPath
            % useGPU: default == false
            
            % Input parser
            p = inputParser;
            
            defaultuseGPU = false;
            addRequired(p, 'inputPath');
            addRequired(p, 'outputPath');
            addOptional(p, 'useGPU', defaultuseGPU);
            parse(p, inputPath, outputPath, varargin{:});
            
            % setup IO
            obj.inputPath = p.Results.inputPath;
            % obj.outputPath = fullfile(obj.inputPath, 'output');
            obj.outputPath = p.Results.outputPath;
            
            % make output folder
            if ~exist(obj.outputPath, 'dir')
                mkdir(obj.outputPath)
            end
            
            % create log file 
            % obj.log = fopen(fullfile(obj.outputPath, 'log.txt'), 'w');
            
            % setup GPU usage
            obj.useGPU = p.Results.useGPU;
            
            % setup metadata
            obj.jobFinished = struct('LoadRawImages', 0);
            
            % show message
            fprintf('Pipeline Obj is generated...\n');
            
        end

        % 2.Load raw images 
        function obj = LoadRawImages( obj, varargin )

            % Input parser
            p = inputParser;
            
            defaultsubdir = '';
            defaultinputDim = [];
            defaultinputFormat = 'uint8';
            
            defaultzrange = '';
            defaultclass = "mat";
            defaultuseGPU = false;
            addOptional(p, 'sub_dir', defaultsubdir);
            addOptional(p, 'input_dim', defaultinputDim);
            addOptional(p, 'input_format', defaultinputFormat);
            
            addOptional(p, 'zrange', defaultzrange);
            addOptional(p, 'output_class', defaultclass);
            addOptional(p, 'useGPU', defaultuseGPU);
            parse(p, varargin{:});
            
            % Load tiff stacks from inputPath
            fprintf('====Loading raw images====\n');
            output_format = p.Results.input_format;         % output format should be consistent with input format
            %obj.rawImages = new_LoadImageStacks(obj.inputPath, dims, p.Results.sub_dir, false);
            [obj.rawImages, obj.dims] = test_LoadImageStacks_zf(obj.inputPath, p.Results.sub_dir, ...
                                        p.Results.input_dim, p.Results.input_format, output_format, ...
                                        p.Results.zrange, p.Results.output_class, false);
            
            obj.dimX = obj.dims(1);
            obj.dimY = obj.dims(2);
            obj.dimZ = obj.dims(3);
            disp(obj.dims);
            if length(obj.dims) > 3
                obj.Nchannel = obj.dims(4);
            else
                obj.Nchannel = 1;
            end
            if length(obj.dims) > 4
                obj.Nround = obj.dims(5);
            else
                obj.Nround = 1;
            end


            
            % change metadata
            obj.jobFinished.LoadRawImages = class(obj.rawImages);
            
        end
        
        
        % 2.5.Swap channels (1 & 2)
        function obj = SwapChannels( obj, varargin )
            
            % Input parser
            p = inputParser;
            
            defaultChannel_1 = 1;
            defaultChannel_2 = 2;
            addOptional(p, 'channel_1', defaultChannel_1);
            addOptional(p, 'channel_2', defaultChannel_2);
            parse(p, varargin{:});
            
            % swap channels
            fprintf('====Swap Channels====\n');
            fprintf(sprintf('Channel %d <==> Channel %d\n', p.Results.channel_1, p.Results.channel_2));
            obj.rawImages = SwapTwoChannels(obj.rawImages, p.Results.channel_1, p.Results.channel_2);
            
            % change metadata
            obj.jobFinished.SwapChannels = [1 p.Results.channel_1 p.Results.channel_2];
            
        end
        
        
        % 3.Min-Max intensity normalization
        function obj = MinMaxNormalize( obj, varargin )
            p = inputParser;
            % Defaults
            defaultoutputFormat = 'uint8';
            addOptional(p, 'output_format', defaultoutputFormat);
            parse(p, varargin{:});
            
            % obj.registeredImages = new_MinMaxNorm(obj.rawImages);
            obj.rawImages = new_MinMaxNorm(obj.rawImages, p.Results.output_format);
            
            % change metadata
            obj.jobFinished.MinMaxNormalization = 1;
            
        end

        % 3.1 Percenile normalization
        function obj = PercenNormalize( obj, varargin )
            p = inputParser;
            % Defaults
            defaultoutputFormat = 'uint8';
            defaultPercenMinper = 0;
            defaultPercenMaxper = 100;

            addParameter(p, 'output_format', defaultoutputFormat);
            addParameter(p, 'minper', defaultPercenMinper);
            addParameter(p, 'maxper', defaultPercenMaxper)
            parse(p, varargin{:})

            obj.rawImages = new_PercenNorm(obj.rawImages, p.Results.output_format, p.Results.minper, p.Results.maxper);

            % change metadata
            obj.jobFinished.PercenNormalization = 1;
        end

        % sdata = sdata.fixedScaleNormalize('output_format', p.Results.norm_out_format, 'fixedMax', p.Results.fixedMax, 'fixedMin', p.Results.fixedMin); fixedScaleNormalize
        % 3.2 fixed scale Normalization
        function obj = fixedScaleNormalize( obj, varargin )
            p = inputParser;
            % Defaults
            defaultoutputFormat = 'uint8';
            defaultfixedMin = 0;
            defaultfixedMax = 255;


            addParameter(p, 'output_format', defaultoutputFormat);
            addParameter(p, 'fixedMin', defaultfixedMin);
            addParameter(p, 'fixedMax', defaultfixedMax);
            parse(p, varargin{:});

            obj.rawImages = new_FixedScaleNorm(obj.rawImages, p.Results.output_format, p.Results.fixedMin, p.Results.fixedMax);

            % change metadata
            obj.jobFinished.fixedScaleNormalization = 1;
        end
        
        

        
        
        % 4.Morphological reconstruction
        function obj = MorphoRecon( obj, varargin )
            
            % Input parser
            p = inputParser;
            
            % Defaults
            defaultMethod = "2d";
            defaultRadius = 6;
            defaultHeight = 3;
            defaulterode = 1;
            defaulttransform = 1;

            addParameter(p,'Method',defaultMethod);
            addParameter(p,'radius',defaultRadius);
            addParameter(p,'height',defaultHeight);
            addParameter(p,'erode',defaulterode);
            addParameter(p,'transform',defaulttransform);


            parse(p, varargin{:});
            
            fprintf("====Morphological Reconstruction====\n");
            fprintf(sprintf('Method: %s\n', p.Results.Method));
            
            % GPU test
            if obj.useGPU
                
                % setup structure element
                se = strel('disk', p.Results.radius);

                for r=1:obj.Nround
                    tic
                    fprintf(sprintf("Processing Round %d...", r));

                    for c=1:obj.Nchannel
                        curr_channel = gpuArray(obj.rawImages(:,:,:,c,r));
                        for z=1:obj.dimZ
                            curr_slice = curr_channel(:,:,z);
                            marker = imerode(curr_slice, se); % Morphological opening is useful for removing small objects from an image while preserving the shape and size of larger objects in the image
                            obr = imreconstruct(marker, curr_slice);
                            curr_out = curr_slice - obr;

                            curr_out = imsubtract(imadd(curr_out, imtophat(curr_out, se)), imbothat(curr_out, se));

                            curr_channel(:,:,z) = curr_out;
                        end
                        obj.rawImages(:,:,:,c,r) = gather(uint8(curr_channel));
                    end
                    fprintf(sprintf('[time = %.2f s]\n', toc));
                end 
   

                % obj.rawImages = im_mat2cell(obj.rawImages);
                % for r=1:obj.Nround
                %     obj.rawImages{r} = gpuArray(obj.rawImages{r});
                % end
                %     obj.rawImages = cell_MorphologicalReconstruction(obj.rawImages, p.Results.Method, p.Results.radius, p.Results.height);
                    
                % for r=1:obj.Nround   
                %     obj.rawImages{r} = gather(obj.rawImages{r});
                % end
                % obj.rawImages = im_cell2mat(obj.rawImages);
            else
                obj.rawImages = new_MorphologicalReconstruction(obj.rawImages, p.Results.Method, ...
                                                                'radius', p.Results.radius, 'height', p.Results.height, ...
                                                                'erode', p.Results.erode, 'transform', p.Results.transform);
                % obj.registeredImages = new_MorphologicalReconstruction(obj.registeredImages, p.Results.Method, p.Results.radius, p.Results.height);
            end
            
            % change metadata
            obj.jobFinished.MorphologicalReconstruction = 1;
            
        end
        
        
        % 5.Global registration
        function obj = GlobalRegistration( obj, varargin )
            
            % Input parser
            p = inputParser;
            
            % Defaults
            defaultRef = 1;
            defaultnblocks = [1 1];
            defaultuseOverlay = false;

            addOptional(p,'ref_round',defaultRef);
            addOptional(p,'nblocks',defaultnblocks);
            addOptional(p,'useOverlay',defaultuseOverlay);
            parse(p, varargin{:});
            
            
            fprintf('====Global Registration====\n');
            fprintf(sprintf('Reference round: %d\n', p.Results.ref_round));
            fprintf(sprintf('Use overlay: %d\n', p.Results.useOverlay));
            
            obj.registeredImages = will_JointRegister3D(obj.rawImages, p.Results.ref_round, p.Results.nblocks, p.Results.useOverlay);


            % change metadata
            obj.jobFinished.GlobalRegistration = [1 p.Results.ref_round, p.Results.nblocks p.Results.useOverlay];
            
        end
        
        % 5.5.Global registration
        function obj = test_GlobalRegistration( obj, varargin )
            % Input parser
            p = inputParser;
            
            % Defaults
            defaultRef = 1;
            defaultuseGPU = obj.useGPU;
            defaultAlignBasis = "maxProjection";

            addOptional(p,'ref_round',defaultRef);
            addOptional(p, 'useGPU', defaultuseGPU);
            addOptional(p, 'alignBasis', defaultAlignBasis);
            parse(p, varargin{:});
            
            Size = size(obj.rawImages);
            Class = class(obj.rawImages);

            if Size(4) == 4
                spot_channel = 3;
            else
                spot_channel = Size(4);
            end
            
            fprintf('====Global Registration====\n');
            % output_reg = zeros(size(obj.rawImages), 'uint8');
            % output_reg(:,:,:,:,p.Results.ref_round) = obj.rawImages(:,:,:,:,p.Results.ref_round);
            % obj.registeredImages = zeros(size(obj.rawImages), 'uint8');
            % obj.registeredImages = zeros(size(obj.rawImages), 'uint16');
            obj.registeredImages = zeros(Size, Class);      % construct new image stack of specific data type
            obj.registeredImages(:,:,:,:,p.Results.ref_round) = obj.rawImages(:,:,:,:,p.Results.ref_round);
            
            rounds = 1:obj.Nround;
            rounds = rounds(rounds ~= p.Results.ref_round);
            channels = 1:obj.Nchannel;
            
            if p.Results.useGPU
                
                for r=rounds
                    tic;
                    % ref_round = gpuArray(obj.rawImages(:,:,:,:,p.Results.ref_round));
                    % fix = max(ref_round, [], 4);

                    ref_round = obj.rawImages(:,:,:,:,p.Results.ref_round);
                    fix = gpuArray(max(ref_round, [], 4));
                    
                    % curr_round = gpuArray(obj.rawImages(:,:,:,:,r));
                    % curr_mov = max(curr_round, [], 4);
                    
                    curr_round = obj.rawImages(:,:,:,:,r);
                    curr_mov = gpuArray(max(curr_round, [], 4));

                    params = DFTRegister3D(fix, curr_mov, false);
                    % disp("DFTRegister success!");
                    for c=channels   % 修改这里的循环
                        curr_reg = DFTApply3D(gpuArray(curr_round(:,:,:,c)), params, false);
                        curr_round(:,:,:,c) = curr_reg;
                    end

                    obj.registeredImages(:,:,:,:,r) = gather(curr_round);
                    % fprintf(sprintf('Round %d vs. Round %d finished [time=%02f]\n', r, 1, toc));
                    % fprintf(obj.log, sprintf('Round %d vs. Round %d finished [time=%02f]\n', r, 1, toc));
                    fprintf(sprintf('Round %d vs. Round %d finished [time=%02f]\n', r, p.Results.ref_round, toc));
                    fprintf(obj.log, sprintf('Round %d vs. Round %d finished [time=%02f]\n', r, p.Results.ref_round, toc));
                    fprintf(sprintf('Shifted by %s\n', num2str(params.shifts)));
                    fprintf(obj.log, sprintf('Shifted by %s\n', num2str(params.shifts)));
                    reset(gpuDevice);
                end
               
            else
                for r=rounds
                    starting = tic;
                    ref_round = obj.rawImages(:,:,:,:,p.Results.ref_round);
                    curr_round = obj.rawImages(:,:,:,:,r);

                    if p.Results.alignBasis == "maxProjection"
                        fix = max(ref_round(:,:,:,1:spot_channel), [], 4);
                        curr_mov = max(curr_round(:,:,:,1:spot_channel), [], 4);
                    elseif p.Results.alignBasis == "dapi"
                        fix = ref_round(:,:,:,end);  % DAPI 通道 stack
                        curr_mov = curr_round(:,:,:,end);  % 当前轮的 DAPI 通道 stack
                    end

                    params = DFTRegister3D(fix, curr_mov, false);
                    % disp("DFTRegister success!");
                    fprintf(sprintf('DFT register finished [time=%02f]\n', toc(starting)));
                    
                    starting_apply = tic;
                    for c=channels   % 修改这里的循环
                        curr_reg = DFTApply3D(curr_round(:,:,:,c), params, false);
                        curr_round(:,:,:,c) = curr_reg;
                    end
                    fprintf(sprintf('DFT apply finished [time=%02f]\n', toc(starting_apply)));
                    
                    obj.registeredImages(:,:,:,:,r) = curr_round;
                    % output_reg(:,:,:,:,r) = curr_round;
                    % fprintf(sprintf('Round %d vs. Round %d finished [time=%02f]\n', r, 1, toc));
                    % fprintf(obj.log, sprintf('Round %d vs. Round %d finished [time=%02f]\n', r, 1, toc));
                    fprintf(sprintf('Round %d vs. Round %d finished [time=%02f]\n', r, p.Results.ref_round, toc));
                    fprintf(obj.log, sprintf('Round %d vs. Round %d finished [time=%02f]\n', r, p.Results.ref_round, toc));
                    fprintf(sprintf('Shifted by %s\n', num2str(params.shifts)));
                    fprintf(obj.log, sprintf('Shifted by %s\n', num2str(params.shifts)));
                end
                
            end
            
            % obj.registeredImages = output_reg;


            % change metadata
            obj.rawImages = [];
            obj.jobFinished.test_GlobalRegistration = 1;
            
        end
        
        % 6.Local (Non-rigid) registration
        function obj = LocalRegistration( obj, varargin )

            % Input parser
            p = inputParser;
            % Defaults
            defaultRef = 1;
            defaultMethod = "max";
            defaultIter = 60;
            defaultAFS = 1;

            %addRequired(p,'object');
            addOptional(p,'ref_round',defaultRef);
            addOptional(p,'Method',defaultMethod);
            addParameter(p,'Iterations',defaultIter);
            addParameter(p,'AccumulatedFieldSmoothing',defaultAFS);

            parse(p, varargin{:});
            
            % WARNING
            if obj.useGPU
                obj.gpuImages = obj.registeredImages;
                obj.registeredImages = gather(obj.registeredImages);
            else
                obj.gpuImages = obj.registeredImages;
            end
            
            fprintf('====Local (Non-rigid) Registration====\n');
            obj = new_LocalRegistration(obj, p.Results.ref_round, 'Method', p.Results.Method, 'Iterations', p.Results.Iterations, 'AccumulatedFieldSmoothing', p.Results.AccumulatedFieldSmoothing);

            
            % change metadata
            obj.jobFinished.LocalRegistration = [1 p.Results.Method floor(log2(obj.dimZ)) p.Results.AccumulatedFieldSmoothing];
            
        end
        
        % 6.1.Local (Non-rigid) registration test
        function obj = xxx_LocalRegistration( obj, varargin )

            % Input parser
            p = inputParser;
            % Defaults
            defaultRef = 1;
            defaultMethod = "max";
            defaultIter = 60;
            defaultAFS = 1;
            defaultalignBasis = "maxProjection";

            %addRequired(p,'object');
            addOptional(p,'ref_round',defaultRef);
            addOptional(p,'Method',defaultMethod);
            addParameter(p,'Iterations',defaultIter);
            addParameter(p,'AccumulatedFieldSmoothing',defaultAFS);
            addParameter(p,'alignBasis',defaultalignBasis);

            parse(p, varargin{:});
            
            fprintf('====Local (Non-rigid) Registration====\n');
            obj = test_LocalRegistration(obj, 'ref_round', p.Results.ref_round, 'Method', p.Results.Method, ...
                                         'Iterations', p.Results.Iterations, ...
                                         'AccumulatedFieldSmoothing', p.Results.AccumulatedFieldSmoothing, ...
                                         'alignBasis', p.Results.alignBasis);

            % change metadata
            obj.jobFinished.LocalRegistration = [1 p.Results.Method floor(log2(obj.dimZ)) p.Results.AccumulatedFieldSmoothing];
            
        end
        
        
        % 6.5 DAPI registration  
        function obj = NucleiRegistration( obj, ref_dapi, move_dapi )
            
            fprintf('====Nuclei-based Registration====\n');
            

            round1_img = obj.rawImages(:,:,:,:,1);
            
            if obj.useGPU
                
                tic;
                
                fix = gpuArray(ref_dapi);
                mov = gpuArray(move_dapi);

                params = DFTRegister3D(fix, mov, false);

                for c=1:4
                    curr_reg = DFTApply3D(gpuArray(round1_img(:,:,:,c)), params, false);
                    round1_img(:,:,:,c) = curr_reg;
                end

                obj.rawImages(:,:,:,:,1) = gather(round1_img);
                fprintf(sprintf('Move nuclei vs. Ref nuclei finished [time=%02f]\n', toc));
                fprintf(obj.log, sprintf('Move nuclei vs. Ref nuclei finished [time=%02f]\n', toc));
                fprintf(sprintf('Shifted by %s\n', num2str(params.shifts)));
                fprintf(obj.log, sprintf('Shifted by %s\n', num2str(params.shifts)));
                reset(gpuDevice);
               
            else
                tic;
                params = DFTRegister3D(ref_dapi, move_dapi, false);

                for c=1:4
                    curr_reg = DFTApply3D(round1_img(:,:,:,c), params, false);
                    round1_img(:,:,:,c) = curr_reg;
                end

                obj.rawImages(:,:,:,:,1) = round1_img;
                fprintf(sprintf('Move nuclei vs. Ref nuclei finished [time=%02f]\n', toc));
                fprintf(obj.log, sprintf('Move nuclei vs. Ref nuclei finished [time=%02f]\n', toc));
                fprintf(sprintf('Shifted by %s\n', num2str(params.shifts)));
                fprintf(obj.log, sprintf('Shifted by %s\n', num2str(params.shifts)));
                reset(gpuDevice);
            end

            % change metadata
            obj.jobFinished.NucleiRegistration = 1;
            
        end
        
        
        % 6.5 use DAPI register protein images  
        function obj = NucleiRegistrationProtein( obj, protein_folder, reference_round, sub_dir, dapi_channel, ...
                                                  input_format, output_format )
            
            fprintf('====Nuclei-based Registration====\n');
            
            % dapi_formatIn = input_format;
            % dapi_formatOut = output_format;
            
            % load reference dapi image
            fprintf('Loading reference DAPI image from %s...\n', reference_round);
            ref_dapi_path = dir(fullfile(obj.inputPath, reference_round, sub_dir, "*.tif"));
            ref_dapi = new_LoadMultipageTiff(fullfile(ref_dapi_path(end).folder, ref_dapi_path(end).name), ...
                                             input_format, output_format, false);
            
            % load protein images
            protein_path = fullfile(obj.inputPath, protein_folder, sub_dir); % IF/Position{iii}
            protein_files = dir(fullfile(protein_path, '*.tif'));
            nfiles = numel(protein_files);      % 参考轮图像一起存进来
            protein_imgs = cell(nfiles, 1);  % create a cell array to store protein images

            % Load tiff files of all channels
            for c=1:nfiles 
                curr_path = strcat(protein_files(c).folder, '/', protein_files(c).name);
                curr_img = new_LoadMultipageTiff(curr_path, input_format, output_format, false);
                protein_imgs{c} = curr_img;
            end


            if obj.useGPU
                
                tic;
                
                fix = gpuArray(ref_dapi);
                mov = gpuArray(protein_imgs{dapi_channel});

                params = DFTRegister3D(fix, mov, false);

                for c=1:4
                    curr_reg = DFTApply3D(gpuArray(protein_imgs{c}), params, false);
                    protein_imgs{c} = uint8(gather(curr_reg));
                end

                obj.proteinImages = protein_imgs;
                fprintf(sprintf('Move nuclei vs. Ref nuclei finished [time=%02f]\n', toc));
                fprintf(obj.log, sprintf('Move nuclei vs. Ref nuclei finished [time=%02f]\n', toc));
                fprintf(sprintf('Shifted by %s\n', num2str(params.shifts)));
                fprintf(obj.log, sprintf('Shifted by %s\n', num2str(params.shifts)));
                reset(gpuDevice);
               
            else
                tic;
                % add 2023-03-15
                mov = protein_imgs{dapi_channel};  % args: default dapi_channel=1; here is 4
                img_class = class(mov);            % z axis 

                if size(mov, 3) == 1               % 2d images
                    params = DFTRegister2D(ref_dapi, mov, false);
                    for c=1:nfiles
                        curr_reg = DFTApply2D(protein_imgs{c}, params, false);
                        % protein_imgs{c} = uint8(curr_reg);
                        switch img_class
                            case 'uint8'
                                protein_imgs{c} = uint8(curr_reg);
                            case 'uint16'
                                protein_imgs{c} = uint16(curr_reg);
                        end
                    end
    
                    obj.proteinImages = protein_imgs;
                    fprintf(sprintf('Move nuclei vs. Ref nuclei finished [time=%02f]\n', toc));
                    fprintf(obj.log, sprintf('Move nuclei vs. Ref nuclei finished [time=%02f]\n', toc));
                    fprintf(sprintf('Shifted by %s\n', num2str(params.shifts)));
                    fprintf(obj.log, sprintf('Shifted by %s\n', num2str(params.shifts)));

                else
                    fprintf('Reference DAPI size: %s\n', mat2str(size(ref_dapi)));
                    fprintf('Moving Image size: %s\n', mat2str(size(mov)));
                    params = DFTRegister3D(ref_dapi, mov, false);

                    for c=1:nfiles
                        curr_reg = DFTApply3D(protein_imgs{c}, params, false);   % 依次应用 配准参数

                        switch img_class
                            case 'uint8'
                                protein_imgs{c} = uint8(curr_reg);
                            case 'uint16'
                                protein_imgs{c} = uint16(curr_reg);
                        end
                    end
                    % 用作固定图像的参考轮图像也存进protein_imgs，以特定命名存入IF，作为拼接配准的主要目标
                    ref_dapi_mip_raw = max(ref_dapi, [], 3); 
                    switch img_class
                        case 'uint8'
                            ref_dapi_formatted = uint8(ref_dapi);
                            ref_dapi_mip = uint8(ref_dapi_mip_raw);
                            
                        case 'uint16'
                            ref_dapi_formatted = uint16(ref_dapi);
                            ref_dapi_mip = uint16(ref_dapi_mip_raw);
                            
                        otherwise
                            ref_dapi_formatted = ref_dapi;
                            ref_dapi_mip = ref_dapi_mip_raw;
                    end
                    protein_imgs{end+1} = ref_dapi_formatted;
                    protein_imgs{end+1} = ref_dapi_mip;
    
                    obj.proteinImages = protein_imgs;   % 更新后的配准蛋白质图像 存储到 obj.proteinImages
                    fprintf(sprintf('Move nuclei vs. Ref nuclei finished [time=%02f]\n', toc));
                    fprintf(obj.log, sprintf('Move nuclei vs. Ref nuclei finished [time=%02f]\n', toc));
                    fprintf(sprintf('Shifted by %s\n', num2str(params.shifts)));
                    fprintf(obj.log, sprintf('Shifted by %s\n', num2str(params.shifts)));
                end
            end

            % change metadata
            obj.jobFinished.NucleiRegistrationProtein = 1;
            
        end
        
        
        % 7.Spot finding
        function obj = SpotFinding( obj, varargin )
            
            % Input parser
            p = inputParser;
            
            % Defaults
            defaultMethod = "max3d";
            defaultrefIndex = 1;
            defaultfsize = [5 5 3];
            defaultfsigma = 1;
            defaultintensityThreshold = 0.2;
            defaultqualityThreshold = 0.7;
            defaultvolumeThreshold = 10;
            defaultbarcodeMethod = "image";
            defaultshowPlots = true;

            addParameter(p,'Method',defaultMethod);
            addParameter(p,'intensityThreshold', defaultintensityThreshold);
            addParameter(p, 'ref_index', defaultrefIndex);
            addParameter(p, 'fsize', defaultfsize);
            addParameter(p, 'fsigma', defaultfsigma);
            addParameter(p, 'qualityThreshold', defaultqualityThreshold);
            addParameter(p, 'volumeThreshold', defaultvolumeThreshold);
            addParameter(p, 'barcodeMethod', defaultbarcodeMethod);
            addParameter(p, 'showPlots', defaultshowPlots);
            
            parse(p, varargin{:});
            
            
            fprintf('====Spot Finding====\n');
            fprintf(sprintf('Method: %s\n', p.Results.Method));
            fprintf(sprintf('Reference round: %d\n', p.Results.ref_index));
            fprintf(sprintf('Intensity threshold: %d\n', p.Results.intensityThreshold));
 
            tic
            switch p.Results.Method
                case "max3d"
                    obj.allSpots = SpotFindingMax3D(obj.registeredImages, p.Results.ref_index, p.Results.intensityThreshold);
                    obj.jobFinished.SpotFinding = [1 p.Results.Method];
                case "ex_max3d"
                    obj.allSpots = SpotFindingExtendedMax3D(obj.registeredImages, p.Results.intensityThreshold);
                    obj.jobFinished.SpotFinding = [1 p.Results.Method];
                case "log3d"
                    obj.allSpots = SpotFindingLog3D(obj.registeredImages, p.Results.ref_index, p.Results.fsize, p.Results.fsigma, p.Results.intensityThreshold);
                    obj.jobFinished.SpotFinding = [1 p.Results.Method p.Results.fsize p.Results.fsigma];
                case "barcode"
                    obj.allSpots = SpotFindingBarcode(obj.registeredImages, ...
                        obj.seqToGene, ...
                        p.Results.qualityThreshold, ...
                        p.Results.volumeThreshold, ...
                        p.Results.barcodeMethod, ...
                        p.Results.showPlots, ...
                        obj.useGPU);
                    obj.jobFinished.SpotFinding = [1 p.Results.Method ...
                        p.Results.qualityThreshold ...
                        p.Results.volumeThreshold ...
                        p.Results.barcodeMethod, ...
                        p.Results.showPlots ...
                        ];
                case "barcode_test"
                    [obj.allReads, obj.allSpots, obj.allScores, obj.basecsMat] = test_SpotFindingBarcode(obj.registeredImages, ...
                        obj.seqToGene, ...
                        p.Results.qualityThreshold, ...
                        p.Results.volumeThreshold, ...
                        p.Results.showPlots, ...
                        obj.useGPU);
                    obj.jobFinished.SpotFinding = [1 p.Results.Method ...
                        p.Results.qualityThreshold ...
                        p.Results.volumeThreshold ...
                        p.Results.barcodeMethod, ...
                        p.Results.showPlots ...
                        ];
                case "will"
                    obj.allSpots = SpotFindingWill(obj.registeredImages);
                    obj.jobFinished.SpotFinding = [1 p.Results.Method];
            end
            fprintf(sprintf('Number of spots found by %s: %d\n', p.Results.Method, size(obj.allSpots, 1)));
            fprintf(sprintf('[time = %.2f s]\n', toc));
            
            if ~isempty(obj.log)
                fprintf(obj.log, '====Spot Finding====\n');
                fprintf(obj.log, sprintf('Method: %s\n', p.Results.Method));
                fprintf(obj.log, sprintf('Reference round: %d\n', p.Results.ref_index));
                fprintf(obj.log, sprintf('Number of spots found by %s: %d\n', p.Results.Method, size(obj.allSpots, 1)));
            end
            
        end
        
        
        % 8.Reads extraction
        function obj = ReadsExtraction( obj, varargin )
            
            % Input parser
            p = inputParser;
            
            % Defaults
            defaultvoxelSize = [3 3 1];
            defaultthreshold = 0.5;
            defaultIntensityThresh_perRound = 270;
            defaultshowPlots = false;
            defaultinterm_outpath = '';
            defaultrefIndex = 1;
            defaultdecoding_rounds = obj.Nround;
            

            addParameter(p, 'voxelSize', defaultvoxelSize);
            addParameter(p, 'q_score_thers', defaultthreshold);
            addParameter(p, 'IntensityThresh_perRound', defaultIntensityThresh_perRound);
            addParameter(p, 'showPlots', defaultshowPlots);
            % 'interm_outpath'
            addParameter(p, 'interm_outpath', defaultinterm_outpath);
            addParameter(p, 'ref_index', defaultrefIndex);
            % 'decoding_rounds'
            addParameter(p, 'decoding_rounds', defaultdecoding_rounds);

            parse(p, varargin{:});
            
            fprintf('====Reads Extraction====\n');
            fprintf(sprintf('voxel size: %d x %d x %d\n', p.Results.voxelSize));
            
            % [obj.allReads, obj.allSpots, obj.allScores, obj.basecsMat] = ExtractFromLocation( obj.registeredImages, obj.allSpots, ...
            %                                                                         p.Results.voxelSize, p.Results.q_score_thers, ...
            %                                                                         p.Results.interm_outpath, p.Results.showPlots, obj.log ); 

            [obj.allReads, obj.allSpots, obj.allScores, obj.basecsMat, obj.allIntensity, obj.maxIntensity, ...
             obj.allReads_raw, obj.allSpots_raw, obj.allScores_raw, obj.basecsMat_raw, obj.allIntensity_raw, obj.maxIntensity_raw] = ...
                                                        ExtractFromLocation_stats( obj.registeredImages, obj.allSpots, ...
                                                                                    p.Results.voxelSize, p.Results.q_score_thers, ...
                                                                                    p.Results.IntensityThresh_perRound, ...
                                                                                    p.Results.interm_outpath, p.Results.ref_index, ...
                                                                                    p.Results.decoding_rounds, ...
                                                                                    p.Results.showPlots, obj.log );


            obj.jobFinished.ReadsExtraction = [1 p.Results.voxelSize];
        
        end
        
        
        % 9.Load codebook
        function obj = LoadCodebook( obj, varargin )
        
            % Input parser
            p = inputParser;
            
            % Defaults
            defaultdoReverse = true;
            defaultremoveIndex = [];
            defaultmode = "tri";
            defaultcodeMap_mode = "Olympus";            % "Olympus" / "Leica_rj"

            addParameter(p, 'remove_index', defaultremoveIndex);
            addParameter(p, 'doReverse', defaultdoReverse);
            addParameter(p, 'mode', defaultmode);
            addParameter(p, 'codeMap_mode', defaultcodeMap_mode);

            parse(p, varargin{:});
            
            fprintf('====Load Codebook====\n');
            fprintf(sprintf('mode: %s\n', p.Results.mode));
    	    fprintf(sprintf('doReverse: %d\n', p.Results.doReverse));
            % removeIndex
            fprintf(sprintf('Remove index: %s\n', num2str(p.Results.remove_index)))
            fprintf(sprintf('CodeMap_mode: %s\n', p.Results.codeMap_mode))
            % load hash tables of gene name -> seq and seq -> gene name
            % where 'seq' is the string representation of the barcode in colorspace

            switch p.Results.mode
                case "regular"
                    [obj.geneToSeq, obj.seqToGene] = new_LoadCodebook(obj.inputPath, p.Results.remove_index, ...
                                                                      p.Results.doReverse, p.Results.codeMap_mode);
                case "double"
                    [obj.geneToSeq, obj.seqToGene] = new_LoadCodebook(obj.inputPath, p.Results.remove_index, ...
                                                                      p.Results.doReverse, p.Results.codeMap_mode);
                case "duo"
                    [obj.geneToSeq, obj.seqToGene] = new_LoadCodebook(obj.inputPath, p.Results.remove_index, ...
                                                                      p.Results.doReverse, p.Results.codeMap_mode);
                case "tri"
                    [obj.geneToSeq, obj.seqToGene] = new_LoadCodebook_tri(obj.inputPath, p.Results.remove_index, ...
                                                                          p.Results.doReverse, p.Results.codeMap_mode);
                case "single_nc"
                    [obj.geneToSeq, obj.seqToGene] = new_LoadCodebook_single_nc(obj.inputPath, p.Results.remove_index, ...
                                                                          p.Results.doReverse, p.Results.codeMap_mode);
            end



            %[obj.geneToSeq, obj.seqToGene] = new_LoadCodebook(obj.inputPath, p.Results.remove_index, p.Results.doReverse);  
            
            seqStrs = obj.seqToGene.keys;
            seqCS = []; % color sequences in matrix form for computing hamming distances ie: Nbarcode x Nround double
            for i=1:numel(seqStrs)
                % seqStrs{i}
                seqCS(end+1, :) = Str2Colorseq(seqStrs{i});
            end
            obj.barcodeMat = seqCS;
            obj.barcodeNames = obj.seqToGene.values; % cell array of seq names
            obj.barcodeSeqs = obj.seqToGene.keys; % str color seqs
            
            % change metadata
            obj.jobFinished.LoadCodebook = 1;
        
        end
        
        function obj = LoadCodebook_zf( obj, varargin )
        
            % Input parser
            p = inputParser;
            
            % Defaults
            defaultdoReverse = true;
            defaultremoveIndex = [];

            addParameter(p, 'remove_index', defaultremoveIndex);
            addParameter(p, 'doReverse', defaultdoReverse);

            parse(p, varargin{:});
            
            fprintf('====Load Codebook====\n');
            fprintf(sprintf('doReverse: %d\n', p.Results.doReverse));
            % load hash tables of gene name -> seq and seq -> gene name
            % where 'seq' is the string representation of the barcode in colorspace
            [obj.geneToSeq, obj.seqToGene] = new_LoadCodebook_zf(obj.inputPath, p.Results.remove_index, p.Results.doReverse);  
            
            seqStrs = obj.seqToGene.keys;
            seqCS = []; % color sequences in matrix form for computing hamming distances ie: Nbarcode x Nround double
            for i=1:numel(seqStrs)
                % seqStrs{i}
                seqCS(end+1, :) = Str2Colorseq(seqStrs{i});
            end
            obj.barcodeMat = seqCS;
            obj.barcodeNames = obj.seqToGene.values; % cell array of seq names
            obj.barcodeSeqs = obj.seqToGene.keys; % str color seqs
            
            % change metadata
            obj.jobFinished.LoadCodebook = 1;
        
        end
        
        % 10.Reads filtration
        function obj = ReadsFiltration( obj, varargin )
            
            % Input parser
            p = inputParser;
            
            % Defaults
            defaultthreshold = 0.5;
            defaultmode = "regular";
            defaultendBases = ['A', 'A'];
            defaultsplitLoc = [5,11];
            defaultshowPlots = true;
            defaultendBasesMix = ['C', 'A'];
            defaultcodeMap_mode = "Olympus";            % "Olympus" / "Leica_rj"

            addParameter(p, 'q_score_thers', defaultthreshold);
            addParameter(p, 'mode', defaultmode);
            addParameter(p, 'endBases', defaultendBases);
            addParameter(p, 'split_loc', defaultsplitLoc);
            addParameter(p, 'showPlots', defaultshowPlots);
            addParameter(p, 'endBases_mix', defaultendBasesMix);
            addParameter(p, 'codeMap_mode', defaultcodeMap_mode);

            parse(p, varargin{:});
            
            fprintf('====Reads Filtration====\n');
            fprintf(sprintf('mode: %s\n', p.Results.mode));
            fprintf(sprintf('Base in start: %s -- \n', p.Results.endBases(1)));

            switch p.Results.mode
                case "regular"
                    % normal single barcode-mode
                    obj = new_FilterReads(obj, p.Results.endBases, p.Results.showPlots, p.Results.codeMap_mode); 
                case "double"
                    % normal double barcode-mode
                    obj = new_FilterReads_double(obj, p.Results.endBases, p.Results.showPlots, p.Results.codeMap_mode);
                case "duo"
                    % abnormal double barcode-mode
                    obj = new_FilterReads_Duo(obj, p.Results.endBases, p.Results.showPlots, p.Results.codeMap_mode);
                    %obj = new_FilterReads_Duo(obj, p.Results.endBases, p.Results.split_loc, p.Results.q_score_thers, p.Results.showPlots);
                case "tri"
                    % normal triple barcode-mode
                    obj = new_FilterReads_tri(obj, p.Results.endBases, p.Results.showPlots, p.Results.codeMap_mode);
                case "single_nc"
                    % single round non-contiuous reads filtration
                    obj = new_FilterReads_nc(obj, p.Results.endBases, p.Results.showPlots, p.Results.codeMap_mode);
                    
            end
            
            % change metadata
            obj.jobFinished.ReadsFiltration = [1 p.Results.mode];
            
        end
        
        
        % 11.Save reads
        function obj = SaveReads( obj, varargin )
            
            % Input parser
            p = inputParser;
            
            % Defaults
            defaultinputId = '';

            addOptional(p, 'inputId', defaultinputId);

            parse(p, varargin{:});
            
            fprintf('====Save Reads====\n');

            obj.allCounts = SaveGoodReads( obj, p.Results.inputId );  
            
            % change metadata
            obj.jobFinished.SaveReads = 1;   
            
            
        end
        
        
        % 12.Load cell images (should do this at the beginning)
        function obj = LoadCellImages( obj, file_path )
            
            fprintf('====Load Cell Segmentation Images====\n');
            obj.labelImages = LoadMultipageTiff(file_path, 'uint16', false);
            obj.Ncells = numel(unique(obj.labelImages)) - 1;

            
            % change metadata
            obj.jobFinished.LoadCellImages = 1;
            
        end
        
        
        % 13.Assign reads to cells 
        function obj = AssignReads( obj, varargin )
            
            fprintf('====Assign Reads to Cells====\n');
            
            % get cell idx of good reads using goodSpots
            obj.goodReadsLoc = GetReadsLocation(obj.goodSpots, obj.labelImages); 
            
            % get gene by cell expression matrix 
            obj.geneByCells = GetGeneByCells( obj ); 
            
            fprintf('====Assign Finished====\n');
            
            % change metadata
            obj.jobFinished.AssignReads = 1;
            
        end
        
    end
    
    
    methods % Optional 
        
        % 1.Load registered images
        function obj = LoadRegisteredImages( obj, inputPath, varargin )

            % Input parser
            p = inputParser;
            
            defaultuseGPU = false;
            
            addRequired(p, 'inputPath');
            addOptional(p, 'useGPU', defaultuseGPU);
            parse(p, inputPath, varargin{:});
            
            % Load tiff stacks from inputPath
            fprintf('====Loading registered images====\n');
            obj.registeredImages = new_LoadImageStacks(p.Results.inputPath, obj.dims, false);
            
            % change metadata
            obj.jobFinished.LoadRegisteredImages = 1;
            
        end
        
        % 2.Hitogram Equalization
        function obj = HistEqualize( obj, varargin )
            
            % Input parser
            p = inputParser;
            
            % Defaults
            defaultMethod = "inter_round";
            defaulthist_channel = 1;
            defaulthist_round = 1;

            addParameter(p,'Method',defaultMethod);
            addParameter(p, 'hist_channel', defaulthist_channel);
            addParameter(p, 'hist_round', defaulthist_round);

            parse(p, varargin{:});
            
            fprintf("====Histogram Equalization====\n");
            fprintf(sprintf('Method: %s\n', p.Results.Method));

            % function input_img = new_EqualizeHist3D( input_img, method, hist_channel, hist_round )

            if isempty(obj.registeredImages)
                obj.rawImages = new_EqualizeHist3D(obj.rawImages, p.Results.Method, p.Results.hist_channel, p.Results.hist_round);
                obj.jobFinished.HistogramEqualization = "rawImages";
            else
                obj.registeredImages = new_EqualizeHist3D(obj.registeredImages, p.Results.Method, p.Results.hist_channel, p.Results.hist_round);
                obj.jobFinished.HistogramEqualization = "registeredImages";
            end
            
            
            
        end
        
        % 3.Load dimension 
        function obj = LoadDim(obj, input_dim)
            
            obj.dims = input_dim;
            obj.dimX = obj.dims(1);
            obj.dimY = obj.dims(2);
            obj.dimZ = obj.dims(3);
            obj.Nchannel = obj.dims(4);
            obj.Nround = obj.dims(5);
            
        end
            
    end
    
    
    end
