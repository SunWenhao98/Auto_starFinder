function input_img = new_EqualizeHist3D( input_img, method, hist_channel, hist_round )
% 

    Nround = size(input_img, 5);
    spotsChannels = size(input_img, 4) - 1;
    Nchannels = size(input_img, 4);        % may contains dapi channel
    InputClass = class(input_img);

    switch method
        case "intra_round"
            for t=1:Nround 
                fprintf('Equalizing round %d\n', t);
                currStack = input_img(:,:,:,:,t);
                if t == 11
                    fprintf('Skipping round %d for Equalization of intra-round\n', t);
                    continue;
                end


                for i=1:spotsChannels                
                    % currStack(:,:,:,i) = uint8(imhistmatchn(uint8(currStack(:,:,:,i)), uint8(currStack(:,:,:,1)), 256));
                    % currStack(:,:,:,i) = uint16(imhistmatchn(uint16(currStack(:,:,:,i)), uint16(currStack(:,:,:,1)), 65536));
                    %currStack(:,:,:,i) = gather(histeq(gpuArray(currStack(:,:,:,i))));
                    switch InputClass
                        case "uint8"
                            currStack(:,:,:,i) = uint8(imhistmatchn(uint8(currStack(:,:,:,i)), uint8(currStack(:,:,:,hist_channel)), 256));
                        case "uint16"
                            currStack(:,:,:,i) = uint16(imhistmatchn(uint16(currStack(:,:,:,i)), uint16(currStack(:,:,:,hist_channel)), 65536));
                        otherwise
                            error("Unsupported input class");
                    end
                end    

                input_img(:,:,:,:,t) = currStack;
            end
            
        case "inter_round"
            for t=1:Nchannels
                fprintf('Equalizing channel %d\n', t);
                currStack = input_img(:,:,:,t,:);   

                for i=1:Nround
                    % currStack = input_img{i}(:,:,:,t);   
                    % input_img{i}(:,:,:,t) = uint8(imhistmatchn(uint8(currStack), uint8(input_img{1}(:,:,:,t)), 256));
                    % currStack(:,:,:,:,i) = uint8(imhistmatchn(uint8(currStack(:,:,:,:,i)), uint8(currStack(:,:,:,:,1)), 256));
                    % currStack(:,:,:,:,i) = uint16(imhistmatchn(uint16(currStack(:,:,:,:,i)), uint16(currStack(:,:,:,:,1)), 65536));
                    if i == 11
                        fprintf('Skipping round %d for Equalization of inter-round\n', i);
                        continue;
                    end

                    switch InputClass
                        case "uint8"
                            currStack(:,:,:,:,i) = uint8(imhistmatchn(uint8(currStack(:,:,:,:,i)), uint8(currStack(:,:,:,:,hist_round)), 256));
                        case "uint16"
                            currStack(:,:,:,:,i) = uint16(imhistmatchn(uint16(currStack(:,:,:,:,i)), uint16(currStack(:,:,:,:,hist_round)), 65536));
                        otherwise
                            error("Unsupported input class");
                    end
                end

                input_img(:,:,:,t,:) = currStack;
            end
            
    end

end

