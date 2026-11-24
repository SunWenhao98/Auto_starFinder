function test_nuclei_registration_contracts(output_root)
% Exercise DAPI-only registration and explicit image output on small images.
    assert(~isfolder(output_root) && ~isfile(output_root));
    mkdir(output_root);
    rng(1729, 'twister');
    for depth = [1, 5]
        sample = sprintf('SyntheticZ%d', depth);
        source_dir = fullfile(output_root, sample, '01_data');
        tile = 'Position001';
        ref_dir = fullfile(source_dir, 'round005', tile);
        moving_dir = fullfile(source_dir, 'IF', tile);
        mkdir(ref_dir);
        mkdir(moving_dir);
        native8 = uint8(randi([1, 100], [16, 16, depth]));
        fixed = uint16(native8) .* uint16(257);
        displacement = [2, -3, 1];
        if depth == 1
            displacement(3) = 0;
        end
        moving = circshift(native8, displacement);
        write_tiff(fullfile(ref_dir, 'synthetic_ch03.tif'), fixed);
        write_tiff(fullfile(moving_dir, 'synthetic_ch03.tif'), moving);
        fixed8 = im2uint8(fixed);
        moving8 = moving;
        if depth == 1
            expected = DFTRegister2D(fixed, uint16(moving), false);
        else
            expected = DFTRegister3D(fixed, uint16(moving), false);
        end
        assert(isequal(expected.shifts, -displacement(1:numel(expected.shifts))));

        % The default path succeeds with only two DAPI input TIFFs.
        core_matlab_new(sample, 'nuclei_protein_registration', tile, 16, depth, 5, 3, 11, ...
            output_root, '01_data', '02_registration_shifts', 'log', ...
            'moving_round', 'IF', 'aligned_round_outdir', 'A_Fiji/IF', ...
            'ref_input_format', 'uint16', 'moving_input_format', 'uint8', 'norm_out_format', 'uint16', ...
            'channel_panel', {'561-CA9', '488-CD144', '647-CD31', 'DAPI'});
        shifts_root = fullfile(output_root, sample, '02_registration_shifts');
        log_path = fullfile(shifts_root, tile, 'log', 'log_protein_registration_ref-round005_moving-IF.txt');
        log_text = fileread(log_path);
        token = regexp(log_text, 'Shifted by\s+([^\r\n]+)', 'tokens', 'once');
        actual_shifts = sscanf(token{1}, '%f')';
        assert(isequal(actual_shifts, expected.shifts));
        assert(~isfolder(fullfile(shifts_root, 'A_Fiji')));
        assert(isempty(dir(fullfile(shifts_root, '**', '*.tif'))));
        % The same round pair replaces its old log, independently of method layout.
        write_text(log_path, 'previous completed registration');
        core_matlab_new(sample, 'nuclei_protein_registration', tile, 16, depth, 5, 3, 11, ...
            output_root, '01_data', '02_registration_shifts', 'log', ...
            'moving_round', 'IF', 'aligned_round_outdir', 'A_Ashlar/IF', ...
            'ref_input_format', 'uint16', 'moving_input_format', 'uint8', 'norm_out_format', 'uint16', ...
            'channel_panel', {'561-CA9', '488-CD144', '647-CD31', 'DAPI'});
        log_text = fileread(log_path);
        token = regexp(log_text, 'Shifted by\s+([^\r\n]+)', 'tokens', 'once');
        assert(isequal(sscanf(token{1}, '%f')', expected.shifts));
        assert(~contains(log_text, 'previous completed registration'));
        assert(numel(dir(fullfile(shifts_root, tile, 'log', 'log_protein_registration_*.txt'))) == 1);

        % A failure after opening the registration path keeps the completed log.
        moving_dapi = fullfile(moving_dir, 'synthetic_ch03.tif');
        held_dapi = [moving_dapi, '.held'];
        movefile(moving_dapi, held_dapi);
        restore_dapi = onCleanup(@() movefile(held_dapi, moving_dapi));
        expect_failure(@() core_matlab_new(sample, 'nuclei_protein_registration', tile, 16, depth, 5, 3, 11, ...
            output_root, '01_data', '02_registration_shifts', 'log', ...
            'moving_round', 'IF', 'aligned_round_outdir', 'A_Fiji/IF', ...
            'ref_input_format', 'uint16', 'moving_input_format', 'uint8', 'norm_out_format', 'uint16', ...
            'channel_panel', {'561-CA9', '488-CD144', '647-CD31', 'DAPI'}));
        clear restore_dapi;
        assert(strcmp(fileread(log_path), log_text));

        % Explicit output preserves the original per-channel transforms and dtype.
        channel_names = {'561-CA9', '488-CD144', '647-CD31', 'DAPI', 'ref-DAPI'};
        moving_channels = cell(1, 4);
        for channel = 1:3
            moving_channels{channel} = uint8(randi([1, 100], [16, 16, depth]));
            write_tiff(fullfile(moving_dir, sprintf('synthetic_ch%02d.tif', channel - 1)), moving_channels{channel});
        end
        moving_channels{4} = moving;
        panel = channel_names(1:4);
        if depth == 5
            panel = panel';
        end
        core_matlab_new(sample, 'nuclei_protein_registration', tile, 16, depth, 5, 3, 11, ...
            output_root, '01_data', '02_registration_images', 'log', ...
            'moving_round', 'IF', 'aligned_round_outdir', 'A_Fiji/IF', ...
            'ref_input_format', 'uint16', 'moving_input_format', 'uint8', 'norm_out_format', 'uint16', ...
            'channel_panel', panel, 'apply_and_save_images', true);
        images_root = fullfile(output_root, sample, '02_registration_images', 'A_Fiji', 'IF');
        for channel = 1:4
            if depth == 1
                aligned = DFTApply2D(uint16(moving_channels{channel}), expected, false);
            else
                aligned = DFTApply3D(uint16(moving_channels{channel}), expected, false);
            end
            image_path = fullfile(images_root, channel_names{channel}, [tile, '.tif']);
            image_info = imfinfo(image_path);
            assert(all([image_info.BitDepth] == 16));
            actual = new_LoadMultipageTiff(image_path, ...
                'uint16', 'uint16', false);
            assert(isequal(actual, uint16(aligned)));
        end
        actual_ref = new_LoadMultipageTiff(fullfile(images_root, 'ref-DAPI', [tile, '.tif']), 'uint16', 'uint16', false);
        assert(isequal(actual_ref, fixed));
        assert(numel(dir(fullfile(images_root, '**', '*.tif'))) == 5);

        % Explicit uint8 remains available, with each input converted from its own dtype.
        if depth == 1
            expected8 = DFTRegister2D(fixed8, moving8, false);
        else
            expected8 = DFTRegister3D(fixed8, moving8, false);
        end
        core_matlab_new(sample, 'nuclei_protein_registration', tile, 16, depth, 5, 3, 11, ...
            output_root, '01_data', '02_registration_legacy8', 'log', ...
            'moving_round', 'IF', 'aligned_round_outdir', 'A_Fiji/IF', ...
            'ref_input_format', 'uint16', 'moving_input_format', 'uint8', 'norm_out_format', 'uint8', ...
            'channel_panel', panel, 'apply_and_save_images', true);
        legacy_image = fullfile(output_root, sample, '02_registration_legacy8', 'A_Fiji', 'IF', 'DAPI', [tile, '.tif']);
        legacy_info = imfinfo(legacy_image);
        assert(all([legacy_info.BitDepth] == 8));
        legacy_actual = new_LoadMultipageTiff(legacy_image, 'uint8', 'uint8', false);
        if depth == 1
            legacy_expected = DFTApply2D(moving8, expected8, false);
        else
            legacy_expected = DFTApply3D(moving8, expected8, false);
        end
        assert(isequal(legacy_actual, uint8(legacy_expected)));
        legacy_ref = fullfile(output_root, sample, '02_registration_legacy8', 'A_Fiji', 'IF', 'ref-DAPI', [tile, '.tif']);
        assert(isequal(new_LoadMultipageTiff(legacy_ref, 'uint8', 'uint8', false), fixed8));

        % An existing output from this FOV is protected before opening a new log.
        protected_root = fullfile(output_root, sample, '02_registration_protected');
        protected = fullfile(protected_root, 'A_Fiji', 'IF', channel_names{1}, [tile, '.tif']);
        mkdir(fileparts(protected));
        write_tiff(protected, uint8(17 * ones(16, 16, depth)));
        expect_failure(@() core_matlab_new(sample, 'nuclei_protein_registration', tile, 16, depth, 5, 3, 11, ...
            output_root, '01_data', '02_registration_protected', 'log', ...
            'moving_round', 'IF', 'aligned_round_outdir', 'A_Fiji/IF', ...
            'channel_panel', channel_names(1:4), 'apply_and_save_images', true));
        protected_image = new_LoadMultipageTiff(protected, 'uint8', 'uint8', false);
        assert(all(protected_image == 17, 'all'));
        assert(~isfile(fullfile(protected_root, tile, 'log', 'log_protein_registration_ref-round005_moving-IF.txt')));

        % A channel directory link would redirect SaveCellImg into the original input.
        linked_root = fullfile(output_root, sample, '02_registration_linked');
        linked_dir = fullfile(linked_root, 'A_Fiji', 'IF', 'ref-DAPI');
        mkdir(fileparts(linked_dir));
        link_file = java.io.File(linked_dir);
        source_file = java.io.File(ref_dir);
        java.nio.file.Files.createSymbolicLink(link_file.toPath(), source_file.toPath(), ...
            javaArray('java.nio.file.attribute.FileAttribute', 0));
        expect_failure(@() core_matlab_new(sample, 'nuclei_protein_registration', tile, 16, depth, 5, 3, 11, ...
            output_root, '01_data', '02_registration_linked', 'log', ...
            'moving_round', 'IF', 'aligned_round_outdir', 'A_Fiji/IF', ...
            'channel_panel', channel_names(1:4), 'apply_and_save_images', true));
        assert(~isfile(fullfile(ref_dir, [tile, '.tif'])));
        assert(~isfile(fullfile(linked_root, tile, 'log', 'log_protein_registration_ref-round005_moving-IF.txt')));

        % A linked method parent must be rejected before its missing IF directory is created.
        intermediate_root = fullfile(output_root, sample, '02_registration_intermediate');
        method_link = fullfile(intermediate_root, 'A_Fiji');
        original_target = fullfile(source_dir, 'guard_target');
        mkdir(intermediate_root);
        mkdir(original_target);
        method_file = java.io.File(method_link);
        original_file = java.io.File(original_target);
        java.nio.file.Files.createSymbolicLink(method_file.toPath(), original_file.toPath(), ...
            javaArray('java.nio.file.attribute.FileAttribute', 0));
        expect_failure(@() core_matlab_new(sample, 'nuclei_protein_registration', tile, 16, depth, 5, 3, 11, ...
            output_root, '01_data', '02_registration_intermediate', 'log', ...
            'moving_round', 'IF', 'aligned_round_outdir', 'A_Fiji/IF', ...
            'channel_panel', panel, 'apply_and_save_images', true));
        assert(~isfolder(fullfile(original_target, 'IF')));
        assert(~isfile(fullfile(intermediate_root, tile, 'log', 'log_protein_registration_ref-round005_moving-IF.txt')));
    end
    fprintf('STATUS: SUCCESS | test_nuclei_registration_contracts\n');
end

function write_tiff(path, image)
    for index = 1:size(image, 3)
        imwrite(image(:, :, index), path, 'WriteMode', 'append');
    end
end

function expect_failure(call)
    failed = false;
    try
        call();
    catch
        failed = true;
    end
    assert(failed);
end

function write_text(path, text)
    handle = fopen(path, 'w');
    cleanup = onCleanup(@() fclose(handle));
    fprintf(handle, '%s\n', text);
end
