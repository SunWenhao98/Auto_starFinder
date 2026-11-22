function test_decode_pr_contracts(run_root, candidate_root)
% Small synthetic checks; run on a compute node with the saved source copies.
    paths = jsondecode(fileread(fullfile(run_root, 'paths.json')));
    before_dir = fullfile(run_root, 'source_before', 'core_programs', 'starFinder');
    if nargin < 2
        candidate_root = fileparts(fileparts(mfilename('fullpath')));
    end
    candidate_dir = fullfile(candidate_root, 'core_programs', 'starFinder');
    original_path = path;
    restore_path = onCleanup(@() path(original_path));
    addpath(fullfile(paths.target, 'core_programs', 'starFinder'), '-begin');
    output_dir = tempname;
    mkdir(output_dir);
    cleanup_output = onCleanup(@() rmdir(output_dir, 's'));
    rng(1729, 'twister');

    verify_legacy_baseline(before_dir, candidate_dir, output_dir);
    verify_base_calling(before_dir, candidate_dir);
    verify_candidate_rows(candidate_dir, output_dir);
    verify_rectangular_boundaries(candidate_dir, output_dir);
    verify_all_round_gate(candidate_dir, output_dir);
    verify_neighborhood_evidence(candidate_dir, output_dir);
    verify_plane9_separation(candidate_dir, output_dir);
    verify_parameter_failures(candidate_dir, output_dir);
    fprintf('STATUS: SUCCESS | test_decode_pr_contracts\n');
    clear cleanup_output restore_path
end

function select_source(source_dir)
    addpath(source_dir, '-begin');
    clear ExtractFromLocation_stats new_GetBaseSeq
    assert(strcmp(which('ExtractFromLocation_stats'), fullfile(source_dir, 'ExtractFromLocation_stats.m')));
    assert(strcmp(which('new_GetBaseSeq'), fullfile(source_dir, 'new_GetBaseSeq.m')));
end

function result = extract(source_dir, image, spots, radius, threshold, rounds, output_dir, output_count)
    select_source(source_dir);
    if nargin < 8
        output_count = 13;
    end
    [result{1:output_count}] = ExtractFromLocation_stats(image, spots, radius, 0.5, threshold, ...
                                              output_dir, 1, rounds, false, []);
end

function verify_legacy_baseline(before_dir, candidate_dir, output_dir)
    spots = [1 1 1 10 0 1; 7 8 4 20 0 2; 4 5 2 30 0 1; 4 5 2 31 0 2; 2 7 3 40 0 3];
    for dtype = ["uint8", "uint16"]
        image = cast(randi([0, double(intmax(dtype))], [8 8 4 3 3]), dtype);
        expected = extract(before_dir, image, spots, [1 1 1], 0, 3, output_dir, 12);
        actual = extract(candidate_dir, image, spots, [1 1 1], 0, 3, output_dir);
        for output_index = [1:6 8:12]
            assert(isequaln(actual{output_index}, expected{output_index}));
        end
        valid = ~any(isinf(expected{9}), 2);
        assert(isequal(actual{7}(valid), expected{7}(valid, 1)));
        assert(isequal(size(actual{7}), [size(spots, 1), 1]));
        assert(all(cellfun(@isempty, actual{7}(~valid))));
    end
    fprintf('PR_CONTRACT: legacy_baseline_uint8_uint16=PASS\n');
end

function verify_base_calling(before_dir, candidate_dir)
    colors = repmat(reshape([0.9 0.2 0.1], [1 1 3]), 7, 3, 1);
    colors(2, 2, :) = [0.5 0.5 0.1];
    colors(3, :, :) = NaN;
    colors(4, :, :) = 0;
    colors(5, 1, 1) = Inf;
    colors(6, 1, :) = [NaN 0.8 0.2];
    select_source(before_dir);
    [expected_reads, expected_colors, expected_scores] = new_GetBaseSeq(colors);
    select_source(candidate_dir);
    [reads, called_colors, scores] = new_GetBaseSeq(colors);
    assert(isequaln(called_colors, expected_colors));
    assert(isequaln(scores, expected_scores));
    valid = ~any(isinf(expected_scores), 2);
    assert(isequal(reads(valid), expected_reads(valid, 1)));
    assert(all(cellfun(@isempty, reads(~valid))));
    assert(isequal(size(reads), [7 1]));

    [reads, called_colors, scores] = new_GetBaseSeq(zeros(3, 11, 3));
    assert(isequal(size(reads), [3 1]));
    assert(all(cellfun(@isempty, reads)));
    assert(all(called_colors == -1, 'all'));
    assert(all(isinf(scores), 'all'));
    [reads, called_colors, scores] = new_GetBaseSeq(zeros(0, 11, 3));
    assert(isequal(size(reads), [0 1]));
    assert(isequal(size(called_colors), [0 11]));
    assert(isequal(size(scores), [0 11]));
    fprintf('PR_CONTRACT: ties_invalid_empty_base_calls=PASS\n');
end

function verify_candidate_rows(candidate_dir, output_dir)
    image = zeros(7, 7, 3, 3, 3, 'uint16');
    image(4, 4, 2, 1, :) = 200;
    image(5, 5, 2, 1:2, :) = 100;
    spots = [4 4 2 200 0 1; 4 4 2 190 0 2; 5 5 2 100 0 1; 1 1 1 0 0 3];
    actual = extract(candidate_dir, image, spots, [0 0 0], 108, 3, output_dir);
    assert(isequal(actual{2}, spots(1:2, :)));
    assert(isequal(actual{8}, spots));
    assert(isequal(size(actual{7}), [4 1]));
    raw_reads = actual{7};
    assert(strcmp(raw_reads{1}, raw_reads{2}));
    assert(all(cellfun(@isempty, actual{7}(3:4))));
    for output_index = [9 10 11 12]
        assert(size(actual{output_index}, 1) == size(spots, 1));
    end

    many_spots = repmat(spots(1, :), 4097, 1);
    many_spots(:, 4) = (1:4097)';
    chunked = extract(candidate_dir, image, many_spots, [0 0 0], 108, 3, output_dir);
    assert(isequal(chunked{2}, many_spots));
    assert(isequal(chunked{8}, many_spots));
    assert(all(chunked{12} == 200, 'all'));

    empty_result = extract(candidate_dir, image, zeros(0, 6), [1 1 1], 108, 3, output_dir);
    assert(isequal(size(empty_result{1}), [0 1]));
    assert(isequal(size(empty_result{2}), [0 6]));
    assert(isequal(size(empty_result{7}), [0 1]));
    assert(isequal(size(empty_result{11}), [0 15]));
    assert(isequal(size(empty_result{13}.channel_sum), [0 45]));
    assert(isequal(size(empty_result{13}.channel_l1), [0 45]));
    assert(isequal(size(empty_result{13}.voxel_count), [0 5]));
    assert(isequal(size(empty_result{13}.zero_signal), [0 15]));
    assert(isequal(size(empty_result{13}.pr_round_signal), [0 3]));
    fprintf('PR_CONTRACT: candidate_identity_duplicates_chunk_boundary_empty=PASS\n');
end

function verify_rectangular_boundaries(candidate_dir, output_dir)
    image = zeros(5, 8, 3, 3, 2, 'uint16');
    image(:, :, :, 1, :) = 20;
    image(:, :, :, 2, :) = 3;
    spots = [8 5 2; 8 1 1];
    actual = extract(candidate_dir, image, spots, [1 1 1], 0, 2, output_dir);
    expected_maxima = [240 240; 160 160];
    assert(isequal(actual{2}, spots));
    assert(isequal(actual{12}, expected_maxima));
    assert(isequal(actual{11}(:, [1 6]), repmat(20, 2, 2)));
    assert(isequal(actual{11}(:, [2 7]), expected_maxima));
    assert(isequal(actual{11}(:, [3 8]), [36 36; 24 24]));
    assert(isequal(actual{13}.pr_round_signal, single([80 80; 80 80])));
    cutoff = extract(candidate_dir, image, spots, [1 1 1], 80, 2, output_dir);
    assert(isequal(cutoff{2}, spots));
    cutoff = extract(candidate_dir, image, spots, [1 1 1], 81, 2, output_dir);
    assert(isempty(cutoff{2}));
    fprintf('PR_CONTRACT: rectangular_xyz_clipping_fixed_plane9_sum=PASS\n');
end

function verify_all_round_gate(candidate_dir, output_dir)
    image = zeros(7, 23, 3, 3, 11, 'uint16');
    amounts = [36 72 108 144 180];
    spots = [(4:4:20)' repmat([4 2], 5, 1)];
    for index = 1:5
        image(5, spots(index, 1), 2, 1, :) = amounts(index);
    end
    previous = true(5, 1);
    for threshold = [0 amounts]
        actual = extract(candidate_dir, image, spots, [1 1 1], threshold, 11, output_dir);
        expected_keep = amounts' >= threshold;
        assert(isequal(actual{2}, spots(expected_keep, :)));
        assert(all(~expected_keep | previous));
        assert(isequal(actual{12}, repmat(amounts', 1, 11)));
        assert(all(actual{11}(:, 1:5:end) == 0, 'all'));
        previous = expected_keep;
    end

    image(5, 4, 2, 1, 11) = 35;
    all_rounds = extract(candidate_dir, image, spots, [1 1 1], 36, 11, output_dir);
    first_ten = extract(candidate_dir, image, spots, [1 1 1], 36, 10, output_dir);
    assert(isequal(all_rounds{2}, spots(2:5, :)));
    assert(isequal(first_ten{2}, spots));
    image(5, 8, 2, 1, 4) = 35;
    internal_failure = extract(candidate_dir, image, spots, [1 1 1], 36, 11, output_dir);
    assert(isequal(internal_failure{2}, spots(3:5, :)));
    assert(size(internal_failure{7}, 1) == 5);
    fprintf('PR_CONTRACT: equality_all_rounds_center_diagnostic_monotonicity=PASS\n');
end

function verify_neighborhood_evidence(candidate_dir, output_dir)
    % The symmetric 1:27 cube gives hand-computable sums: count times 14.
    image = zeros(5, 5, 5, 3, 2, 'uint16');
    cube = reshape(uint16(1:27), 3, 3, 3);
    for channel = 1:3
        image(2:4, 2:4, 2:4, channel, 1) = cube .* uint16(channel);
        image(2:4, 2:4, 2:4, channel, 2) = cube .* uint16(4 - channel);
    end
    spots = [3 3 3; 3 3 3];
    actual = extract(candidate_dir, image, spots, [1 1 1], 0, 2, output_dir);
    evidence = actual{13};
    assert(isa(evidence.channel_sum, 'single'));
    assert(isa(evidence.channel_l1, 'single'));
    assert(isa(evidence.channel_l2, 'single'));
    assert(isa(evidence.voxel_count, 'uint8'));
    assert(islogical(evidence.zero_signal));
    assert(isequal(evidence.voxel_count, uint8(repmat([1 5 9 19 27], 2, 1))));
    manual_sums = [14 70 126 266 378];
    expected = zeros(2, 3, 5, 2, 'single');
    for neighborhood = 1:5
        expected(:, :, neighborhood, 1) = repmat(single(manual_sums(neighborhood) * [1 2 3]), 2, 1);
        expected(:, :, neighborhood, 2) = repmat(single(manual_sums(neighborhood) * [3 2 1]), 2, 1);
    end
    assert(isequal(evidence.channel_sum, reshape(expected, 2, [])));
    assert(isequal(evidence.pr_round_signal, single(repmat([378 378], 2, 1))));
    expected_double = double(expected);
    expected_l1 = single(expected_double ./ sum(expected_double, 2));
    expected_l2 = single(expected_double ./ (sqrt(sum(expected_double.^2, 2)) + 1E-6));
    assert(isequal(evidence.channel_l1, reshape(expected_l1, 2, [])));
    assert(isequal(evidence.channel_l2, reshape(expected_l2, 2, [])));
    assert(~any(evidence.zero_signal, 'all'));

    % Decode radius zero must stay radius zero; evidence still uses five fixed masks.
    radius_zero = extract(candidate_dir, image, spots, [0 0 0], 0, 2, output_dir);
    assert(isequal(radius_zero{11}(:, [2 3 4]), repmat([14 28 42], 2, 1)));
    assert(isequaln(radius_zero{13}, evidence));

    edge_image = ones(3, 3, 3, 3, 2, 'uint16');
    edge = extract(candidate_dir, edge_image, [1 1 1], [1 1 1], 0, 2, output_dir);
    assert(isequal(edge{13}.voxel_count, uint8([1 3 4 7 8])));
    expected_edge = reshape(repmat(single([1 3 4 7 8]), 3, 1), 1, []);
    assert(isequal(edge{13}.channel_sum, [expected_edge expected_edge]));

    zero_image = zeros(3, 3, 3, 3, 2, 'uint8');
    zero = extract(candidate_dir, zero_image, [2 2 2], [1 1 1], 0, 2, output_dir);
    assert(all(zero{13}.channel_sum == 0, 'all'));
    assert(all(isnan(zero{13}.channel_l1), 'all'));
    assert(all(zero{13}.channel_l2 == 0, 'all'));
    assert(all(zero{13}.zero_signal, 'all'));
    fprintf('PR_CONTRACT: five_masks_ratios_order_counts_zero_independent_decode_window=PASS\n');
end

function verify_plane9_separation(candidate_dir, output_dir)
    image = zeros(7, 11, 5, 3, 11, 'uint16');
    spots = [3 4 3; 8 4 3];
    % Candidate one: strong upper/lower layers, dark current plane.
    image(3:5, 2:4, 2, 1, :) = 20;
    image(3:5, 2:4, 4, 1, :) = 20;
    % Candidate two: dark center, bright same-plane neighbor at exact threshold.
    image(4, 9, 3, 2, :) = 36;
    actual = extract(candidate_dir, image, spots, [1 1 1], 36, 11, output_dir);
    assert(isequal(actual{2}, spots(2, :)));
    assert(isequal(actual{12}, repmat([360; 36], 1, 11)));
    assert(isequal(actual{13}.pr_round_signal, single(repmat([0; 36], 1, 11))));
    assert(all(actual{11}(:, 1:5:end) == 0, 'all'));
    fprintf('PR_CONTRACT: upper_lower_signal_excluded_same_plane_neighbor_included=PASS\n');
end

function verify_parameter_failures(candidate_dir, output_dir)
    image = zeros(3, 3, 3, 3, 11, 'uint8');
    spot = [2 2 2];
    expect_failure(@() extract(candidate_dir, image, spot, [1 1 1], 108, 12, output_dir));
    expect_failure(@() extract(candidate_dir, image, spot, [1 1 1], 108, 0, output_dir));
    expect_failure(@() extract(candidate_dir, image, spot, [1 1 1], 108, 2.5, output_dir));
    expect_failure(@() extract(candidate_dir, image, spot, [1 1 1], -1, 11, output_dir));
    expect_failure(@() extract(candidate_dir, image, spot, [1 1 1], Inf, 11, output_dir));
    expect_failure(@() extract(candidate_dir, image, spot, [1 1], 108, 11, output_dir));
    fprintf('PR_CONTRACT: required_rounds_and_scientific_values=PASS\n');
end

function expect_failure(operation)
    failed = false;
    try
        operation();
    catch
        failed = true;
    end
    assert(failed);
end
