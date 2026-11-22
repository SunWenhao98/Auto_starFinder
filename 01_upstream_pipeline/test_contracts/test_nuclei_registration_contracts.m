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
        fixed = uint16(randi([0, 65535], [16, 16, depth]));
        displacement = [2, -3, 1];
        if depth == 1
            displacement(3) = 0;
        end
        moving = circshift(fixed, displacement);
        write_tiff(fullfile(ref_dir, 'synthetic_ch03.tif'), fixed);
        write_tiff(fullfile(moving_dir, 'synthetic_ch03.tif'), moving);
        fixed8 = im2uint8(fixed);
        moving8 = im2uint8(moving);
        if depth == 1
            expected = DFTRegister2D(fixed8, moving8, false);
        else
            expected = DFTRegister3D(fixed8, moving8, false);
        end
        assert(isequal(expected.shifts, -displacement(1:numel(expected.shifts))));

        % The default path succeeds with only two DAPI input TIFFs.
        core_matlab_new(sample, 'nuclei_protein_registration', tile, 16, depth, 5, 3, 11, ...
            output_root, '01_data', '02_registration_shifts', 'log', ...
            'moving_round', 'IF', 'aligned_round_outdir', 'A_Fiji/IF', ...
            'input_format', 'uint16', 'norm_out_format', 'uint8', ...
            'channel_panel', {'561-CA9', '488-CD144', '647-CD31', 'DAPI'});
        shifts_root = fullfile(output_root, sample, '02_registration_shifts');
        log_path = fullfile(shifts_root, tile, 'log', 'log_protein_registration_A_Fiji_IF.txt');
        log_text = fileread(log_path);
        token = regexp(log_text, 'Shifted by\s+([^\r\n]+)', 'tokens', 'once');
        actual_shifts = sscanf(token{1}, '%f')';
        assert(isequal(actual_shifts, expected.shifts));
        assert(~isfolder(fullfile(shifts_root, 'A_Fiji')));
        assert(isempty(dir(fullfile(shifts_root, '**', '*.tif'))));
        expect_failure(@() core_matlab_new(sample, 'nuclei_protein_registration', tile, 16, depth, 5, 3, 11, ...
            output_root, '01_data', '02_registration_shifts', 'log', ...
            'moving_round', 'IF', 'aligned_round_outdir', 'A_Fiji/IF', ...
            'channel_panel', {'561-CA9', '488-CD144', '647-CD31', 'DAPI'}));
        assert(strcmp(fileread(log_path), log_text));

        % Explicit output preserves the original per-channel transforms and dtype.
        channel_names = {'561-CA9', '488-CD144', '647-CD31', 'DAPI', 'ref-DAPI'};
        moving_channels = cell(1, 4);
        for channel = 1:3
            moving_channels{channel} = uint16(randi([0, 65535], [16, 16, depth]));
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
            'input_format', 'uint16', 'norm_out_format', 'uint8', ...
            'channel_panel', panel, 'apply_and_save_images', true);
        images_root = fullfile(output_root, sample, '02_registration_images', 'A_Fiji', 'IF');
        for channel = 1:4
            if depth == 1
                aligned = DFTApply2D(im2uint8(moving_channels{channel}), expected, false);
            else
                aligned = DFTApply3D(im2uint8(moving_channels{channel}), expected, false);
            end
            actual = new_LoadMultipageTiff(fullfile(images_root, channel_names{channel}, [tile, '.tif']), ...
                'uint8', 'uint8', false);
            assert(isequal(actual, uint8(aligned)));
        end
        actual_ref = new_LoadMultipageTiff(fullfile(images_root, 'ref-DAPI', [tile, '.tif']), 'uint8', 'uint8', false);
        assert(isequal(actual_ref, fixed8));
        assert(numel(dir(fullfile(images_root, '**', '*.tif'))) == 5);

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
        assert(~isfile(fullfile(protected_root, tile, 'log', 'log_protein_registration_A_Fiji_IF.txt')));

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
        assert(~isfile(fullfile(linked_root, tile, 'log', 'log_protein_registration_A_Fiji_IF.txt')));

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
        assert(~isfile(fullfile(intermediate_root, tile, 'log', 'log_protein_registration_A_Fiji_IF.txt')));
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
