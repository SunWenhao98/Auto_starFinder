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
        'codebook_index'; 'neighbor_voxel_count'})));
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

    metadata_text = fileread(fullfile(output_dir, 'metadata.json'));
    recorded = jsondecode(metadata_text);
    assert(recorded.schema_version == 1 && recorded.decoding_rounds == 11);
    assert(recorded.quality_threshold == 0.5 && recorded.intensityThresh_PR == 270);
    assert(isequal(recorded.voxel_size(:)', [3, 2, 1]));
    assert(isequal(recorded.image_size(:)', [7, 9, 4, 3, 11]));
    assert(strcmp(recorded.sample, metadata.sample));
    assert(strcmp(recorded.position, metadata.position));
    assert(strcmp(recorded.source_mat, metadata.source_mat));
    assert(strcmp(recorded.source_allspots, metadata.source_allspots));
    assert(isequal(recorded.codebook_genes(:), {'GeneA_rbRNA'; 'GeneB_ntRNA'}));
    assert(isequal(recorded.codebook_sequences(:), obj.barcodeSeqs(:)));

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
    empty_dir = fullfile(output_root, 'zero_candidates');
    export_decode_evidence(empty, empty_dir, metadata);
    empty_cached = load(fullfile(empty_dir, 'evidence.mat'));
    assert(isequal(size(empty_cached.candidate_id), [0, 1]));
    assert(isequal(size(empty_cached.spots), [0, 6]));
    assert(isequal(size(empty_cached.intensity), [0, 55]));
    assert(isequal(size(empty_cached.scores), [0, 11]));
    assert(isequal(size(empty_cached.codebook_index), [0, 1]));
    fprintf('EXPORT_EVIDENCE_TEST_DIR=%s\n', output_root);
    fprintf('STATUS: SUCCESS | test_export_decode_evidence\n');
end

function [obj, metadata] = fixture()
    seq_a = repmat('1', 1, 11);
    seq_b = repmat('2', 1, 11);
    obj = struct();
    obj.registeredImages = zeros(7, 9, 4, 3, 11, 'uint8');
    obj.extractionParameters = struct('quality_threshold', 0.5, 'voxel_size', [3, 2, 1], ...
        'decoding_rounds', 11, 'intensityThresh_PR', 270, 'ref_round', 1);
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
    obj.maxIntensity_raw(6, 11) = 269.5;
    obj.maxIntensity_raw(7, 1) = 270;
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
