function p26_register_mosaic_matlab(varargin)
%P26_REGISTER_MOSAIC_MATLAB Estimate a moving-to-reference DAPI mosaic shift.
%   The full mosaics are never passed to FFT. Coarse registration uses a
%   strided overview and fine registration uses multiple full-resolution ROIs.

parser = inputParser;
addParameter(parser, 'fixed_mosaic', '', @ischar);
addParameter(parser, 'moving_mosaic', '', @ischar);
addParameter(parser, 'output_json', '', @ischar);
addParameter(parser, 'output_csv', '', @ischar);
addParameter(parser, 'output_roi_csv', '', @ischar);
addParameter(parser, 'overview_downsample', 16, @isnumeric);
addParameter(parser, 'roi_size_px', 1024, @isnumeric);
addParameter(parser, 'roi_count', 9, @isnumeric);
addParameter(parser, 'min_valid_rois', 4, @isnumeric);
addParameter(parser, 'min_overlap_ratio', 0.2, @isnumeric);
addParameter(parser, 'max_roi_spread_px', 1.0, @isnumeric);
addParameter(parser, 'overwrite', false, @(x) islogical(x) || isnumeric(x));
addParameter(parser, 'dft_helper_dir', '', @ischar);
parse(parser, varargin{:});
options = parser.Results;

requiredText = {'fixed_mosaic', 'moving_mosaic', 'output_json', ...
    'output_csv', 'output_roi_csv', 'dft_helper_dir'};
for index = 1:numel(requiredText)
    name = requiredText{index};
    if isempty(options.(name))
        error('p26:MissingParameter', '%s is required', name);
    end
end

outputs = {options.output_json, options.output_csv, options.output_roi_csv};
if ~logical(options.overwrite)
    for index = 1:numel(outputs)
        if isfile(outputs{index})
            error('p26:OutputExists', ...
                'Refusing to overwrite existing output: %s', outputs{index});
        end
    end
end
for index = 1:numel(outputs)
    outputParent = fileparts(outputs{index});
    if ~isempty(outputParent) && ~isfolder(outputParent)
        mkdir(outputParent);
    end
end

addpath(options.dft_helper_dir);
if exist('DFTRegister2D', 'file') ~= 2
    error('p26:MissingDFTHelper', ...
        'DFTRegister2D.m was not found under %s', options.dft_helper_dir);
end

fixedInfo = single_plane_info(options.fixed_mosaic);
movingInfo = single_plane_info(options.moving_mosaic);
fixedIdentity = image_identity(options.fixed_mosaic, fixedInfo);
movingIdentity = image_identity(options.moving_mosaic, movingInfo);
downsample = round(options.overview_downsample);
if downsample < 1
    error('p26:InvalidDownsample', 'overview_downsample must be at least 1');
end

fprintf('[MATLAB] Building strided overviews with downsample=%d\n', downsample);
fixedOverview = read_strided_overview(options.fixed_mosaic, fixedInfo, downsample);
movingOverview = read_strided_overview(options.moving_mosaic, movingInfo, downsample);

commonHeight = max(size(fixedOverview, 1), size(movingOverview, 1));
commonWidth = max(size(fixedOverview, 2), size(movingOverview, 2));
fixedPadded = zeros(commonHeight, commonWidth, 'single');
movingPadded = zeros(commonHeight, commonWidth, 'single');
fixedPadded(1:size(fixedOverview, 1), 1:size(fixedOverview, 2)) = ...
    prepare_for_correlation(fixedOverview);
movingPadded(1:size(movingOverview, 1), 1:size(movingOverview, 2)) = ...
    prepare_for_correlation(movingOverview);
clear fixedOverview movingOverview;

coarseParameters = DFTRegister2D(fixedPadded, movingPadded, false);
coarseShiftY = double(coarseParameters.shifts(1)) * downsample;
coarseShiftX = double(coarseParameters.shifts(2)) * downsample;
clear fixedPadded movingPadded;

[overlapBounds, overlapRatio] = overlap_bounds( ...
    [fixedInfo.Height, fixedInfo.Width], ...
    [movingInfo.Height, movingInfo.Width], ...
    [coarseShiftY, coarseShiftX]);
if overlapRatio < options.min_overlap_ratio
    error('p26:InsufficientOverlap', ...
        'Estimated overlap %.4f is below %.4f', ...
        overlapRatio, options.min_overlap_ratio);
end

roiSize = round(options.roi_size_px);
roiCount = round(options.roi_count);
minValidRois = round(options.min_valid_rois);
candidates = candidate_origins(overlapBounds, roiSize, max(roiCount * 4, 9));
candidateData = repmat(empty_candidate(), 0, 1);
for index = 1:size(candidates, 1)
    fixedOrigin = candidates(index, :);
    movingOrigin = round(fixedOrigin - [coarseShiftY, coarseShiftX]);
    if movingOrigin(1) < 0 || movingOrigin(2) < 0 || ...
            movingOrigin(1) + roiSize > movingInfo.Height || ...
            movingOrigin(2) + roiSize > movingInfo.Width
        continue;
    end
    fixedRoi = read_roi(options.fixed_mosaic, fixedOrigin, roiSize);
    movingRoi = read_roi(options.moving_mosaic, movingOrigin, roiSize);
    fixedValidRatio = nnz(isfinite(fixedRoi) & fixedRoi ~= 0) / numel(fixedRoi);
    movingValidRatio = nnz(isfinite(movingRoi) & movingRoi ~= 0) / numel(movingRoi);
    if min(fixedValidRatio, movingValidRatio) < 0.02
        continue;
    end
    textureScore = std(double(fixedRoi), 0, 'all') + ...
        std(double(movingRoi), 0, 'all');
    if ~isfinite(textureScore) || textureScore <= 0
        continue;
    end
    entry = empty_candidate();
    entry.fixed_origin_yx = fixedOrigin;
    entry.moving_origin_yx = movingOrigin;
    entry.fixed_roi = fixedRoi;
    entry.moving_roi = movingRoi;
    entry.fixed_valid_ratio = fixedValidRatio;
    entry.moving_valid_ratio = movingValidRatio;
    entry.texture_score = textureScore;
    candidateData(end + 1, 1) = entry; %#ok<AGROW>
end

if numel(candidateData) < minValidRois
    error('p26:InsufficientROIs', ...
        'Only %d usable ROI pairs; need %d', numel(candidateData), minValidRois);
end
[~, ranking] = sort([candidateData.texture_score], 'descend');
candidateData = candidateData(ranking(1:min(roiCount, numel(ranking))));

roiResults = repmat(empty_roi_result(), numel(candidateData), 1);
globalShifts = zeros(numel(candidateData), 2);
for index = 1:numel(candidateData)
    candidate = candidateData(index);
    [localShift, peakQuality] = local_dft_subpixel_shift( ...
        candidate.fixed_roi, candidate.moving_roi);
    globalShift = localShift + candidate.fixed_origin_yx - ...
        candidate.moving_origin_yx;
    globalShifts(index, :) = globalShift;
    roiResults(index).roi_index = index - 1;
    roiResults(index).fixed_origin_yx = candidate.fixed_origin_yx;
    roiResults(index).moving_origin_yx = candidate.moving_origin_yx;
    roiResults(index).size_yx = [roiSize, roiSize];
    roiResults(index).local_shift_y_px = localShift(1);
    roiResults(index).local_shift_x_px = localShift(2);
    roiResults(index).global_shift_y_px = globalShift(1);
    roiResults(index).global_shift_x_px = globalShift(2);
    roiResults(index).registration_peak_quality = peakQuality;
    roiResults(index).fixed_valid_ratio = candidate.fixed_valid_ratio;
    roiResults(index).moving_valid_ratio = candidate.moving_valid_ratio;
    roiResults(index).texture_score = candidate.texture_score;
end

consensus = robust_consensus(globalShifts, minValidRois, ...
    options.max_roi_spread_px);
for index = 1:numel(roiResults)
    roiResults(index).inlier = logical(consensus.inlier_mask(index));
end

coordinateSystem = struct();
coordinateSystem.axis_order = 'xy';
coordinateSystem.units = 'pixel';
coordinateSystem.pixel_origin = 'zero_based';
coordinateSystem.x_axis = 'image_column_increasing_right';
coordinateSystem.y_axis = 'image_row_increasing_down';
coordinateSystem.formula = struct( ...
    'x_ref', 'x_moving + shift_x_px', ...
    'y_ref', 'y_moving + shift_y_px');

result = struct();
result.schema_name = 'starfinder_translation_registration';
result.schema_version = '1.1';
result.transform_type = 'translation_2d';
result.mapping = 'moving_to_reference';
result.coordinate_system = coordinateSystem;
finalFixedInfo = single_plane_info(options.fixed_mosaic);
finalMovingInfo = single_plane_info(options.moving_mosaic);
finalFixedIdentity = image_identity(options.fixed_mosaic, finalFixedInfo);
finalMovingIdentity = image_identity(options.moving_mosaic, finalMovingInfo);
assert_identity_unchanged('Reference', fixedIdentity, finalFixedIdentity);
assert_identity_unchanged('Moving', movingIdentity, finalMovingIdentity);
result.reference = fixedIdentity;
result.moving = movingIdentity;
result.transform = struct( ...
    'shift_x_px', consensus.shift_x_px, ...
    'shift_y_px', consensus.shift_y_px);
parameters = struct( ...
    'overview_downsample', downsample, ...
    'roi_size_px', roiSize, ...
    'roi_count', roiCount, ...
    'min_valid_rois', minValidRois, ...
    'min_overlap_ratio', options.min_overlap_ratio, ...
    'max_roi_spread_px', options.max_roi_spread_px);
result.method = struct( ...
    'backend', 'matlab', ...
    'algorithm', 'coarse_to_fine_dft_correlation', ...
    'backend_version', version('-release'), ...
    'parameters', parameters);
result.quality = struct( ...
    'status', consensus.status, ...
    'coarse_shift_x_px', coarseShiftX, ...
    'coarse_shift_y_px', coarseShiftY, ...
    'estimated_overlap_ratio', overlapRatio, ...
    'n_rois_requested', roiCount, ...
    'n_rois_valid', size(globalShifts, 1), ...
    'n_rois_inlier', consensus.n_inlier, ...
    'roi_shift_mad_px', consensus.mad_px, ...
    'roi_shift_spread_px', consensus.spread_px);
result.roi_results = roiResults;

write_json(options.output_json, result);
write_summary_csv(options.output_csv, result);
write_roi_csv(options.output_roi_csv, roiResults);
fprintf('[MATLAB] Registration status=%s shift_x_px=%.4f shift_y_px=%.4f\n', ...
    consensus.status, consensus.shift_x_px, consensus.shift_y_px);
if ~strcmp(consensus.status, 'PASS')
    error('p26:RegistrationRejected', ...
        'Registration rejected: ROI spread %.4f px', consensus.spread_px);
end
end


function info = single_plane_info(path)
allInfo = imfinfo(path);
if numel(allInfo) ~= 1
    error('p26:Expected2D', ...
        'Expected one 2D image plane, found %d pages in %s', numel(allInfo), path);
end
info = allInfo(1);
end


function overview = read_strided_overview(path, info, downsample)
rowRegion = [1, downsample, info.Height];
columnRegion = [1, downsample, info.Width];
overview = single(imread(path, 'PixelRegion', {rowRegion, columnRegion}));
end


function prepared = prepare_for_correlation(image)
prepared = single(image);
valid = isfinite(prepared) & prepared ~= 0;
prepared(~isfinite(prepared)) = 0;
if any(valid, 'all')
    prepared(valid) = prepared(valid) - mean(prepared(valid), 'double');
end
windowY = cosine_window(size(prepared, 1));
windowX = cosine_window(size(prepared, 2));
prepared = prepared .* (windowY * windowX');
end


function values = cosine_window(count)
if count <= 1
    values = ones(count, 1, 'single');
else
    indices = single((0:count - 1)');
    values = 0.5 - 0.5 * cos(2 * pi * indices / single(count - 1));
end
end


function [bounds, overlapRatio] = overlap_bounds(fixedShape, movingShape, shift)
y0 = max(0, ceil(shift(1)));
x0 = max(0, ceil(shift(2)));
y1 = min(fixedShape(1), floor(shift(1) + movingShape(1)));
x1 = min(fixedShape(2), floor(shift(2) + movingShape(2)));
bounds = [y0, y1, x0, x1];
overlapArea = max(0, y1 - y0) * max(0, x1 - x0);
smallerArea = min(prod(fixedShape), prod(movingShape));
overlapRatio = overlapArea / smallerArea;
end


function origins = candidate_origins(bounds, roiSize, candidateCount)
if bounds(2) - bounds(1) < roiSize || bounds(4) - bounds(3) < roiSize
    origins = zeros(0, 2);
    return;
end
side = max(1, ceil(sqrt(candidateCount)));
yValues = round(linspace(bounds(1), bounds(2) - roiSize, side));
xValues = round(linspace(bounds(3), bounds(4) - roiSize, side));
[xGrid, yGrid] = meshgrid(xValues, yValues);
origins = unique([yGrid(:), xGrid(:)], 'rows', 'stable');
end


function roi = read_roi(path, originYX, roiSize)
rowRegion = [originYX(1) + 1, originYX(1) + roiSize];
columnRegion = [originYX(2) + 1, originYX(2) + roiSize];
roi = single(imread(path, 'PixelRegion', {rowRegion, columnRegion}));
end


function [shift, peakQuality] = local_dft_subpixel_shift(fixed, moving)
fixedPrepared = prepare_for_correlation(fixed);
movingPrepared = prepare_for_correlation(moving);
correlation = abs(ifft2(fft2(fixedPrepared) .* conj(fft2(movingPrepared))));
[peakValue, linearIndex] = max(correlation(:));
[rowIndex, columnIndex] = ind2sub(size(correlation), linearIndex);
rowAxis = ifftshift(-fix(size(correlation, 1) / 2): ...
    ceil(size(correlation, 1) / 2) - 1);
columnAxis = ifftshift(-fix(size(correlation, 2) / 2): ...
    ceil(size(correlation, 2) / 2) - 1);
rowOffset = parabolic_offset(correlation(:, columnIndex), rowIndex);
columnOffset = parabolic_offset(correlation(rowIndex, :)', columnIndex);
shift = [double(rowAxis(rowIndex)) + rowOffset, ...
    double(columnAxis(columnIndex)) + columnOffset];
denominator = norm(double(fixedPrepared(:))) * norm(double(movingPrepared(:)));
peakQuality = double(peakValue) / max(denominator, eps);
end


function offset = parabolic_offset(values, peakIndex)
count = numel(values);
previousIndex = mod(peakIndex - 2, count) + 1;
nextIndex = mod(peakIndex, count) + 1;
previousValue = double(values(previousIndex));
peakValue = double(values(peakIndex));
nextValue = double(values(nextIndex));
denominator = previousValue - 2 * peakValue + nextValue;
if abs(denominator) <= eps
    offset = 0;
else
    offset = 0.5 * (previousValue - nextValue) / denominator;
    offset = max(-0.5, min(0.5, offset));
end
end


function consensus = robust_consensus(shifts, minValid, maxSpread)
if size(shifts, 1) < minValid || any(~isfinite(shifts), 'all')
    error('p26:InvalidShifts', 'Insufficient or non-finite ROI shifts');
end
initialMedian = median(shifts, 1);
distances = sqrt(sum((shifts - initialMedian) .^ 2, 2));
madValue = median(abs(distances - median(distances)));
threshold = max(0.25, 3 * 1.4826 * madValue);
inlierMask = distances <= threshold;
if nnz(inlierMask) < minValid
    [~, order] = sort(distances, 'ascend');
    inlierMask = false(size(distances));
    inlierMask(order(1:minValid)) = true;
end
inlierShifts = shifts(inlierMask, :);
finalShift = median(inlierShifts, 1);
spread = max(sqrt(sum((inlierShifts - finalShift) .^ 2, 2)));
if spread <= maxSpread
    status = 'PASS';
else
    status = 'REJECTED';
end
consensus = struct( ...
    'shift_y_px', finalShift(1), ...
    'shift_x_px', finalShift(2), ...
    'inlier_mask', inlierMask, ...
    'n_inlier', nnz(inlierMask), ...
    'mad_px', madValue, ...
    'spread_px', spread, ...
    'status', status);
end


function identity = image_identity(path, info)
canonicalFile = java.io.File(path).getCanonicalFile();
identity = struct( ...
    'image', char(canonicalFile.getPath()), ...
    'height_px', info.Height, ...
    'width_px', info.Width, ...
    'dtype', image_dtype(info), ...
    'size_bytes', int64(canonicalFile.length()), ...
    'mtime_epoch_s', idivide(int64(canonicalFile.lastModified()), int64(1000), 'floor'));
end


function dtype = image_dtype(info)
bits = double(info.BitDepth);
if isfield(info, 'SampleFormat')
    sampleFormat = lower(char(info.SampleFormat));
else
    sampleFormat = 'unsigned integer';
end
if contains(sampleFormat, 'unsigned')
    prefix = 'uint';
elseif contains(sampleFormat, 'signed') || contains(sampleFormat, 'integer')
    prefix = 'int';
elseif contains(sampleFormat, 'float') || contains(sampleFormat, 'real')
    if bits == 32
        dtype = 'float32';
    elseif bits == 64
        dtype = 'float64';
    else
        error('p26:UnsupportedDtype', ...
            'Unsupported floating-point TIFF bit depth: %d', bits);
    end
    return;
else
    error('p26:UnsupportedDtype', ...
        'Unsupported TIFF SampleFormat: %s', sampleFormat);
end
if ~ismember(bits, [8, 16, 32, 64])
    error('p26:UnsupportedDtype', ...
        'Unsupported integer TIFF bit depth: %d', bits);
end
dtype = sprintf('%s%d', prefix, bits);
end


function assert_identity_unchanged(label, before, after)
fields = fieldnames(before);
changed = cell(0, 1);
for index = 1:numel(fields)
    name = fields{index};
    if ~isequal(before.(name), after.(name))
        changed{end + 1, 1} = name; %#ok<AGROW>
    end
end
if ~isempty(changed)
    error('p26:InputChanged', ...
        '%s mosaic changed while registration was running: %s', ...
        label, strjoin(changed, ', '));
end
end


function write_json(path, result)
fileId = fopen(path, 'w');
if fileId < 0
    error('p26:OutputOpenFailed', 'Cannot open output JSON: %s', path);
end
cleanup = onCleanup(@() fclose(fileId));
fprintf(fileId, '%s\n', jsonencode(result));
end


function write_summary_csv(path, result)
summary = table( ...
    string(result.schema_name), ...
    string(result.schema_version), ...
    string(result.reference.image), ...
    string(result.moving.image), ...
    string(result.method.backend), ...
    string(result.mapping), ...
    result.transform.shift_x_px, ...
    result.transform.shift_y_px, ...
    string(result.quality.status), ...
    result.quality.n_rois_valid, ...
    result.quality.n_rois_inlier, ...
    result.quality.roi_shift_spread_px, ...
    'VariableNames', {'schema_name', 'schema_version', 'reference_image', ...
    'moving_image', 'backend', 'mapping', 'shift_x_px', 'shift_y_px', ...
    'status', 'n_rois_valid', 'n_rois_inlier', 'roi_shift_spread_px'});
writetable(summary, path);
end


function write_roi_csv(path, results)
fixedOrigins = vertcat(results.fixed_origin_yx);
movingOrigins = vertcat(results.moving_origin_yx);
roiTable = table( ...
    [results.roi_index]', ...
    fixedOrigins(:, 1), fixedOrigins(:, 2), ...
    movingOrigins(:, 1), movingOrigins(:, 2), ...
    [results.local_shift_y_px]', [results.local_shift_x_px]', ...
    [results.global_shift_y_px]', [results.global_shift_x_px]', ...
    [results.registration_peak_quality]', ...
    [results.fixed_valid_ratio]', [results.moving_valid_ratio]', ...
    [results.texture_score]', [results.inlier]', ...
    'VariableNames', {'roi_index', 'fixed_origin_y0', 'fixed_origin_x0', ...
    'moving_origin_y0', 'moving_origin_x0', 'local_shift_y_px', ...
    'local_shift_x_px', 'global_shift_y_px', 'global_shift_x_px', ...
    'registration_peak_quality', 'fixed_valid_ratio', ...
    'moving_valid_ratio', 'texture_score', 'inlier'});
writetable(roiTable, path);
end


function candidate = empty_candidate()
candidate = struct( ...
    'fixed_origin_yx', [0, 0], ...
    'moving_origin_yx', [0, 0], ...
    'fixed_roi', single([]), ...
    'moving_roi', single([]), ...
    'fixed_valid_ratio', 0, ...
    'moving_valid_ratio', 0, ...
    'texture_score', 0);
end


function result = empty_roi_result()
result = struct( ...
    'roi_index', 0, ...
    'fixed_origin_yx', [0, 0], ...
    'moving_origin_yx', [0, 0], ...
    'size_yx', [0, 0], ...
    'local_shift_y_px', 0, ...
    'local_shift_x_px', 0, ...
    'global_shift_y_px', 0, ...
    'global_shift_x_px', 0, ...
    'registration_peak_quality', 0, ...
    'fixed_valid_ratio', 0, ...
    'moving_valid_ratio', 0, ...
    'texture_score', 0, ...
    'inlier', false);
end
