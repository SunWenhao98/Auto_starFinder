function FinalImage = new_LoadMultipageTiff( fname, formatIn, formatOut, useGPU )

    % Suppress all warnings 
    warning('off','all');
    
    % impossible to happen
    if nargin < 2
        formatIn = 'uint8';
        formatOut = 'uint8';
    end

    InfoImage=imfinfo(fname);
    mImage=InfoImage(1).Width;          % X 
    nImage=InfoImage(1).Height;         % Y
    NumberImages=length(InfoImage);     % Z, frames

 
    if useGPU
        %FinalImage=zeros(nImage,mImage,NumberImages,format, 'gpuArray');
        FinalImage=zeros(nImage ,mImage ,NumberImages, formatIn, 'gpuArray');
    else
        %FinalImage=zeros(nImage,mImage,NumberImages,format);
        FinalImage=zeros(nImage, mImage, NumberImages, formatIn);   % 构建特定位深的三维矩阵
    end

    TifLink = Tiff(fname, 'r');
    for i=1:NumberImages
        TifLink.setDirectory(i);
        FinalImage(:,:,i)=TifLink.read();   % 逐张读入图像
        
        % if i == 29
        %     % 打印最大值
        %     fprintf('Max value: %d\n', max(FinalImage(:,:,i)));
    end
    % fprintf('Max value: %d\n', max(FinalImage(:,:,29), [], 'all'));
    

    % safe design: impossible to happen
    if ~strcmp(formatIn, formatOut)
        % Convert to uint8
        if strcmp(formatOut, 'uint8')
            FinalImage = im2uint8(FinalImage);
        end
    end
    
    TifLink.close();
    
end

