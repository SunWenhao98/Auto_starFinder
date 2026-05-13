function s = Colorseq2Str( cs )
s = '';
for i=1:numel(cs)
    s = [s num2str(cs(i))];  % 使用方括号 [] 进行水平拼接（horizontal concatenation）
end

end

