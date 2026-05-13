function output_img = new_PercenNorm( input_img, output_format, miper, maper )
    %new_PercenNorm is a function to normalize the intensity profile of each channel
    %   -----INPUT-----
    %   input_img: mat with input images 
    %   output_format: string, output data type, "uint8" or "uint16"
    %   miper: percentage of minimum intensity value, default is 0.01
    %   maper: percentage of maximum intensity value, default is 0.99
    %   -----OUTPUT-----
    %   output_img: mat with normalized images
    %   -----EXAMPLE-----
    %   input_img = imread('input.tif');
    %   output_img = new_PercenNorm(input_img, 'uint8', 0.01, 0.99);
    %   ---------------------
    
    
    
    
    
        % --- 处理可选参数 ---
        % 如果未提供 maper 参数，则默认为 100
        if nargin < 3
            maper = 100;
        end
        % 如果未提供 miper 参数，则默认为 0
        if nargin < 2
            miper = 0;
        end
    
    
    
    
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
                
                curr_channel = im2double(curr_channel);
                % curr_min = min(curr_channel, [] ,'all');
                % curr_max = max(curr_channel, [] ,'all');
    
                curr_min = prctile(curr_channel, [], miper);
                curr_max = prctile(curr_channel, [], maper);
                
                
                if curr_max - curr_min > 0
                    curr_channel = (curr_channel - curr_min) ./ (curr_max - curr_min);  % percenile normalization
                else
                    curr_channel = zeros(size(curr_channel), 'double');
                end
    
                % cut image into [0, 1]
                curr_channel(curr_channel < 0) = 0;
                curr_channel(curr_channel > 1) = 1;
    
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
    
    