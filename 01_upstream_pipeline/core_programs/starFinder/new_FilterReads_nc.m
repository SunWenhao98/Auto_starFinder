function obj = new_FilterReads( obj, endBases, showPlots, codeMap_mode )
    % 
    % FilterReads: for special situations where we need to filter reads
    % nc means non-continuous; this is for the case where we only have some rounds of one seq; we cannot decode continuously decodeCS, but we can still filter reads based on whether they are in the codebook

    % Filter reads by whether they are in the codebook
    % This is just as a sanity check; reads are actually filtered
    % by whether they are in the codebook


    % filtBases = obj.basecsMat;
    % correctSeqs = zeros(size(filtBases, 1), 1); % count sequences that are of correct form
    % % 打印前十个 filtBases 元素
    % %disp('前十个 filtBases 元素:');
    % %disp(filtBases(1:min(10, size(filtBases, 1)), :));

    % % older code for filtering reads in sequence space
    % bases = new_DecodeCS(filtBases, endBases(1), codeMap_mode);
    % disp('bases:');
    % disp(bases);

    % % seqD 端点校验：GxxxxA
    % for i=1:numel(bases)
    %     currSeq = bases{i};
    %     if currSeq(1) == endBases(1) && currSeq(end) == endBases(2)
    %     %if currSeq(1) == endBases(1) 
    %         correctSeqs(i) = 1;
    %     end
    % end
    
    fprintf('Filtration Statistics:\n');
    fprintf(obj.log, 'Filtration Statistics:\n');
    % score_1 = sum(correctSeqs)/size(filtBases,1);
    % s1 = sprintf('%f [%d / %d] percent of good reads match barcode pattern  %sNNNNN%s\n',...
    %     sum(correctSeqs)/size(filtBases,1),...
    %     sum(correctSeqs),...
    %     size(filtBases,1),...
    %     endBases(2),...
	%     endBases(1));
    % fprintf(s1);



    % filter reads based on codebook
    Nreads = numel(obj.allReads);
    inCodebook = zeros(Nreads,1);
    codebookSeqs = obj.barcodeSeqs;
    %disp('codebookseqs:');
    %disp(codebookSeqs);
    for s=1:Nreads
        str = obj.allReads{s};
        % disp(['Read Sequence ', num2str(s), ': ', str]);
        if ismember(str, codebookSeqs)         
            inCodebook(s) = 1;
        else
            inCodebook(s) = 0;
        end
    end

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



    % score_3 = sum(readsToKeep)/sum(correctSeqs);
    % s3 = sprintf('%f [%d / %d] percent of form matched reads are in codebook\n',...
    %     sum(readsToKeep)/sum(correctSeqs),...
    %     sum(readsToKeep), ...
    %     sum(correctSeqs));
    % fprintf(s3);


    % obj.FilterScores = [score_1 score_2 score_3]; % 3 scores for filtering
    obj.FilterScores = [score_2];
    if ~isempty(obj.log)
        % fprintf(obj.log, s1);
        fprintf(obj.log, s2);
        % fprintf(obj.log, s3);
    end
end
