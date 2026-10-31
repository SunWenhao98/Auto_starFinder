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
    if decoding_rounds ~= 11 || size(spots, 2) ~= 6 || ...
            ~isequal(size(intensity), [candidate_count, 5 * decoding_rounds]) || ...
            ~isequal(size(scores), [candidate_count, decoding_rounds]) || ...
            ~isequal(size(obj.basecsMat_raw), [candidate_count, decoding_rounds]) || ...
            ~isequal(size(obj.maxIntensity_raw), [candidate_count, decoding_rounds]) || ...
            ~iscell(raw_reads) || ~isequal(size(raw_reads), [candidate_count, 1])
        error('Tri evidence requires aligned N-by-6 spots and all 11 decoding rounds.');
    end

    candidate_id = uint64((1:candidate_count)');
    color_index = int8(obj.basecsMat_raw);
    quality_pass = ~any(isinf(scores), 2) & mean(scores, 2) < parameters.quality_threshold;
    intensity_pass = all(obj.maxIntensity_raw >= parameters.intensityThresh_PR, 2);

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

    metadata.schema_version = 1;
    metadata.decoding_rounds = decoding_rounds;
    metadata.voxel_size = voxel_size;
    metadata.quality_threshold = parameters.quality_threshold;
    metadata.intensityThresh_PR = parameters.intensityThresh_PR;
    metadata.ref_round = parameters.ref_round;
    metadata.extraction_parameters = parameters;
    metadata.image_size = image_size;
    metadata.candidate_count = candidate_count;
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
         'codebook_index', 'neighbor_voxel_count', '-v7.3');
    metadata_file = fopen(fullfile(output_dir, 'metadata.json'), 'w');
    close_metadata = onCleanup(@() fclose(metadata_file));
    fprintf(metadata_file, '%s\n', metadata_json);
    clear close_metadata;
    fprintf('DECODE_EVIDENCE: saved candidates=%d\n', candidate_count);
end
