function [allReads, allSpots, allScores, csMat, allIntensity_table, maxIntensity_perRound, ...
          allReads_raw, allSpots_raw, allScores_raw, basecsMat_raw, allIntensity_raw, maxIntensity_raw] = ...
            ExtractFromLocation_stats( input_img, allSpots, voxelSize, q_score_thers, IntensityThresh_perRound, ...
                                       interm_outpath, ref_round, decoding_rounds, showPlots, obj_log )
    % ExtractFromLocation are optimized for statistics of decoding results

    % get dims
    if size(input_img, 4) > 3
        input_img = input_img(:,:,:,1:3,:); % remove DAPI channel
    end

    % input_img = input_img(:,:,:,:,2:6); % only keep round 2-6 for duo chemistry
    [x, y, z, Nchannel, Nround] = size(input_img);
    Nround = min(Nround, decoding_rounds); % limit to specified number of rounds
    
    Npoint = size(allSpots,1);
    colorSeq = zeros(Npoint, Nround, Nchannel); % "color value" of each dot in each channel of each sequencing round 
    outputData = []; % Initialize outputData
    fprintf('Geting color sequence for each voxel...\n');

    % 每一轮 5 列: [currSpot_max, currVol_Ch1, currVol_Ch2, currVol_Ch3, currVol_max]
    allIntensity_table = zeros(Npoint, Nround * 5);
    maxIntensity_perRound = zeros(Npoint, Nround);

    for i=1:Npoint
        
        % Get voxel for each dot
        curr_p = double(allSpots(i, 1:3));

        % extentsX = GetExtents(curr_p(2), voxelSize(1), x);
        % extentsY = GetExtents(curr_p(1), voxelSize(2), y);
        % extentsZ = GetExtents(curr_p(3), voxelSize(3), z);

        cols_range = GetExtents(curr_p(1), voxelSize(1), x);  % 原 extentsX
        rows_range = GetExtents(curr_p(2), voxelSize(2), y); % 原 extentsY
        slices_range = GetExtents(curr_p(3), voxelSize(3), z); % 原 extentsZ

        % disp(['range calculated: ', num2str(cols_range), ...
        %      ' ', num2str(rows_range), ' ', num2str(slices_range)]);
        
        
        for r=1:Nround
            % currVol = input_img(extentsX, extentsY, extentsZ, :, r); % 4-D array
            currVol = input_img(rows_range, cols_range, slices_range, :, r);

            colorSeq(i,r,:) = single(squeeze(sum(currVol, [1 2 3]))); % sum along row,col,z
            raw_vals = colorSeq(i,r,:);
            colorSeq(i,r,:) = colorSeq(i,r,:) ./ (sqrt(sum(squeeze(colorSeq(i,r,:)).^2)) + 1E-6);  % +1E-6 avoids denominator equaling to 0
            
            currSpot = input_img(curr_p(2), curr_p(1), curr_p(3), :, r); % 注意这里的索引顺序是 (row, col, slice, channel, round)
            start_col = (r - 1) * 5 + 1;
            allIntensity_table(i, start_col) = max(currSpot);               % store max intensity at center voxel
            allIntensity_table(i, start_col + 1:start_col + 3) = raw_vals;  % store raw intensity values in neighboring voxels
            allIntensity_table(i, start_col + 4) = max(raw_vals);           % store max intensity in the entire volume
            maxIntensity_perRound(i, r) = max(raw_vals);
        end
        

    end
    
    %writematrix(outputData, 'output_location.csv'); % 或者使用 'output_data.txt' 保存为 TXT

    fprintf('\n');
    
    [allReads, csMat, allScores] = new_GetBaseSeq(colorSeq);

    % return raw results of allspots 
    % obj.allSpots_raw, obj.allScores_raw, obj.allReads_raw, obj.basecsMat_raw
    
    allSpots_raw = allSpots;        % allSpots : [Npoints x 3]  注意：这里的坐标是以 1 为起点的
    allScores_raw = allScores;      % allScores: [Npoints x Nrounds]
    allReads_raw = allReads;        % allReads: [Npoints x 1]
    basecsMat_raw = csMat;          % basecsMat: [Npoints x Nrounds]
    allIntensity_raw = allIntensity_table; % [Npoints x (Nrounds * 5)]
    maxIntensity_raw = maxIntensity_perRound; % [Npoints x Nrounds]

    % allSpots_raw = [allSpots_raw, allIntensity_raw]; % [Npoints x (3 + Nrounds * 5)]
    




    % label reads/spots with any infinite values in any rounds
    finiteScores = ~any(isinf(allScores), 2);

    % remove reads with bad quality scores
    if showPlots
        figure(1);
        histogram(mean(allScores, 2), 100)
        xlabel('Average scores'); ylabel('Count');
    end
    
    % export_fig is an add-on
    % export_fig(fullfile(obj.outPath, 'average_scores.png'));


    belowScoreThresh = mean(allScores, 2) < q_score_thers; % 0.5; 
    s = sprintf('%f [%d / %d] percent of reads are below score thresh %d\n',...
        sum(belowScoreThresh)/numel(belowScoreThresh),...
        sum(belowScoreThresh), ...
        numel(belowScoreThresh), ...
        q_score_thers);
    fprintf(s);
    
    if ~isempty(obj_log)
        fprintf(obj_log, s);
    end

    validScores = allScores(finiteScores,:);
    belowvalidScores = mean(validScores, 2) < q_score_thers; % 0.5; 
    s = sprintf('%f [%d / %d] percent of reads are below score thresh %d of all valid spots\n',...
        sum(belowvalidScores)/numel(belowvalidScores),...
        sum(belowvalidScores), ...
        numel(belowvalidScores), ...
        q_score_thers);
    fprintf(s);
    
    if ~isempty(obj_log)
        fprintf(obj_log, s);
    end
    
    
    fid = fopen(fullfile(interm_outpath, 'stats.txt'), 'a'); % 使用 'a' 模式
    fprintf(fid, s);
    fclose(fid);

    toKeep = belowScoreThresh & finiteScores; % points to keep;
    allReads = allReads(toKeep);
    allScores = allScores(toKeep,:);
    allSpots = allSpots(toKeep,:);
    csMat = csMat(toKeep,:);
    allIntensity_table = allIntensity_table(toKeep,:);
    maxIntensity_perRound = maxIntensity_perRound(toKeep,:);
    

    % 过滤掉任意一轮低于某个阈值的信号
    % is_bright_enough = maxIntensity_perRound >= IntensityThresh_perRound; % 0.1;
    % intensity_pass_mask = all(is_bright_enough, 2);
    % s = sprintf('%f [%d / %d] percent of reads have intensity above %d\n',...
    %     sum(intensity_pass_mask)/numel(intensity_pass_mask),...
    %     sum(intensity_pass_mask), ...
    %     numel(intensity_pass_mask), ...
    %     IntensityThresh_perRound);
    % fprintf(s);

    % 过滤掉在参考轮次低于某个阈值的信号
    is_bright_enough_ref = maxIntensity_perRound(:, ref_round) >= IntensityThresh_perRound;
    intensity_pass_mask = is_bright_enough_ref;

    % 3. 统计并打印（用于日志核对）
    s = sprintf('%f [%d / %d] percent of reads have intensity above %f in Reference Round (Round %d)\n',...
        sum(intensity_pass_mask)/numel(intensity_pass_mask),...
        sum(intensity_pass_mask), ...
        numel(intensity_pass_mask), ...
        IntensityThresh_perRound, ...
        ref_round);
    fprintf(s);




    allReads = allReads(intensity_pass_mask,:);
    allScores = allScores(intensity_pass_mask,:);
    allSpots = allSpots(intensity_pass_mask,:);
    csMat = csMat(intensity_pass_mask,:);
    allIntensity_table = allIntensity_table(intensity_pass_mask,:);
    maxIntensity_perRound = maxIntensity_perRound(intensity_pass_mask,:);


    % allSpots 和 allIntensity_table 按行拼接
    % allSpots = [allSpots, allIntensity_table]; % [Npoints x (3+Nrounds*5)]


    
%     if ~isempty(dividerBase)
%         k = {'AT','CT','GT','TT',...
%             'AG', 'CG', 'GG', 'TG',...
%             'AC', 'CC', 'GC', 'TC',...
%             'AA', 'CA', 'GA', 'TA'};
%         v = {4,3,2,1,3,4,1,2,2,1,4,3,1,2,3,4};
%         codeMap = containers.Map(k, v);  
%         
%         dividerColor = codeMap(dividerBase);
%         divideLoc = Nround / 2;
%         allReads = cellfun(@(x) insertAfter(x, divideLoc, int2str(dividerColor)), allReads, 'UniformOutput', false);
%         divideMat = repmat(dividerColor, size(csMat, 1), 1);
%         csMat = [csMat(:, 1:divideLoc) divideMat csMat(:, divideLoc+1:end)];
%     end
    
    
    if showPlots
        figure(2);
        errorbar(mean(allScores), std(allScores),'ko-'); 
        xlim([0 Nround+1]); 
        xlabel('Round'); ylabel('Average qual score');
    end
    
%     export_fig(fullfile(obj.outPath, 'average_qual_score_belowThresh.png'));
%     save(fullfile(obj.outPath, 'points.mat'), 'allReads', 'qualScores', 'allPoints');

end

% extentsX = GetExtents(curr_p(2), voxelSize(1), x);
% extentsY = GetExtents(curr_p(1), voxelSize(2), y);                    
% extentsZ = GetExtents(curr_p(3), voxelSize(3), z);    

function e = GetExtents(pos, voxelSize, lim)

if pos-voxelSize < 1 
    e1 = 1;
else
    e1 = pos-voxelSize;
end

if pos+voxelSize > lim
    e2 = lim;
else
    e2 = pos+voxelSize;
end

e = e1:e2;

end