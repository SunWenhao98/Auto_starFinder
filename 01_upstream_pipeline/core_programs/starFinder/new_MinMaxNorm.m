function output_img = new_MinMaxNorm( input_img, output_format )
%MinMaxNorm is used to normalize the intensity profile of each channel
%   -----IO-----
%   input_img: mat with input images 
%   output_img: mat with normalized images


    Nround = size(input_img, 5);
    Nchannel = size(input_img, 4);
    InputClass = class(input_img);
    OutputClass = output_format;
    
    fprintf("====Min-Max intensity normalization====\n");
    fprintf("Input class: %s\n", InputClass);
    fprintf("Output class: %s\n", OutputClass);
    
    % ==================== 核心修改 1 ====================
    % 创建一个与输入大小相同，但数据类型为目标类型的新矩阵
    output_img = zeros(size(input_img), OutputClass);
    % ====================================================
    
    for r=1:Nround
        tic
        fprintf(sprintf("Normalizing Round %d...", r))
        
        for c=1:Nchannel 
            curr_channel = input_img(:,:,:,c,r);
            
            curr_channel = double(curr_channel);
            curr_min = min(curr_channel, [] ,'all');
            curr_max = max(curr_channel, [] ,'all');
            
            
            curr_channel = (curr_channel - curr_min) ./ (curr_max - curr_min);  % [0,1]
            % curr_channel = uint8(curr_channel .* 255); %% WARNING
            % curr_channel = uint8(curr_channel .* curr_max);
            % curr_channel = uint16(curr_channel .* 65535);
            switch OutputClass
                case "uint8"
                    curr_channel = uint8(curr_channel .* 255);  % [0,255]
                case "uint16"
                    curr_channel = uint16(curr_channel .* 65535);  % [0,65535]
                otherwise
                    error("Unsupported input class");
            end

            % ==================== 核心修改 2 ====================
            % 将处理好的切片放入新的输出矩阵中
            output_img(:,:,:,c,r) = curr_channel;
            % ====================================================
        end
        fprintf(sprintf('[time = %.2f s]\n', toc));
    end

end

