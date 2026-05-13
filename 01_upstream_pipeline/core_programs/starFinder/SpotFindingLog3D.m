function locations = SpotFindingLog3D( input_img, ref_index, fsize, fsigma, intensityThreshold )
    %SpotFindingLog3D - 按照 SpotFindingMax3D 的输出范式改写
    % 输入: 
    %   input_img: 5D 图像矩阵 [H, W, Z, C, R]
    %   ref_index: 用于找点的参考轮次索引
    %   fsize, fsigma: LoG 算子的尺寸和标准差
    %   intensityThreshold: 相对强度阈值 (0-1)

    % 初始化输出坐标矩阵
    locations = [];

    ref_round = input_img(:,:,:,:,ref_index);
    if size(input_img, 4) > 3
        Nchannel = 3;
    else
        Nchannel = size(ref_round, 4);
    end

    InputClass = class(input_img);
    
    % 预定义 LoG 算子
    % 注意：LoG 滤波后斑点中心通常为极小值（负值）
    log3d = fspecial3('log', fsize, fsigma);
    
    for c=1:Nchannel
        curr_channel = ref_round(:,:,:,c);
        
        % 1. LoG 滤波及区域极小值检测
        curr_log = imfilter(single(curr_channel), log3d, 'replicate');
        curr_min = imregionalmin(curr_log); % 3D 连通区域极小值分析

        % 2. 强度阈值处理 (参照 Max3D 的数据类型判断逻辑)
        % 计算用于输出的绝对阈值数值
        switch InputClass
            case "uint8"
                abs_threshold_val = intensityThreshold * 255;
            case "uint16"
                abs_threshold_val = intensityThreshold * 65535;
            otherwise
                % 如果是 single/double，通常按 max_intensity 计算，此处对齐 Max3D 的逻辑
                error("Unsupported input image class: " + InputClass);
        end
        
        % 结合 LoG 极小值和原始通道强度阈值
        curr_out = curr_min & (curr_channel > abs_threshold_val);
        
        % 3. 提取质心
        curr_centroid = regionprops3(curr_out, "Centroid");
        curr_centroid = int16(curr_centroid.Centroid);
        
        % 4. 格式化输出 (对齐 Max3D 的 6 列格式)
        % 列定义: [sx, sy, sz, intensity, (threshold_val), channel_index]
        num_spots = size(curr_centroid, 1);
        for s = 1:num_spots
            sx = curr_centroid(s, 1);
            sy = curr_centroid(s, 2);
            sz = curr_centroid(s, 3);
            
            % 防止坐标越界保护（可选）
            intensity = curr_channel(sy, sx, sz); 
            
            % 按照 Max3D 范式构建行：
            % 1-3: 坐标, 4: 强度, 5: 阈值数值(用于Spotiflow兼容), 6: 通道索引
            locations = [locations; sx, sy, sz, double(intensity), double(abs_threshold_val), c];
        end
    end
end