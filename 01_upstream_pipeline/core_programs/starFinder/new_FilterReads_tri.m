function obj = new_FilterReads_tri( obj, endBases, showPlots, codeMap_mode )
% FilterReads_Tri

    % Filter reads by whether they are in the codebook
    % This is just as a sanity check; reads are actually filtered
    % by whether they are in the codebook
    filtBases = obj.basecsMat;  % Npoints*Nrounds
    correctSeqs = zeros(size(filtBases,1), 3); % count sequences that are of correct form
    cs_front = filtBases(:, 1:5);       % seqD
    cs_back = filtBases(:, 6:10);       % seqF
    cs_omics = filtBases(:,11);         % omics: seqE

    % Decode the sequences with the provided first end base
    bases_front = new_DecodeCS(cs_front, endBases(2), codeMap_mode);
    bases_back = new_DecodeCS(cs_back, endBases(3), codeMap_mode);
    bases_omics = new_DecodeCS_omic(cs_omics, endBases(1), codeMap_mode);
    
    disp('bases_front:');
    disp(bases_front);
    disp('bases_back:');
    disp(bases_back);
    disp('bases_omics:');
    disp(bases_omics);
    
    % seqD 端点校验：GxxxxA
    for i=1:numel(bases_front)
        currSeq = bases_front{i};
	    if currSeq(1) == endBases(2) && currSeq(end) == endBases(4)
            correctSeqs(i, 1) = 1;
        end 
    end

    % seqF 端点校验：AxxxxA
    for i=1:numel(bases_back)
        currSeq = bases_back{i};
	    if currSeq(1) == endBases(3) && currSeq(end) == endBases(5)
            correctSeqs(i, 2) = 1;
        end
    end

    % seqE 端点校验：Gc/Gt
    for i=1:numel(bases_omics)
        currSeq = bases_omics{i};
        if currSeq(1) == endBases(1)
            correctSeqs(i, 3) = 1;
        end
    end
    % 三者都正确才算正确
    correctSeq1 = correctSeqs(:,1);
    correctSeq2 = correctSeqs(:,2);
    correctSeqs = correctSeqs(:,1) .* correctSeqs(:,2) .* correctSeqs(:,3);
    fprintf('The shape of correctSeqs is %d x %d\n', size(correctSeqs,1), size(correctSeqs,2));


    fprintf('Filtration Statistics:\n');
    % fprintf(obj.log, 'Filtration Statistics:\n');

    % seqD 区段满足端点条件的比例
    s_seqD = sprintf('%f [%d / %d] percent of reads match seqD barcode pattern NN - %sNNNN%s - NNNNNN\n',...
        sum(correctSeq1)/size(filtBases,1),...
        sum(correctSeq1),...
        size(filtBases,1),...
        endBases(4),...
        endBases(2));
    fprintf(s_seqD);

    % seqD 和 seqF 区段均满足端点条件的比例
    s_seqF = sprintf('%f [%d / %d] percent of reads match seqF barcode pattern NN - NNNNNN - %sNNNN%s\n',...
        sum(correctSeq2)/size(filtBases,1),...
        sum(correctSeq2),...
        size(filtBases,1),...
        endBases(5),...
        endBases(3));
    fprintf(s_seqF);
        

    % 所有区段均满足端点条件的比例
    score_1 = sum(correctSeqs)/size(filtBases,1);
    s1 = sprintf('%f [%d / %d] percent of good reads match barcode pattern N%s - %sNNNN%s - %sNNNN%s\n',...
        sum(correctSeqs)/size(filtBases,1),...
        sum(correctSeqs),...
        size(filtBases,1),...
        endBases(1),...
        endBases(4),...
        endBases(2),...
        endBases(5),...
        endBases(3));
    fprintf(s1);


    % filter reads based on codebook
    Nreads = numel(obj.allReads);
    inCodebook = zeros(Nreads, 1);
    codebookSeqs = obj.barcodeSeqs;

    for s=1:Nreads
        str = obj.allReads{s};
        % disp(['Read Sequence ', num2str(s), ': ', str]);
        % disp(['Codebook Sequence ', codebookSeqs]);
        % codebook 已经包含了GC/GT 对应的两种可能，所以不需要再判断，直接查找即可
        if ismember(str, codebookSeqs)         
            inCodebook(s) = 1;
        else
            inCodebook(s) = 0;
        end
    end

    % sum(inCodebook)

    readsToKeep = inCodebook==1;
    obj.goodSpots = obj.allSpots(readsToKeep,:);
    obj.goodReads = obj.allReads(readsToKeep);
    obj.goodScores = obj.allScores(readsToKeep,:);
    obj.goodAllIntensity = obj.allIntensity(readsToKeep,:);
    obj.goodMaxIntensity = obj.maxIntensity(readsToKeep,:);

    if showPlots
        figure(1);
        errorbar(mean(obj.goodScores), std(obj.goodScores),'ko-'); 
        xlim([0 obj.Nround+1]); 
        xlabel('Round'); ylabel('Average qual score');
    end

    % 序列完全正确的比例
    score_2 = sum(readsToKeep)/Nreads;
    s2 = sprintf('%f [%d / %d] percent of good reads are in codebook\n',...
        sum(readsToKeep)/Nreads,...
        sum(readsToKeep),...
        Nreads);
    fprintf(s2);

    % 序列完全正确占满足端点条件的比例
    score_3 = sum(readsToKeep)/sum(correctSeqs);
    s3 = sprintf('%f [%d / %d] percent of form matched reads are in codebook\n',...
        sum(readsToKeep)/sum(correctSeqs),...
        sum(readsToKeep), ...
        sum(correctSeqs));            
    fprintf(s3);

    obj.FilterScores = [score_1 score_2 score_3]; 
    
    if ~isempty(obj.log)
        fprintf(obj.log, s_seqD);
        fprintf(obj.log, s_seqF);
        fprintf(obj.log, s1);
        fprintf(obj.log, s2);
        fprintf(obj.log, s3);
    end
        
end
