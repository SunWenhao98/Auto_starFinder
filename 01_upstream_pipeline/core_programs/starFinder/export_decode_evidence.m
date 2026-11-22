function export_decode_evidence(obj, output_dir, metadata)
% 保存 tri 研究所需的逐候选证据，不改变现有解码和过滤结果。
    if ~strcmp(metadata.barcode_mode, 'tri')
        error('Decode evidence export currently supports tri research only.');
    end
    if isfolder(output_dir) || isfile(output_dir)
        error('Decode evidence output already exists: %s', output_dir);
    end

    parameters = obj.extractionParameters;
    decoding_rounds = parameters.decoding_rounds;
    spots = obj.allSpots_raw;
    intensity = obj.allIntensity_raw;
    scores = obj.allScores_raw;
    raw_reads = obj.allReads_raw;
    candidate_count = size(spots, 1);
    neighborhood_order = {'center1', 'cross5', 'plane9', 'volume19', 'volume27'};
    neighborhood_count = numel(neighborhood_order);
    evidence = obj.neighborhoodEvidence;
    neighborhood_channel_sum = evidence.channel_sum;
    neighborhood_channel_l1 = evidence.channel_l1;
    neighborhood_channel_l2 = evidence.channel_l2;
    neighborhood_voxel_count = evidence.voxel_count;
    neighborhood_zero_signal = evidence.zero_signal;
    pr_round_signal = evidence.pr_round_signal;
    if decoding_rounds ~= 11 || size(spots, 2) ~= 6 || ...
            ~isequal(size(intensity), [candidate_count, 5 * decoding_rounds]) || ...
            ~isequal(size(scores), [candidate_count, decoding_rounds]) || ...
            ~isequal(size(obj.basecsMat_raw), [candidate_count, decoding_rounds]) || ...
            ~isequal(size(obj.maxIntensity_raw), [candidate_count, decoding_rounds]) || ...
            ~iscell(raw_reads) || ~isequal(size(raw_reads), [candidate_count, 1])
        error('Tri evidence requires aligned N-by-6 spots and all 11 decoding rounds.');
    end
    neighborhood_shape = [candidate_count, decoding_rounds * neighborhood_count * 3];
    if ~isequal(size(neighborhood_channel_sum), neighborhood_shape) || ...
            ~isequal(size(neighborhood_channel_l1), neighborhood_shape) || ...
            ~isequal(size(neighborhood_channel_l2), neighborhood_shape) || ...
            ~isequal(size(neighborhood_voxel_count), [candidate_count, neighborhood_count]) || ...
            ~isequal(size(neighborhood_zero_signal), [candidate_count, decoding_rounds * neighborhood_count]) || ...
            ~isequal(size(pr_round_signal), [candidate_count, decoding_rounds]) || ...
            ~isa(neighborhood_channel_sum, 'single') || ...
            ~isa(neighborhood_channel_l1, 'single') || ...
            ~isa(neighborhood_channel_l2, 'single') || ...
            ~isa(neighborhood_voxel_count, 'uint8') || ...
            ~islogical(neighborhood_zero_signal) || ~isa(pr_round_signal, 'single')
        error('Neighborhood evidence must preserve all candidate rows, rounds, neighborhoods and channels.');
    end

    % 按块核验零信号与筛选来源，避免为诊断数组再创建完整大小的副本。
    % 每轮连续三个 plane9 通道，列顺序与缓存写入顺序一致。
    plane9_columns = reshape(((0:decoding_rounds - 1) * (neighborhood_count * 3)) + (7:9)', 1, []);
    for first_row = 1:4096:candidate_count
        rows = first_row:min(first_row + 4095, candidate_count);
        sums = neighborhood_channel_sum(rows, :);
        l1 = neighborhood_channel_l1(rows, :);
        l2 = neighborhood_channel_l2(rows, :);
        zero_channels = repelem(neighborhood_zero_signal(rows, :), 1, 3);
        actual_zero = reshape(all(reshape(sums', 3, decoding_rounds * neighborhood_count, []) == 0, 1), ...
                              decoding_rounds * neighborhood_count, [])';
        plane9_sums = reshape(sums(:, plane9_columns)', 3, decoding_rounds, []);
        plane9_signal = reshape(max(plane9_sums, [], 1), decoding_rounds, [])';
        nonzero_l1 = l1(~zero_channels);
        if any(isinf(sums) | isnan(sums), 'all') || any(isinf(l2) | isnan(l2), 'all') || ...
                any(~isnan(l1(zero_channels))) || any(isinf(nonzero_l1) | isnan(nonzero_l1)) || ...
                any(sums(zero_channels) ~= 0) || any(l2(zero_channels) ~= 0) || ...
                ~isequal(neighborhood_zero_signal(rows, :), actual_zero) || ...
                ~isequal(pr_round_signal(rows, :), plane9_signal)
            error('Neighborhood zero-signal markers or plane9 gate values are inconsistent.');
        end
    end

    candidate_id = uint64((1:candidate_count)');
    color_index = int8(obj.basecsMat_raw);
    quality_pass = ~any(isinf(scores), 2) & mean(scores, 2) < parameters.quality_threshold;
    intensity_pass = all(pr_round_signal >= parameters.intensityThresh_PR, 2);

    % 无效调用仍占原始行；只对完整字符串批量匹配码本。
    codebook_sequences = reshape(obj.barcodeSeqs, [], 1);
    valid_reads = cellfun(@(read) ischar(read) && isrow(read) && ...
                         numel(read) == decoding_rounds, raw_reads);
    codebook_index = zeros(candidate_count, 1, 'uint32');
    [~, matched_indices] = ismember(raw_reads(valid_reads), codebook_sequences);
    codebook_index(valid_reads) = uint32(matched_indices);
    good_mask = quality_pass & intensity_pass & codebook_index > 0;
    if ~isequaln(spots(good_mask, :), obj.goodSpots) || ...
            ~isequal(raw_reads(good_mask), obj.goodReads)
        error('Evidence gates do not reproduce the existing tri goodSpots/goodReads rows.');
    end

    % x 对应图像列、y 对应图像行；边界候选按实际截断后的邻域计数。
    image_size = arrayfun(@(dimension) size(obj.registeredImages, dimension), 1:5);
    coordinates = double(spots(:, 1:3));
    spatial_limits = image_size([2, 1, 3]);
    validateattributes(coordinates, {'numeric'}, {'integer', 'positive', 'finite'});
    if any(coordinates > spatial_limits, 'all')
        error('Candidate coordinates exceed the registered image dimensions.');
    end
    voxel_size = reshape(parameters.voxel_size, 1, 3);
    lower_bound = max(coordinates - voxel_size, 1);
    upper_bound = min(coordinates + voxel_size, spatial_limits);
    neighbor_voxel_count = uint32(prod(upper_bound - lower_bound + 1, 2));

    metadata.schema_version = 2;
    metadata.decoding_rounds = decoding_rounds;
    metadata.voxel_size = voxel_size;
    metadata.quality_threshold = parameters.quality_threshold;
    metadata.intensityThresh_PR = parameters.intensityThresh_PR;
    metadata.ref_round = parameters.ref_round;
    metadata.extraction_parameters = parameters;
    metadata.image_size = image_size;
    metadata.candidate_count = candidate_count;
    metadata.gating_neighborhood = 'plane9';
    metadata.nominal_gate_voxels = 9;
    metadata.gating_threshold_scale = 0.8;
    metadata.neighborhood_order = neighborhood_order;
    metadata.neighborhood_nominal_voxels = [1, 5, 9, 19, 27];
    metadata.neighborhood_column_order = 'round,neighborhood,channel';
    metadata.neighborhood_zero_signal_column_order = 'round,neighborhood';
    metadata.neighborhood_definitions = { ...
        'center voxel'; ...
        'center plus four face neighbors in the same z plane'; ...
        '3-by-3 square in the same z plane'; ...
        '3-by-3-by-3 cube excluding its eight corners'; ...
        'complete 3-by-3-by-3 cube'};
    metadata.decoding_neighborhood = struct('type', 'box', 'voxel_size', voxel_size);
    metadata.ratio_definitions = struct( ...
        'l1', 'S_c / (S_1 + S_2 + S_3)', ...
        'l2', 'S_c / (sqrt(S_1^2 + S_2^2 + S_3^2) + 1e-6)', ...
        'zero_signal', 'All three channel sums are zero: L1 is NaN, L2 is zero.');
    metadata.diagnostic_precision = 'single';
    metadata.decoding_precision = 'double';
    metadata.boundary_policy = 'Clip neighborhoods to the image; keep the nominal plane9 gate threshold.';
    metadata.codebook_sequences = codebook_sequences;
    metadata.codebook_genes = reshape(values(obj.seqToGene, codebook_sequences), [], 1);
    metadata_json = jsonencode(metadata);

    [created, message, message_id] = mkdir(output_dir);
    if ~created || strcmp(message_id, 'MATLAB:MKDIR:DirectoryExists')
        error('Cannot create new evidence output: %s', message);
    end
    fprintf('DECODE_EVIDENCE: candidates=%d good=%d output=%s\n', ...
            candidate_count, sum(good_mask), output_dir);
    save(fullfile(output_dir, 'evidence.mat'), 'candidate_id', 'spots', 'intensity', ...
         'scores', 'color_index', 'quality_pass', 'intensity_pass', ...
         'codebook_index', 'neighbor_voxel_count', ...
         'neighborhood_channel_sum', 'neighborhood_channel_l1', 'neighborhood_channel_l2', ...
         'neighborhood_voxel_count', 'neighborhood_zero_signal', 'pr_round_signal', '-v7.3');
    metadata_file = fopen(fullfile(output_dir, 'metadata.json'), 'w');
    close_metadata = onCleanup(@() fclose(metadata_file));
    fprintf(metadata_file, '%s\n', metadata_json);
    clear close_metadata;
    fprintf('DECODE_EVIDENCE: saved candidates=%d\n', candidate_count);
end
