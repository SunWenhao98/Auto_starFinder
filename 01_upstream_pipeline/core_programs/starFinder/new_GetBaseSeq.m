function [bases, maxColors, baseScores] = new_GetBaseSeq( colorSeq )
%GetBaseSeq

    [Npoint, Nround, ~] = size(colorSeq);
    maxColors = zeros(Npoint, Nround);
    baseScores = zeros(Npoint, Nround);

    % determine maximal color for each round
    fprintf('Geting max color...\n');

    score_calling_timer = tic;
    [currMax, maxIndex] = max(colorSeq, [], 3);
    maxCount = sum(colorSeq == currMax, 3);
    is_nan = isnan(currMax);
    unique_max = maxCount == 1 & ~is_nan;
    maxColors(:) = -1;
    baseScores(:) = Inf;
    maxColors(unique_max) = maxIndex(unique_max);
    baseScores(unique_max) = -log(currMax(unique_max));
    count = sum(any(maxCount ~= 1 & ~is_nan, 2));
    fprintf('PHASE_TIMING: score_calling_seconds=%.2f\n', toc(score_calling_timer));
    fprintf('%d \n', count);
    
    
    % alexa decoding
    bases = cell(Npoint, 1);
    fprintf('Decoding...\n');
    % parfor i=1:Npoint
    %     if ~any(isinf(baseScores(i, :)))
    %         bases{i, 1} = Colorseq2Str(maxColors(i, :));
    %     end
    % end
    % fprintf('\n');

    string_decoding_timer = tic;
    valid_indices = find(~any(isinf(baseScores), 2));
    for valid_index = 1:numel(valid_indices)
        point_index = valid_indices(valid_index);
        bases{point_index, 1} = Colorseq2Str(maxColors(point_index, :));
    end
    fprintf('PHASE_TIMING: string_decoding_seconds=%.2f\n', toc(string_decoding_timer));
    fprintf('\n');

