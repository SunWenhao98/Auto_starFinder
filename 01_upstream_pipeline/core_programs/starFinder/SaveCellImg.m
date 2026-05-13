% function SaveCellImg( dirName, imgs, curr_data_dir, sub_dirs )

% Nchannel = numel(imgs);  % number of channels


% fprintf(sprintf('Saving cell images to %s\n', dirName));

% tic;

% % sub_dirs = ["plaque", "tau", "pi", "merged_dots"];

% for ch=1:Nchannel
%     % create directory for each channel
%     ch_dir = fullfile(dirName, sub_dirs(ch));
%     z = size(imgs{ch}, 3);  % number of z slices
%     if ~exist(ch_dir, 'dir')
%        mkdir(ch_dir);
%     end

%     % save each z slice as a tif file, named by the current position{iii}
%     fname = fullfile(ch_dir, sprintf('%s.tif', curr_data_dir));
%     if exist(fname, 'file') == 2
%         delete(fname);
%     end
    
%     for j=1:z        
%         imwrite(imgs{ch}(:,:,j), fname, 'writemode', 'append');        
%     end
% end
% fprintf(sprintf('Finished!...[time=%02f]\n', toc));
function SaveCellImg( dirName, imgs, curr_data_dir, sub_dirs )

% 获取指定的子文件夹数量，以此为基准
N_dirs = numel(sub_dirs); 

fprintf('Saving cell images to %s\n', dirName);

tic;

for ch = 1:N_dirs
    % 1. 无论图片是否存在，都根据 sub_dirs 创建对应的子文件夹
    % 使用 char() 兼容 string 数组 (例如 ["plaque", "tau"]) 或 cell 数组
    if iscell(sub_dirs)
        ch_name = sub_dirs{ch};
    else
        ch_name = char(sub_dirs(ch));
    end
    
    ch_dir = fullfile(dirName, ch_name);
    
    if ~exist(ch_dir, 'dir')
       mkdir(ch_dir);
    end

    % 2. 检查 imgs 中是否存在对应的通道数据
    if ch <= numel(imgs) && ~isempty(imgs{ch})
        z = size(imgs{ch}, 3);  % number of z slices
        
        % save each z slice as a tif file, named by the current position
        fname = fullfile(ch_dir, sprintf('%s.tif', curr_data_dir));
        if exist(fname, 'file') == 2
            delete(fname);
        end
        
        for j = 1:z        
            imwrite(imgs{ch}(:,:,j), fname, 'writemode', 'append');        
        end
    else
        % 如果没有对应的图像数据，仅提示（不报错）
        fprintf('  -> No image data for channel %d (%s), folder created but no TIF saved.\n', ch, ch_name);
    end
end

fprintf('Finished!...[time=%02f]\n', toc);

end