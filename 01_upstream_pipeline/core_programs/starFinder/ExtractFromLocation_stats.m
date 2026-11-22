function [allReads, allSpots, allScores, csMat, allIntensity_table, maxIntensity_perRound, ...
          allReads_raw, allSpots_raw, allScores_raw, basecsMat_raw, allIntensity_raw, maxIntensity_raw, neighborhoodEvidence] = ...
            ExtractFromLocation_stats( input_img, allSpots, voxelSize, q_score_thers, IntensityThresh_perRound, ...
                                       interm_outpath, ref_round, decoding_rounds, showPlots, obj_log )
    % Decode the configured volume; gate every round on its same-z 3-by-3 plane.
    % Neighborhood evidence retains every original candidate row.

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

    % Column order: round, neighborhood, channel (channel changes fastest).
    neighborhoodEvidence = struct();
    neighborhoodEvidence.channel_sum = zeros(Npoint, Nround * 5 * 3, 'single');
    neighborhoodEvidence.channel_l1 = zeros(Npoint, Nround * 5 * 3, 'single');
    neighborhoodEvidence.channel_l2 = zeros(Npoint, Nround * 5 * 3, 'single');
    neighborhoodEvidence.voxel_count = zeros(Npoint, 5, 'uint8');
    neighborhoodEvidence.zero_signal = false(Npoint, Nround * 5);
    neighborhoodEvidence.pr_round_signal = zeros(Npoint, Nround, 'single');
    [delta_y, delta_x, delta_z] = ndgrid(-1:1, -1:1, -1:1);
    neighborhood_masks = false(3, 3, 3, 5);
    neighborhood_masks(:, :, :, 1) = delta_x == 0 & delta_y == 0 & delta_z == 0;
    neighborhood_masks(:, :, :, 2) = delta_z == 0 & abs(delta_x) + abs(delta_y) <= 1;
    neighborhood_masks(:, :, :, 3) = delta_z == 0;
    neighborhood_masks(:, :, :, 4) = abs(delta_x) + abs(delta_y) + abs(delta_z) <= 2;
    neighborhood_masks(:, :, :, 5) = true;
    reuse_decode_volume = isequal(double(voxelSize(:)'), [1 1 1]);

    chunk_size = 4096;
    extraction_timer = tic;
    for chunk_start = 1:chunk_size:Npoint
        chunk_end = min(chunk_start + chunk_size - 1, Npoint);
        chunk_indices = chunk_start:chunk_end;
        chunk_count = numel(chunk_indices);
        raw_colors = zeros(chunk_count, Nround, Nchannel);
        center_max = zeros(chunk_count, Nround);
        neighborhood_sums = zeros(chunk_count, Nround, 5, Nchannel, 'single');
        neighborhood_counts = zeros(chunk_count, 5, 'uint8');

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

            % Fixed-radius diagnostic masks are independent of the decode window.
            neighbor_cols = GetExtents(curr_p(1), 1, image_cols);
            neighbor_rows = GetExtents(curr_p(2), 1, image_rows);
            neighbor_slices = GetExtents(curr_p(3), 1, image_slices);
            if reuse_decode_volume
                neighbor_volume = currVol;
            else
                neighbor_volume = input_img(neighbor_rows, neighbor_cols, neighbor_slices, :, 1:Nround);
            end
            point_masks = neighborhood_masks(neighbor_rows - curr_p(2) + 2, ...
                neighbor_cols - curr_p(1) + 2, neighbor_slices - curr_p(3) + 2, :);
            point_masks = reshape(point_masks, [], 5);
            neighborhood_counts(local_index, :) = uint8(sum(point_masks, 1));
            neighbor_values = reshape(neighbor_volume, [], Nchannel, Nround);
            for neighborhood_index = 1:5
                if neighborhood_index == 5 && reuse_decode_volume
                    sums = color_values;
                else
                    sums = single(sum(neighbor_values(point_masks(:, neighborhood_index), :, :), 1));
                end
                neighborhood_sums(local_index, :, neighborhood_index, :) = ...
                    reshape(reshape(sums, [Nchannel, Nround])', [1, Nround, 1, Nchannel]);
            end
        end

        colorSeq(chunk_indices, :, :) = raw_colors ./ (sqrt(sum(raw_colors.^2, 3)) + 1E-6);
        intensity_chunk = zeros(chunk_count, Nround, 5);
        intensity_chunk(:, :, 1) = center_max;
        intensity_chunk(:, :, 2:4) = raw_colors;
        intensity_chunk(:, :, 5) = max(raw_colors, [], 3);
        allIntensity_table(chunk_indices, :) = reshape(permute(intensity_chunk, [1 3 2]), chunk_count, []);
        maxIntensity_perRound(chunk_indices, :) = max(raw_colors, [], 3);

        % Ratios use double arithmetic after the same single-rounded channel sums.
        ratio_sums = double(neighborhood_sums);
        total_signal = sum(ratio_sums, 4);
        zero_signal = total_signal == 0;
        l1_values = ratio_sums ./ total_signal;
        l1_values(repmat(zero_signal, [1, 1, 1, Nchannel])) = NaN;
        l2_values = ratio_sums ./ (sqrt(sum(ratio_sums.^2, 4)) + 1E-6);
        neighborhoodEvidence.channel_sum(chunk_indices, :) = ...
            reshape(permute(neighborhood_sums, [1 4 3 2]), chunk_count, []);
        neighborhoodEvidence.channel_l1(chunk_indices, :) = ...
            single(reshape(permute(l1_values, [1 4 3 2]), chunk_count, []));
        neighborhoodEvidence.channel_l2(chunk_indices, :) = ...
            single(reshape(permute(l2_values, [1 4 3 2]), chunk_count, []));
        neighborhoodEvidence.voxel_count(chunk_indices, :) = neighborhood_counts;
        neighborhoodEvidence.zero_signal(chunk_indices, :) = ...
            reshape(permute(zero_signal, [1 3 2]), chunk_count, []);
        neighborhoodEvidence.pr_round_signal(chunk_indices, :) = ...
            max(neighborhood_sums(:, :, 3, :), [], 4);
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
    fprintf('DECODING_GATE: statistic=max_channel_neighborhood_sum neighborhood=plane9 nominal_voxels=9 rounds=1:%d threshold=%.15g reference_round=%d center_used=false\n', ...
            Nround, IntensityThresh_perRound, ref_round);
    for round_index = 1:Nround
        round_pass = neighborhoodEvidence.pr_round_signal(:, round_index) >= IntensityThresh_perRound;
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
    intensity_pass_mask = all(neighborhoodEvidence.pr_round_signal(toKeep, :) >= IntensityThresh_perRound, 2);

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
