% function [geneToSeq, seqToGene] = new_LoadCodebook_tri(inputPath, remove_index, doReverse, codeMap_mode)
% % new_LoadCodebook

%     % Load file
%     fname = fullfile(inputPath, 'genes.csv');
%     f = readmatrix(fname, 'OutputType', 'string', "Delimiter", ',');
%     fprintf('Loaded codebook from %s\n', fname);

%     % Load gene name and sequence
%     % f(:,1) - gene name, f(:,2) - gene barcode
%     if doReverse
%         f(:,2) = reverse(f(:,2));
%     end

%     % from base to number index: three parts
%     for i = 1:size(f, 1)
%         f(i, 2) = new_EncodeBases_tri(f(i, 2), codeMap_mode);
%     end
    
%     if ~isempty(remove_index)
%         % Sort remove_index in ascending order
%         remove_index = sort(remove_index, 'ascend');  % [6, 12]

%         % Loop over each row in f
%         for row = 1:size(f, 1)
%             % Initialize segments for the current row
%             segments = strings(1, 0);  % Ensure segments is a string array
%                                         % initialize an empty string array

%             current_sequence = f(row, 2);

%             % Split the string into segments based on the adjusted indices
%             start_idx = 1;
%             for j = 1:length(remove_index)      % j = 1, 2
%                 end_idx = remove_index(j) - 1;
%                 if start_idx <= end_idx
%                     segments(end+1) = extractBetween(current_sequence, start_idx, end_idx);  % end+1 to add to the end of the array, 逐项添加
%                 end
%                 start_idx = remove_index(j) + 1;  % Adjust start_idx to skip the removed character
%             end

%             % Add the remaining part of the sequence as the last segment
%             if start_idx <= strlength(current_sequence)
%                 segments(end+1) = extractAfter(current_sequence, start_idx - 1);
%             end

%             % Reorder segments: move the second segment to the front
%             if numel(segments) > 1
%                 reordered_segments = [segments(2), segments(1), segments(3:end)];     % adjust the order of the segments
%             else
%                 reordered_segments = segments;
%             end

%             % Concatenate reordered segments
%             f(row, 2) = strjoin(reordered_segments, '');
%         end
%     end
    
%     disp(f(:, 2));
%     % Create the mappings
%     seqToGene = containers.Map(f(:, 2), f(:, 1));
%     geneToSeq = containers.Map(f(:, 1), f(:, 2));
% end
function [geneToSeq, seqToGene] = new_LoadCodebook_tri(inputPath, remove_index, doReverse, codeMap_mode)
% new_LoadCodebook_tri
% 加载三段式设计的码本，支持特定位置去除和片段重排

    % Load file
    fname = fullfile(inputPath, 'genes_tri.csv');
    f = readmatrix(fname, 'OutputType', 'string', "Delimiter", ',');
    fprintf('Loaded codebook from %s\n', fname);

    % Load gene name and sequence
    % f(:,1) - gene name, f(:,2) - gene barcode
    if doReverse
        f(:,2) = reverse(f(:,2));
    end

    % from base to number index: three parts
    for i = 1:size(f, 1)
        f(i, 2) = new_EncodeBases_tri(f(i, 2), codeMap_mode);
    end
    
    if ~isempty(remove_index)
        % Sort remove_index in ascending order
        remove_index = sort(remove_index, 'ascend');  % e.g., [6, 12]

        % Loop over each row in f
        for row = 1:size(f, 1)
            % Initialize segments for the current row
            segments = strings(1, 0);  % initialize an empty string array

            current_sequence = f(row, 2);

            % Split the string into segments based on the adjusted indices
            start_idx = 1;
            for j = 1:length(remove_index)      % j = 1, 2
                end_idx = remove_index(j) - 1;
                if start_idx <= end_idx
                    segments(end+1) = extractBetween(current_sequence, start_idx, end_idx);  % 逐项添加
                end
                start_idx = remove_index(j) + 1;  % Adjust start_idx to skip the removed character
            end

            % Add the remaining part of the sequence as the last segment
            if start_idx <= strlength(current_sequence)
                segments(end+1) = extractAfter(current_sequence, start_idx - 1);
            end

            % Reorder segments: move the second segment to the front
            % Logic: Swap segment 1 and 2, keep 3 onwards
            if numel(segments) > 1
                reordered_segments = [segments(2), segments(1), segments(3:end)]; 
            else
                reordered_segments = segments;
            end

            % Concatenate reordered segments
            f(row, 2) = strjoin(reordered_segments, '');
        end
    end
    
    % --- Debug Output: Formatted Display (Modified) ---
    fprintf('\n%30s | %30s\n', 'Gene Name', 'Barcode');
    fprintf('%s\n', repmat('-', 1, 65)); % 打印分割线
    
    for i = 1:size(f, 1)
        % 转换为 char 类型以确保 fprintf 兼容性
        gName = char(f(i, 1));
        gCode = char(f(i, 2));
        % %30s 表示占用30字符宽度，默认左侧补空格(即右对齐)
        fprintf('%30s   %30s\n', gName, gCode);
    end
    fprintf('-----------------------------------------------------------------\n');
    % --------------------------------------------------

    % Create the mappings
    seqToGene = containers.Map(f(:, 2), f(:, 1));
    geneToSeq = containers.Map(f(:, 1), f(:, 2));
end