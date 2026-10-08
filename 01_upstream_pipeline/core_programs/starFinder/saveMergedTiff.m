function saveMergedTiff(images, output_dir, filename_pattern, varargin)
% 沿 channel 取最大值，保留 Z；模板包含一个实际 round 占位。
p = inputParser;
addParameter(p, 'out_switch', false, @(x) islogical(x) && isscalar(x));
addParameter(p, 'tif_rounds', []);
addParameter(p, 'channels', 1:size(images, 4));
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
channels = p.Results.channels;
validateattributes(channels, {'numeric'}, {'vector','nonempty','integer','positive','finite','<=',size(images,4)});
for r = reshape(tif_rounds, 1, [])
    filename = fullfile(output_dir, sprintf(filename_pattern, r));
    for z = 1:size(images, 3)
        img_slice = max(images(:,:,z,channels,r), [], 4);
        mode = 'append';
        if z == 1
            mode = 'overwrite';
        end
        imwrite(img_slice, filename, 'WriteMode', mode);
    end
    fprintf('TIFF: %s | round=%d channels=%s\n', filename, r, mat2str(channels));
end
end
