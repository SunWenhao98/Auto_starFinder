function [allReads, allSpots, allScores, csMat, allIntensity_table, maxIntensity_perRound, ...
          allReads_raw, allSpots_raw, allScores_raw, basecsMat_raw, allIntensity_raw, maxIntensity_raw] = ...
            ExtractFromLocation_stats( input_img, allSpots, voxelSize, q_score_thers, IntensityThresh_perRound, ...
                                       interm_outpath, ref_round, decoding_rounds, showPlots, obj_log )
    % Extract all candidate rows, then apply quality and all-round sum gates.

    validateattributes(voxelSize, {'numeric'}, {'vector', 'numel', 3, 'integer', 'nonnegative', 'finite'});
    validateattributes(q_score_thers, {'numeric'}, {'scalar', 'nonnegative', 'finite'});
    validateattributes(IntensityThresh_perRound, {'numeric'}, {'scalar', 'nonnegative', 'finite'});
    validateattributes(decoding_rounds, {'numeric'}, {'scalar', 'integer', 'positive', 'finite'});

    % get dims
    if size(input_img, 4) > 3
        input_img = input_img(:,:,:,1:3,:); % remove DAPI channel
    end

    [image_rows, image_cols, image_slices, Nchannel, available_rounds] = size(input_img);
    if Nchannel ~= 3 || decoding_rounds > available_rounds
        error('Extraction requires three sequencing channels and every requested decoding round.');
    end
    Nround = decoding_rounds;
    
    Npoint = size(allSpots,1);
    colorSeq = zeros(Npoint, Nround, Nchannel); % "color value" of each dot in each channel of each sequencing round 
    fprintf('Geting color sequence for each voxel...\n');

    % 每一轮 5 列: [currSpot_max, currVol_Ch1, currVol_Ch2, currVol_Ch3, currVol_max]
    allIntensity_table = zeros(Npoint, Nround * 5);
    maxIntensity_perRound = zeros(Npoint, Nround);

    chunk_size = 4096;
    extraction_timer = tic;
    for chunk_start = 1:chunk_size:Npoint
        chunk_end = min(chunk_start + chunk_size - 1, Npoint);
        chunk_indices = chunk_start:chunk_end;
        chunk_count = numel(chunk_indices);
        raw_colors = zeros(chunk_count, Nround, Nchannel);
        center_max = zeros(chunk_count, Nround);

        for local_index = 1:chunk_count
            point_index = chunk_indices(local_index);
            curr_p = double(allSpots(point_index, 1:3));
            cols_range = GetExtents(curr_p(1), voxelSize(1), image_cols);
            rows_range = GetExtents(curr_p(2), voxelSize(2), image_rows);
            slices_range = GetExtents(curr_p(3), voxelSize(3), image_slices);
            currVol = input_img(rows_range, cols_range, slices_range, :, 1:Nround);
            % Preserve the legacy single rounding before double normalization.
            color_values = single(squeeze(sum(currVol, [1 2 3])));
            raw_colors(local_index, :, :) = reshape(double(color_values), [Nchannel, Nround])';
            currSpot = input_img(curr_p(2), curr_p(1), curr_p(3), :, 1:Nround);
            center_max(local_index, :) = reshape(double(max(currSpot, [], 4)), [Nround, 1])';
        end

        colorSeq(chunk_indices, :, :) = raw_colors ./ (sqrt(sum(raw_colors.^2, 3)) + 1E-6);
        intensity_chunk = zeros(chunk_count, Nround, 5);
        intensity_chunk(:, :, 1) = center_max;
        intensity_chunk(:, :, 2:4) = raw_colors;
        intensity_chunk(:, :, 5) = max(raw_colors, [], 3);
        allIntensity_table(chunk_indices, :) = reshape(permute(intensity_chunk, [1 3 2]), chunk_count, []);
        maxIntensity_perRound(chunk_indices, :) = max(raw_colors, [], 3);
    end
    fprintf('PHASE_TIMING: color_extraction_seconds=%.2f\n', toc(extraction_timer));
    
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
    fprintf('DECODING_COUNTS: detected=%d tie_or_invalid_rejected=%d quality_passed=%d\n', ...
            Npoint, sum(~finiteScores), sum(toKeep));
    fprintf('DECODING_GATE: statistic=max_channel_neighborhood_sum rounds=1:%d threshold=%.15g reference_round=%d center_used=false\n', ...
            Nround, IntensityThresh_perRound, ref_round);
    for round_index = 1:Nround
        round_pass = maxIntensity_perRound(:, round_index) >= IntensityThresh_perRound;
        fprintf('DECODING_ROUND_GATE: round=%d raw_passed=%d raw_total=%d quality_passed=%d quality_total=%d\n', ...
                round_index, sum(round_pass), Npoint, sum(round_pass & toKeep), sum(toKeep));
    end
    allReads = allReads(toKeep);
    allScores = allScores(toKeep,:);
    allSpots = allSpots(toKeep,:);
    csMat = csMat(toKeep,:);
    allIntensity_table = allIntensity_table(toKeep,:);
    maxIntensity_perRound = maxIntensity_perRound(toKeep,:);
    

    % Every decoded round must pass; center intensity remains diagnostic only.
    intensity_pass_mask = all(maxIntensity_perRound >= IntensityThresh_perRound, 2);

    % 3. 统计并打印（用于日志核对）
    s = sprintf('%f [%d / %d] percent of reads have intensity at least %f in all %d decoding rounds\n',...
        sum(intensity_pass_mask)/numel(intensity_pass_mask),...
        sum(intensity_pass_mask), ...
        numel(intensity_pass_mask), ...
        IntensityThresh_perRound, ...
        Nround);
    fprintf(s);
    fprintf('DECODING_COUNTS: all_round_intensity_passed=%d quality_total=%d\n', ...
            sum(intensity_pass_mask), numel(intensity_pass_mask));
    if ~isempty(obj_log)
        fprintf(obj_log, '%s', s);
    end
    fid = fopen(fullfile(interm_outpath, 'stats.txt'), 'a');
    fprintf(fid, '%s', s);
    fclose(fid);




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
