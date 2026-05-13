function [ geneToSeq, seqToGene ] = new_LoadCodebook_single_nc( inputPath, remove_index, doReverse, codeMap_mode )
% new_LoadCodebook
% 加载基因码本，并处理反转、编码转换及特定位去除

    % load file
    fname = fullfile(inputPath, 'genes.csv');
    % 确保读取为 string 类型以方便后续处理
    f = readmatrix(fname, 'OutputType', 'string', "Delimiter", ',');

    % load gene name and sequence 
    % f(:,1) - gene name
    % f(:,2) - gene barcode sequence (ATCG...)

    % reverse sequence of codebook: seqF + seqD + seqOmics/seqE
    if doReverse
        f(:,2) = reverse(f(:,2));
    end

    % encode barcode: 10 rounds -> 11 bits -> convert ATCG to 1234
    for i=1:size(f, 1)
        f(i,2) = new_EncodeBases(f(i,2), codeMap_mode);
    end
    
    if ~isempty(remove_index)
        % 1. 删除指定位置的字符
        f(:,2) = eraseBetween(f(:,2), remove_index, remove_index);

        % 2. Flip操作: 将删除位置之后的部分移到前面 (Swap front and back)
        % 注意：原始逻辑是提取 remove_index 之后和之前的部分进行交换
        % 假设 remove_index = 6，原来是 12345[6]7890
        % 删除后剩 123457890
        % back (before index 6): 12345
        % front (after index 6): 7890
        % 结果: 789012345
        front = extractBefore(f(:,2), remove_index);
        back = extractAfter(f(:,2), remove_index-1);
        
        f(:,2) = front + back;
    end
    
    % --- Debug Output: Formatted Display ---
    fprintf('\n%30s | %30s\n', 'Gene Name', 'Barcode');
    fprintf('%s\n', repmat('-', 1, 65)); % 分割线
    
    for i = 1:size(f, 1)
        % 将 string 转为 char 以确保 fprintf 兼容性，设置宽度30，右对齐
        gName = char(f(i, 1));
        gCode = char(f(i, 2));
        fprintf('%30s   %30s\n', gName, gCode);
    end
    fprintf('-----------------------------------------------------------------\n');
    % ---------------------------------------
    
    % 构建 Map 映射
    seqToGene = containers.Map(f(:,2), f(:,1));
    geneToSeq = containers.Map(f(:,1), f(:,2));

end