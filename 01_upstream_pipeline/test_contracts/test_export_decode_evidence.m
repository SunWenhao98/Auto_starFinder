function test_export_decode_evidence(output_root)
% 用小数组核对逐行证据、过滤语义、边界体素数和新目录防覆盖。
    if nargin < 1
        error('Pass a new test output directory to test_export_decode_evidence.');
    end
    fprintf('EXPORT_DECODE_EVIDENCE_SOURCE=%s\n', which('export_decode_evidence'));
    [obj, metadata] = fixture();
    output_dir = fullfile(output_root, 'complete_candidates');
    export_decode_evidence(obj, output_dir, metadata);
    cached = load(fullfile(output_dir, 'evidence.mat'));
    assert(isequal(sort(fieldnames(cached)), sort({'candidate_id'; 'spots'; 'intensity'; ...
        'scores'; 'color_index'; 'quality_pass'; 'intensity_pass'; ...
        'codebook_index'; 'neighbor_voxel_count'; 'neighborhood_channel_sum'; ...
        'neighborhood_channel_l1'; 'neighborhood_channel_l2'; 'neighborhood_voxel_count'; ...
        'neighborhood_zero_signal'; 'pr_round_signal'})));
    assert(isa(cached.candidate_id, 'uint64'));
    assert(isequal(cached.candidate_id, uint64((1:8)')));
    assert(numel(unique(cached.candidate_id)) == 8);
    assert(isequal(cached.spots, obj.allSpots_raw));
    assert(isequal(cached.spots(1, :), cached.spots(2, :)));
    assert(isequal(cached.intensity, obj.allIntensity_raw));
    assert(isequaln(cached.scores, obj.allScores_raw));
    assert(isa(cached.color_index, 'int8'));
    assert(isequal(cached.color_index, int8(obj.basecsMat_raw)));
    assert(islogical(cached.quality_pass) && islogical(cached.intensity_pass));
    assert(isequal(cached.quality_pass, logical([1; 1; 0; 1; 0; 1; 1; 0])));
    assert(isequal(cached.intensity_pass, logical([1; 1; 0; 1; 1; 0; 1; 1])));
    assert(isa(cached.codebook_index, 'uint32'));
    assert(isequal(cached.codebook_index, uint32([1; 1; 0; 0; 1; 1; 2; 1])));
    assert(isa(cached.neighbor_voxel_count, 'uint32'));
    assert(isequal(cached.neighbor_voxel_count, uint32([24; 24; 105; 105; 105; 105; 32; 105])));
    assert(isa(cached.neighborhood_channel_sum, 'single'));
    assert(isa(cached.neighborhood_channel_l1, 'single'));
    assert(isa(cached.neighborhood_channel_l2, 'single'));
    assert(isa(cached.neighborhood_voxel_count, 'uint8'));
    assert(islogical(cached.neighborhood_zero_signal));
    assert(isequal(cached.neighborhood_channel_sum, obj.neighborhoodEvidence.channel_sum));
    assert(isequaln(cached.neighborhood_channel_l1, obj.neighborhoodEvidence.channel_l1));
    assert(isequal(cached.neighborhood_channel_l2, obj.neighborhoodEvidence.channel_l2));
    assert(isequal(size(cached.neighborhood_channel_sum), [8, 165]));
    assert(isequal(size(cached.neighborhood_zero_signal), [8, 55]));
    assert(isequal(cached.neighborhood_voxel_count, uint8([1, 3, 4, 7, 8; ...
        1, 3, 4, 7, 8; repmat([1, 5, 9, 19, 27], 4, 1); 1, 4, 6, 10, 12; 1, 5, 9, 19, 27])));
    assert(all(isnan(cached.neighborhood_channel_l1(3, :))));
    assert(all(cached.neighborhood_channel_l2(3, :) == 0));
    assert(all(cached.neighborhood_zero_signal(3, :)));
    % 上下层使旧 27 体素总和足够强，当前层第 11 轮不足仍必须被排除。
    assert(all(obj.maxIntensity_raw(6, :) >= obj.extractionParameters.intensityThresh_PR));
    assert(~cached.intensity_pass(6));
    assert(cached.pr_round_signal(6, 11) == single(71.5));
    assert(cached.pr_round_signal(7, 1) == single(72) && cached.intensity_pass(7));
    channel_sums = reshape(cached.neighborhood_channel_sum', 3, 5, 11, 8);
    assert(isequal(channel_sums(:, 3, 11, 6), single([71.5; 20; 2])));

    metadata_text = fileread(fullfile(output_dir, 'metadata.json'));
    recorded = jsondecode(metadata_text);
    assert(recorded.schema_version == 2 && recorded.decoding_rounds == 11);
    assert(recorded.quality_threshold == 0.5 && recorded.intensityThresh_PR == 72);
    assert(isequal(recorded.voxel_size(:)', [3, 2, 1]));
    assert(isequal(recorded.image_size(:)', [7, 9, 4, 3, 11]));
    assert(strcmp(recorded.sample, metadata.sample));
    assert(strcmp(recorded.position, metadata.position));
    assert(strcmp(recorded.source_mat, metadata.source_mat));
    assert(strcmp(recorded.source_allspots, metadata.source_allspots));
    assert(isequal(recorded.codebook_genes(:), {'GeneA_rbRNA'; 'GeneB_ntRNA'}));
    assert(isequal(recorded.codebook_sequences(:), obj.barcodeSeqs(:)));
    assert(strcmp(recorded.gating_neighborhood, 'plane9'));
    assert(recorded.nominal_gate_voxels == 9 && recorded.gating_threshold_scale == 0.8);
    assert(isequal(recorded.neighborhood_order(:), {'center1'; 'cross5'; 'plane9'; 'volume19'; 'volume27'}));
    assert(isequal(recorded.neighborhood_nominal_voxels(:)', [1, 5, 9, 19, 27]));
    assert(strcmp(recorded.neighborhood_column_order, 'round,neighborhood,channel'));
    assert(strcmp(recorded.neighborhood_zero_signal_column_order, 'round,neighborhood'));
    assert(isequal(recorded.decoding_neighborhood.voxel_size(:)', [3, 2, 1]));
    assert(strcmp(recorded.decoding_neighborhood.type, 'box'));
    assert(strcmp(recorded.diagnostic_precision, 'single'));
    assert(strcmp(recorded.decoding_precision, 'double'));
    assert(contains(recorded.ratio_definitions.l1, 'S_1 + S_2 + S_3'));
    assert(contains(recorded.ratio_definitions.l2, '1e-6'));
    assert(contains(recorded.neighborhood_definitions{4}, 'eight corners'));

    % 同名目录必须拒绝，原缓存与元数据仍可读且内容不变。
    expect_failure(@() export_decode_evidence(obj, output_dir, metadata));
    assert(isequaln(load(fullfile(output_dir, 'evidence.mat')), cached));
    assert(strcmp(fileread(fullfile(output_dir, 'metadata.json')), metadata_text));

    % 两类下游行对齐错误都须在创建目录前失败。
    wrong_spots = obj;
    wrong_spots.goodSpots(1, 1) = 2;
    wrong_reads = obj;
    wrong_reads.goodReads{1} = obj.barcodeSeqs{2};
    for mismatch = {wrong_spots, wrong_reads}
        mismatch_dir = fullfile(output_root, 'misaligned_rows');
        expect_failure(@() export_decode_evidence(mismatch{1}, mismatch_dir, metadata));
        assert(~isfolder(mismatch_dir));
    end
    wrong_mode = metadata;
    wrong_mode.barcode_mode = 'regular';
    mode_dir = fullfile(output_root, 'unsupported_mode');
    expect_failure(@() export_decode_evidence(obj, mode_dir, wrong_mode));
    assert(~isfolder(mode_dir));

    % 阻止证据错列、NaN 逃逸、零信号标记错误及 9 像素筛选值来源错误。
    wrong_shape = obj;
    wrong_shape.neighborhoodEvidence.channel_sum(:, end) = [];
    wrong_nan = obj;
    wrong_nan.neighborhoodEvidence.channel_l1(1, 1) = NaN;
    wrong_zero = obj;
    wrong_zero.neighborhoodEvidence.zero_signal(1, 1) = true;
    wrong_gate = obj;
    wrong_gate.neighborhoodEvidence.pr_round_signal(6, 11) = single(300);
    for malformed = {wrong_shape, wrong_nan, wrong_zero, wrong_gate}
        malformed_dir = fullfile(output_root, 'malformed_evidence');
        expect_failure(@() export_decode_evidence(malformed{1}, malformed_dir, metadata));
        assert(~isfolder(malformed_dir));
    end

    % 单条码本必须保留 JSON 列表，供 Python 按索引消费。
    single_codebook = obj;
    single_codebook.barcodeSeqs = obj.barcodeSeqs(1);
    single_codebook.seqToGene = containers.Map(obj.barcodeSeqs(1), {'GeneA_rbRNA'});
    single_codebook.goodSpots = obj.allSpots_raw(1:2, :);
    single_codebook.goodReads = obj.allReads_raw(1:2);
    single_dir = fullfile(output_root, 'single_codebook');
    export_decode_evidence(single_codebook, single_dir, metadata);
    singleton_json = fileread(fullfile(single_dir, 'metadata.json'));
    assert(~isempty(regexp(singleton_json, '"codebook_genes"\s*:\s*\[', 'once')));
    assert(~isempty(regexp(singleton_json, '"codebook_sequences"\s*:\s*\[', 'once')));

    % 全零信号对应的无效调用保留原始行；零候选也保存既定二维形状。
    empty = obj;
    empty.allSpots_raw = zeros(0, 6);
    empty.allIntensity_raw = zeros(0, 55);
    empty.allScores_raw = zeros(0, 11);
    empty.basecsMat_raw = zeros(0, 11);
    empty.maxIntensity_raw = zeros(0, 11);
    empty.allReads_raw = cell(0, 1);
    empty.goodSpots = zeros(0, 6);
    empty.goodReads = cell(0, 1);
    empty.neighborhoodEvidence = struct('channel_sum', zeros(0, 165, 'single'), ...
        'channel_l1', zeros(0, 165, 'single'), 'channel_l2', zeros(0, 165, 'single'), ...
        'voxel_count', zeros(0, 5, 'uint8'), 'zero_signal', false(0, 55), ...
        'pr_round_signal', zeros(0, 11, 'single'));
    empty_dir = fullfile(output_root, 'zero_candidates');
    export_decode_evidence(empty, empty_dir, metadata);
    empty_cached = load(fullfile(empty_dir, 'evidence.mat'));
    assert(isequal(size(empty_cached.candidate_id), [0, 1]));
    assert(isequal(size(empty_cached.spots), [0, 6]));
    assert(isequal(size(empty_cached.intensity), [0, 55]));
    assert(isequal(size(empty_cached.scores), [0, 11]));
    assert(isequal(size(empty_cached.codebook_index), [0, 1]));
    assert(isequal(size(empty_cached.neighborhood_channel_sum), [0, 165]));
    assert(isequal(size(empty_cached.neighborhood_channel_l1), [0, 165]));
    assert(isequal(size(empty_cached.neighborhood_channel_l2), [0, 165]));
    assert(isequal(size(empty_cached.neighborhood_voxel_count), [0, 5]));
    assert(isequal(size(empty_cached.neighborhood_zero_signal), [0, 55]));
    assert(isequal(size(empty_cached.pr_round_signal), [0, 11]));
    fprintf('EXPORT_EVIDENCE_TEST_DIR=%s\n', output_root);
    fprintf('STATUS: SUCCESS | test_export_decode_evidence\n');
end

function [obj, metadata] = fixture()
    seq_a = repmat('1', 1, 11);
    seq_b = repmat('2', 1, 11);
    obj = struct();
    obj.registeredImages = zeros(7, 9, 4, 3, 11, 'uint8');
    obj.extractionParameters = struct('quality_threshold', 0.5, 'voxel_size', [3, 2, 1], ...
        'decoding_rounds', 11, 'intensityThresh_PR', 72, 'ref_round', 1);
    obj.allSpots_raw = [1, 1, 1, 400, 51, 1; 1, 1, 1, 400, 51, 1; ...
        5, 4, 2, 0, 51, 1; 5, 4, 2, 400, 51, 3; ...
        5, 4, 2, 400, 51, 1; 5, 4, 2, 400, 51, 1; ...
        9, 2, 4, 400, 51, 2; 5, 4, 2, 400, 51, 1];
    obj.allScores_raw = 0.1 * ones(8, 11);
    obj.allScores_raw(3, :) = Inf;
    obj.allScores_raw(5, :) = 0.6;
    obj.allScores_raw(8, :) = 0.5;
    obj.maxIntensity_raw = 300 * ones(8, 11);
    obj.maxIntensity_raw(3, :) = 0;
    obj.allIntensity_raw = reshape(1:(8 * 55), 8, 55);
    obj.allIntensity_raw(:, 5:5:end) = obj.maxIntensity_raw;
    obj.allIntensity_raw(3, :) = 0;
    obj.basecsMat_raw = ones(8, 11);
    obj.basecsMat_raw(3, :) = -1;
    obj.basecsMat_raw(4, :) = 3;
    obj.basecsMat_raw(7, :) = 2;
    obj.allReads_raw = {seq_a; seq_a; []; repmat('3', 1, 11); seq_a; seq_a; seq_b; seq_a};
    obj.barcodeSeqs = {seq_a, seq_b};
    obj.seqToGene = containers.Map(obj.barcodeSeqs, {'GeneA_rbRNA', 'GeneB_ntRNA'});
    obj.goodSpots = obj.allSpots_raw([1, 2, 7], :);
    obj.goodReads = obj.allReads_raw([1, 2, 7]);
    sums = zeros(8, 11, 5, 3, 'single');
    sums(:, :, 1, :) = repmat(reshape(single([10, 2, 0]), 1, 1, 1, 3), 8, 11);
    sums(:, :, 2, :) = repmat(reshape(single([50, 10, 1]), 1, 1, 1, 3), 8, 11);
    sums(:, :, 3, :) = repmat(reshape(single([100, 20, 2]), 1, 1, 1, 3), 8, 11);
    sums(:, :, 4, :) = repmat(reshape(single([200, 25, 3]), 1, 1, 1, 3), 8, 11);
    sums(:, :, 5, :) = repmat(reshape(single([300, 30, 5]), 1, 1, 1, 3), 8, 11);
    sums(2, :, 1, :) = 0;
    sums(3, :, :, :) = 0;
    sums(6, 11, 3, 1) = single(71.5);
    sums(7, 1, 3, 1) = single(72);
    l1 = single(double(sums) ./ sum(double(sums), 4));
    l2 = single(double(sums) ./ (sqrt(sum(double(sums).^2, 4)) + 1e-6));
    obj.neighborhoodEvidence = struct( ...
        'channel_sum', reshape(permute(sums, [1, 4, 3, 2]), 8, []), ...
        'channel_l1', reshape(permute(l1, [1, 4, 3, 2]), 8, []), ...
        'channel_l2', reshape(permute(l2, [1, 4, 3, 2]), 8, []), ...
        'voxel_count', uint8([1, 3, 4, 7, 8; 1, 3, 4, 7, 8; ...
            repmat([1, 5, 9, 19, 27], 4, 1); 1, 4, 6, 10, 12; 1, 5, 9, 19, 27]), ...
        'zero_signal', reshape(permute(all(sums == 0, 4), [1, 3, 2]), 8, []), ...
        'pr_round_signal', reshape(max(sums(:, :, 3, :), [], 4), 8, 11));
    metadata = struct('sample', 'synthetic_sample', 'position', 'Position001', ...
        'source_mat', '/synthetic/localRegistered_image.mat', ...
        'source_allspots', '/synthetic/allSpots_max3d_0.2.csv', 'barcode_mode', 'tri');
end

function expect_failure(action)
    failed = false;
    try
        action();
    catch
        failed = true;
    end
    assert(failed, 'Expected export to fail.');
end
