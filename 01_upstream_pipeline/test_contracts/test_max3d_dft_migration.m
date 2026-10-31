function test_max3d_dft_migration
% 验证 detector 的定位、输出顺序及重复记录保持原样，并检查 DFT 边界。
    fprintf('MAX3D_SOURCE=%s\n', which('SpotFindingMax3D'));
    fprintf('DFTAPPLY3D_SOURCE=%s\n', which('DFTApply3D'));
    rng(1729, 'twister');
    detector_cases = 0;
    for dtype = ["uint8", "uint16"]
        peak = double(intmax(dtype));
        for channels = [1, 3, 4]
            random_image = cast(randi([0, peak], [19, 23, 7, channels, 2]), dtype);
            plateau = zeros(19, 23, 7, channels, 2, dtype);
            plateau(4:5, 8:9, 3:4, :, 2) = cast(peak, dtype);
            for image = {random_image, plateau, zeros(size(plateau), dtype)}
                for threshold = [0, 0.2, 1]
                    expected = legacy_max3d(image{1}, 2, threshold);
                    actual = SpotFindingMax3D(image{1}, 2, threshold);
                    assert(strcmp(class(actual), class(expected)));
                    assert(isequal(actual, expected));
                    detector_cases = detector_cases + 1;
                end
            end
        end

        % 非凸亮环的旧质心在暗中心；不得引入 smoke 的平台分量定位改动。
        ring = zeros(19, 23, 7, 3, 2, dtype);
        ring(5:7, 9:11, 3, :, 2) = cast(peak, dtype);
        ring(6, 10, 3, :, 2) = 0;
        expected = legacy_max3d(ring, 2, 0.2);
        actual = SpotFindingMax3D(ring, 2, 0.2);
        assert(isequal(actual, expected));
        assert(size(actual, 1) == 3);
        assert(all(actual(:, 1:3) == int16([10, 6, 3]), 'all'));
        assert(all(actual(:, 4) == 0));
        assert(isequal(double(actual(:, 6)), (1:3)'));
        detector_cases = detector_cases + 1;
    end
    fprintf('MAX3D_EQUIVALENCE_CASES=%d\n', detector_cases);

    % 非常量体积同时约束平移方向及保留体素，覆盖空间与预 FFT 输入。
    volume = reshape(1:(5 * 6 * 7), [5, 6, 7]);
    boundary_cases = 0;
    for axis_index = 1:3
        for displacement = [-1, 0, 1]
            shifts = zeros(1, 3);
            shifts(axis_index) = displacement;
            expected = zeros(size(volume));
            source = repmat({':'}, 1, 3);
            target = source;
            if displacement < 0
                source{axis_index} = 2:size(volume, axis_index);
                target{axis_index} = 1:(size(volume, axis_index) - 1);
            elseif displacement > 0
                source{axis_index} = 1:(size(volume, axis_index) - 1);
                target{axis_index} = 2:size(volume, axis_index);
            end
            expected(target{:}) = volume(source{:});
            for pre_fft = [false, true]
                input = volume;
                if pre_fft
                    input = fftn(volume);
                end
                actual = DFTApply3D(input, struct('shifts', shifts, 'diffphase', 0), pre_fft);
                assert(max(abs(actual - expected), [], 'all') < 1e-9);
                boundary_cases = boundary_cases + 1;
            end
        end
    end
    fprintf('DFT3D_TRANSLATION_BOUNDARY_CASES=%d\n', boundary_cases);
    fprintf('STATUS: SUCCESS | test_max3d_dft_migration\n');
end

function locations = legacy_max3d(input_img, ref_index, intensity_threshold)
% 既有逐点实现作为行为 oracle，保留 MATLAB 整数转换及拼接语义。
    locations = [];
    ref_round = input_img(:, :, :, :, ref_index);
    for channel = 1:min(size(input_img, 4), 3)
        image = ref_round(:, :, :, channel);
        maxima = imregionalmax(image);
        switch class(input_img)
            case 'uint8'
                selected = maxima & image > intensity_threshold * 255;
            case 'uint16'
                selected = maxima & image > intensity_threshold * 65535;
        end
        centroid = regionprops3(selected, 'Centroid');
        centroid = int16(centroid.Centroid);
        for row = 1:size(centroid, 1)
            x = centroid(row, 1);
            y = centroid(row, 2);
            z = centroid(row, 3);
            intensity = image(y, x, z);
            locations = [locations; x, y, z, intensity, intensity_threshold * 255, channel]; %#ok<AGROW>
        end
    end
end
