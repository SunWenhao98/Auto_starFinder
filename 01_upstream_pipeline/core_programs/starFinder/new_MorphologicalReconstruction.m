function input_img = new_MorphologicalReconstruction( input_img, method, varargin )
%MorphologicalReconstruction

    % Input parser
    p = inputParser;
    
    % Defaults
    defaultRadius = 2; % org = 6
    defaultHeight = 3;
    defaulterode = 1;
    defaulttransform = 1;


    addRequired(p,'input_img');
    addRequired(p,'method');
    addParameter(p,'radius',defaultRadius);
    addParameter(p,'height',defaultHeight); 
    addParameter(p,'erode',defaulterode);
    addParameter(p,'transform',defaulttransform);

    parse(p, input_img, method, varargin{:});

    % p.Results
    
    % get dims 
    Nround = size(input_img, 5);
    Nchannel = size(input_img, 4);
    Nslice = size(input_img, 3);
    InputClass = class(input_img);      % get input class: uint8 or uint16

    % p.Results.radius
    % switch case 2D/3D
    
    switch method
        case "2d"
            % setup structure element
            se = strel('disk', p.Results.radius);

            for r=1:Nround
                tic
                fprintf(sprintf("Processing Round %d using 2D method...", r));

                for c=1:Nchannel
                    
                    curr_channel = input_img(:,:,:,c,r);
                    for z=1:Nslice
                        curr_slice = curr_channel(:,:,z);

                        % Morphological opening is useful for removing small objects from an image while preserving the shape and size of larger objects in the image
                        if p.Results.erode == 1  
                            marker = imerode(curr_slice, se);
                            obr = imreconstruct(marker, curr_slice);
                            curr_slice = curr_slice - obr;
                        end

                        % mask = imbinarize(curr_out);
                        % mask = curr_out > 0;
                        % mask = bwareaopen(mask, 1);
                        % curr_out(~mask) = 0;

                        % bw = imopen(mask, se_2);
                        % curr_out(~bw) = 0;
                        
                        if p.Results.transform == 1
                            curr_slice = imsubtract(...
                                                imadd(curr_slice, imtophat(curr_slice, se)), ...
                                                imbothat(curr_slice, se)...
                                                );
                        end
                        
                        curr_channel(:,:,z) = curr_slice;
                    end

                    switch InputClass
                        case "uint8"
                            input_img(:,:,:,c,r) = uint8(curr_channel);
                        case "uint16"
                            input_img(:,:,:,c,r) = uint16(curr_channel);
                        otherwise
                            error("Unsupported input class");
                    end
                end
                fprintf(sprintf('[time = %.2f s]\n', toc));
            end 
        

        
        case "2d_thres"             
            % setup structure element
            se = strel('disk', p.Results.radius);

            for r=1:Nround
                tic
                fprintf(sprintf("Processing Round %d...", r));

                for c=1:Nchannel

                    curr_channel = input_img(:,:,:,c,r);
                    for z=1:Nslice
                        curr_slice = curr_channel(:,:,z);
                        marker = imerode(curr_slice, se);
                        obr = imreconstruct(marker, curr_slice);
                        curr_out = curr_slice - obr;
                        
                        curr_bw = curr_out > 0 & curr_out < 80;
                        curr_out(curr_bw) = 0;
                        
                        curr_out = im2double(curr_out);
                        curr_max = max(curr_out, [], 'all');
                        curr_min = min(curr_out, [], 'all');
                        curr_out = (curr_out - curr_min) ./ (curr_max - curr_min);
                        curr_out = uint8(curr_out .* 255); %% WARNING
    
                        curr_channel(:,:,z) = curr_out;
                    end
                    % input_img{r}(:,:,:,c) = uint8(curr_channel);
                    % input_img(:,:,:,c,r) = uint8(curr_channel);
                    % input_img(:,:,:,c,r) = uint16(curr_channel);
                    
                    % return to type of input image and save memory
                    switch InputClass
                        case "uint8"
                            input_img(:,:,:,c,r) = uint8(curr_channel);
                        case "uint16"
                            input_img(:,:,:,c,r) = uint16(curr_channel);
                        otherwise
                            error("Unsupported input class");
                    end
                end
                fprintf(sprintf('[time = %.2f s]\n', toc));
            end 
            
        case "3d"
            % setup structure element for 3D
            ms = offsetstrel('ball', p.Results.radius, p.Results.height);
            se = strel('sphere', 2);
            
            for r=1:Nround 
                tic
                fprintf(sprintf("Processing Round %d...", r));

                for c=1:Nchannel
                    
                    curr_channel = input_img(:,:,:,c,r);
                    marker = imerode(curr_channel, ms);
                    obr = imreconstruct(marker, curr_channel);
                    curr_out = curr_channel - obr;
                    % mask = imbinarize(curr_out,0.06);
                    % curr_out(~mask) = 0;

                    bw = imopen(mask, se);
                    curr_out(~bw) = 0;

                    curr_out = imsubtract(imadd(curr_out, imtophat(curr_out, ms)), imbothat(curr_out, ms));
                    
                    % input_img{r}(:,:,:,c) = uint8(curr_out);
                    % input_img(:,:,:,c,r) = uint8(curr_out);
                    % input_img(:,:,:,c,r) = uint16(curr_out);
                    switch InputClass
                        case "uint8"
                            input_img(:,:,:,c,r) = uint8(curr_out);
                        case "uint16"
                            input_img(:,:,:,c,r) = uint16(curr_out);
                        otherwise
                            error("Unsupported input class");
                    end
                end
                fprintf(sprintf('[time = %.2f s]\n', toc));
            end
            
    end
    
end

