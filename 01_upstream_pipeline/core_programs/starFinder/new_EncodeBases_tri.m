function colorSeq = new_EncodeBases_tri( seq, codeMap_mode )
% new_EncodeSOLID

    % construct hash table for encoding
    if strcmp(codeMap_mode, "Leica_rj")
        % Leica_RJ
        k = {'AT', 'GT', 'TT',...
             'AG', 'GG', 'TG',...
             'AA', 'GA', 'TA'};
        v = {3,1,2,...
             1,2,3,...
             2,3,1};
        coding = containers.Map(k,v);

        final_k = {'GT','GC'};
        final_v = {1,2};
        final_coding = containers.Map(final_k, final_v);

    elseif strcmp(codeMap_mode, "Olympus")
        % Olympus_XM
        k = {'AA','TT','GG',...
             'AG','TA','GT',...
             'AT','TG','GA'};
        v = {1,1,1,...
             2,2,2,...
             3,3,3};
        coding = containers.Map(k,v);

        final_k = {'GC', 'GT'};
        final_v = {1,2};
        final_coding = containers.Map(final_k, final_v);

    else
        error('Invalid codeMap_mode. Choose either "Leica_rj" or "Olympus".');
    end



    %  一种类似快慢指针策略，处理最后一对碱基不同编码的情况
    start = 1;
    back = start + 1;
    colorSeq = "";

    while back <= strlength(seq)
        curr_str = extractBetween(seq, start, back);
    	if back == strlength(seq) % omic
            colorSeq = colorSeq + final_coding(curr_str); 
        else
            colorSeq = colorSeq + coding(curr_str); 
        end
        start = start + 1;
        back = start + 1;
    end
    
end

