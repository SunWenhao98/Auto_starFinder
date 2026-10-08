function SaveSingleTiff(images, output_dir, filename_pattern, varargin)
% 按实际 round/channel 写三维 stack；模板依次包含 round、channel 占位。
p = inputParser;
addParameter(p, 'out_switch', false, @(x) islogical(x) && isscalar(x));
addParameter(p, 'tif_rounds', []);
parse(p, varargin{:});
if ~p.Results.out_switch
    return;
end
tif_rounds = p.Results.tif_rounds;
if isempty(tif_rounds)
    tif_rounds = 1:size(images, 5);
end
validateattributes(tif_rounds, {'numeric'}, {'vector','integer','positive','finite','<=',size(images,5)});
assert(numel(unique(tif_rounds)) == numel(tif_rounds), 'tif_rounds must be unique.');
for r = reshape(tif_rounds, 1, [])
    for c = 1:size(images, 4)
        filename = fullfile(output_dir, sprintf(filename_pattern, r, c));
        for z = 1:size(images, 3)
            mode = 'append';
            if z == 1
                mode = 'overwrite';
            end
            imwrite(images(:,:,z,c,r), filename, 'WriteMode', mode);
        end
        fprintf('TIFF: %s | round=%d channel=%d\n', filename, r, c);
    end
end
end

