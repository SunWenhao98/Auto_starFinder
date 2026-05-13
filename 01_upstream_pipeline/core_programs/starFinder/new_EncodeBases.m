function colorSeq = new_EncodeBases( seq, codeMap_mode )
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
    elseif strcmp(codeMap_mode, "Olympus")
        % Olympus_XM
        k = {'AA','TT','GG',...
            'AG','TA','GT',...
            'AT','TG','GA'};
        v = {1,1,1,...
            2,2,2,...
            3,3,3};
        coding = containers.Map(k,v);
    else
        error('Invalid codeMap_mode. Choose either "Leica_rj" or "Olympus".');
    
    end

    
    start = 1;
    back = start + 1;
    colorSeq = "";
    while back <= strlength(seq)
        curr_str = extractBetween(seq, start, back);
        colorSeq = colorSeq + coding(curr_str);
        start = start + 1;
        back = start + 1;
    end
    
end

