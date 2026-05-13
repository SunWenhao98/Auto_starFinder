function output_img = new_PercenNorm( input_img, output_format, miper, maper )
    %new_PercenNorm is a function to normalize the intensity profile of each channel
    %   -----INPUT-----
    %   input_img: mat with input images (expects 5D: h,w,z,channel,round)
    %   output_format: string, output data type, "uint8" or "uint16"
    %   miper: percentage of minimum intensity value, default is 0
    %   maper: percentage of maximum intensity value, default is 100
    %   -----OUTPUT-----
    %   output_img: mat with normalized images
    %   -----EXAMPLE-----
    %   input_img = imread('input.tif'); % Assuming input_img is 5D
    %   output_img = new_PercenNorm(input_img, 'uint16', 0.01, 99.99);
    %   ---------------------
    
        % --- 处理可选参数 ---
        if nargin < 4
            maper = 100; % 使用与文档一致的默认值
        end
        if nargin < 3
            miper = 0;  % 使用与文档一致的默认值
        end
    
        % --- 初始化 ---
        Nround = size(input_img, 5);
        Nchannel = size(input_img, 4);
        InputClass = class(input_img);
        OutputClass = output_format;
        
        fprintf("==== Min-Max Intensity Percentile Normalization ====\n");
        fprintf("Input class: %s\n", InputClass);
        fprintf("Output class: %s\n", OutputClass);
        fprintf("Percentile Range: [%.6f, %.6f]\n", miper, maper);
        
        % 预分配输出矩阵以提高效率
        output_img = zeros(size(input_img), OutputClass);
        
        % --- 循环处理 ---
        for r=1:Nround
            tic
            fprintf('Normalizing Round %d...', r)
            
            for c=1:Nchannel 
                % 直接转换为double进行计算，不改变原始数值范围
                curr_channel = double(input_img(:,:,:,c,r));
                
                % 使用 prctile 函数
                curr_min = prctile(curr_channel(:), miper);
                curr_max = prctile(curr_channel(:), maper);
                
                if curr_max - curr_min > 0
                    % 进行百分位归一化
                    curr_channel = (curr_channel - curr_min) / (curr_max - curr_min);
                else
                    curr_channel = zeros(size(curr_channel), 'double');
                end
    
                % 将数值裁剪到 [0, 1] 范围
                curr_channel(curr_channel < 0) = 0;
                curr_channel(curr_channel > 1) = 1;
    
                % 根据目标类型，将 [0, 1] 的浮点数映射到整数范围
                switch OutputClass
                    case "uint8"
                        curr_channel = uint8(curr_channel .* 255);
                    case "uint16"
                        curr_channel = uint16(curr_channel .* 65535);
                    otherwise
                        error("Unsupported output class: %s. Use 'uint8' or 'uint16'.", OutputClass);
                end
    
                % 将处理好的通道放回预分配的矩阵中
                output_img(:,:,:,c,r) = curr_channel;
            end
            fprintf('[time = %.2f s]\n', toc);
        end
    
    end