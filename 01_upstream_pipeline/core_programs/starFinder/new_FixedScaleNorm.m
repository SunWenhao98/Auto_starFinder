function output_img = new_FixedScaleNorm( input_img, output_format, minfix, maxfix )
    %new_FixedScaleNorm is a function to normalize the intensity profile of each channel
    %   -----INPUT-----
    %   input_img: mat with input images (expects 5D: h,w,z,channel,round)
    %   output_format: string, output data type, "uint8" or "uint16"
    %   minfix: fixed minimum intensity value, default is 0
    %   maxfix: fixed maximum intensity value, default is 65535 for uint16, 255 for uint8
    %   -----OUTPUT-----
    %   output_img: mat with normalized images
    %   -----EXAMPLE-----
    %   % Assuming input_img is 5D
    %   output_img = new_FixedScaleNorm(input_img, 'uint16', 100, 4095);
    %   ---------------------
        
        % --- (已修正) 处理可选参数 ---
        if nargin < 2
            error('至少需要提供 input_img 和 output_format 两个参数。');
        end
        if nargin < 3
            minfix = 0;  % minfix 的默认值是 0
        end
        if nargin < 4
            % maxfix 的默认值取决于输出格式
            switch output_format
                case "uint8"
                    maxfix = 255;
                case "uint16"
                    maxfix = 65535;
                otherwise
                    error("不支持的 output_format: %s. 请使用 'uint8' 或 'uint16'.", output_format);
            end
        end
    
        
        % --- 初始化 ---
        Nround = size(input_img, 5);
        Nchannel = size(input_img, 4);
        InputClass = class(input_img);
        OutputClass = output_format;
        
        % --- (已修正) 更新打印信息 ---
        fprintf("==== Fixed-Scale Intensity Normalization ====\n");
        fprintf("Input class:  %s\n", InputClass);
        fprintf("Output class: %s\n", OutputClass);
        fprintf("Fixed Range:  [%d, %d]\n", minfix, maxfix);
        
        % 预分配输出矩阵以提高效率
        output_img = zeros(size(input_img), OutputClass);
        
        % --- 循环处理 ---
        for r=1:Nround
            tic
            fprintf('Normalizing Round %d...', r)
            
            for c=1:Nchannel 
                % 直接转换为double进行计算，不改变原始数值范围
                curr_channel = double(input_img(:,:,:,c,r));
                
                % 使用固定的 minfix 和 maxfix
                curr_min = minfix;
                curr_max = maxfix;
                
                if curr_max - curr_min > 0
                    % 进行固定范围归一化
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
                        % 理论上在参数检查部分已经拦截，这里作为双重保险
                        error("Unsupported output class: %s.", OutputClass);
                end
    
                % 将处理好的通道放回预分配的矩阵中
                output_img(:,:,:,c,r) = curr_channel;
            end
            fprintf('[time = %.2f s]\n', toc);
        end
    
    end