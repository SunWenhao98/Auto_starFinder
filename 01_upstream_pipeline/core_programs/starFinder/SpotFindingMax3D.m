function locations = SpotFindingMax3D( input_img, ref_index, intensityThreshold )
%SpotFindingMax3D 

    % initialize output of coordinates
    locations = [];

    % ref round is used for spot finding 
    ref_round = input_img(:,:,:,:,ref_index);
    if size(input_img, 4) > 3
        Nchannel = 3;
    else
        Nchannel = size(ref_round, 4);
    end

    InputClass = class(input_img);
    
    for c=1:Nchannel
        curr_channel = ref_round(:,:,:,c);
        curr_max = imregionalmax(curr_channel); % 3d connected regional components analysis

        % max_intensity = max(curr_channel, [], 'all');
        % curr_out = curr_max & curr_channel > intensityThreshold * max_intensity;
        switch InputClass
            case "uint8"
                curr_out = curr_max & curr_channel > intensityThreshold * 255;
            case "uint16"
                curr_out = curr_max & curr_channel > intensityThreshold * 65535;
            otherwise
                error("Unsupported input image class: " + InputClass);
        end
        
        % extract centroids of each connected region
        curr_centroid = regionprops3(curr_out, "Centroid");
        curr_centroid = int16(curr_centroid.Centroid);
        
        
        % locations = [locations; curr_centroid]; %% WARNING
        % 2025-08-27: TODO: ADD channel information to the output
        % chLabel = sprintf("ch%02d", c);

        % 2025-08-13: add intensity value to the output
        for s = 1:size(curr_centroid, 1)
            sx = curr_centroid(s, 1);
            sy = curr_centroid(s, 2);
            sz = curr_centroid(s, 3);
            intensity = curr_channel(sy, sx, sz); 
            locations = [locations; sx, sy ,sz, intensity, (intensityThreshold * 255), c];
            % the setting of fifth column is for compatibility with spotiflow version;
            % locations = [locations; {sx, sy, sz, intensity, (intensityThreshold * 255), chLabel}];
        end

    end


end

