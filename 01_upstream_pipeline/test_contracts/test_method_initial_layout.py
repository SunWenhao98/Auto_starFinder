"""A method owns one MAF coordinate source; rounds consume relative file links."""

import csv
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest


PIPELINE = Path(__file__).resolve().parents[1]
FOV = PIPELINE / "02_FovIntegration"


@pytest.fixture
def layout_inputs(tmp_path):
    sample = tmp_path / "Sample"
    registration = sample / "02_registration_test"
    manifest = tmp_path / "rounds with spaces.csv"
    with manifest.open("x", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["role", "rawdata_round", "channel_mode", "subdir"])
        writer.writerows([
            ("ref", "round001", "LeicaRef", "ref"),
            ("IF", "IF", "LeicaIF", "IF"),
            ("seqE", "round011", "LeicaSeqE", "seqE"),
        ])
    for round_name in ("round001", "IF", "round011"):
        for position in (1, 2):
            (sample / "01_data" / round_name / f"Position{position:03d}").mkdir(parents=True)
    maf = tmp_path / "positions.maf"
    maf.write_text(
        '<MAF><XYZStagePointDefinition StageXPos="0.001" StageYPos="0.002"/>'
        '<XYZStagePointDefinition StageXPos="0.00101" StageYPos="0.00202"/></MAF>'
    )
    conda = tmp_path / "conda.sh"
    conda.write_text("conda() { :; }\n")
    environment = os.environ.copy()
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment["PATH"]
    environment["MPLBACKEND"] = "Agg"
    environment["MPLCONFIGDIR"] = str(tmp_path / "matplotlib")
    environment.update({f"SLURM_{key}": "test" for key in (
        "JOB_ID", "JOB_NAME", "JOB_USER", "SUBMIT_HOST", "SUBMIT_DIR", "NODELIST",
        "JOB_NUM_NODES", "JOB_PARTITION", "CPUS_PER_TASK", "JOB_CPUS_PER_NODE",
    )})
    environment["SLURMD_NODENAME"] = "test"
    return tmp_path, registration, manifest, maf, conda, environment


@pytest.fixture
def position_id_layout_inputs(layout_inputs):
    root, _, _, maf, *_ = layout_inputs
    for round_name in ("round001", "IF", "round011"):
        raw_round = root / "Sample/01_data" / round_name
        for old, new in ((1, 3), (2, 7)):
            (raw_round / f"Position{old:03d}").rename(raw_round / f"Position{new:03d}")
    # Keep original board IDs while deliberately changing the XML element order.
    board_ids = [17, 2, 13, 1, *(value for value in range(1, 19) if value not in (17, 2, 13, 1))]
    maf.write_text("<MAF>" + "".join(
        f'<XYZStagePointDefinition PositionID="{value}" '
        f'StageXPos="{0.001 + value * 0.00001:.8f}" '
        f'StageYPos="{0.002 + value * 0.00002:.8f}"/>'
        for value in board_ids
    ) + "</MAF>")
    return layout_inputs


def run_initial(inputs, method, source_channel_dir="ref/raw-refDAPI", *,
                positions=(2, 1), position_offset=0, maf_match_mode=None):
    root, registration, manifest, maf, conda, environment = inputs
    work = registration / method
    for role in ("ref", "IF", "seqE"):
        (work / role).mkdir(parents=True, exist_ok=True)
    source = work / source_channel_dir
    source.mkdir(exist_ok=True)
    # Step 12 enumerates acquisition names and MAF metadata, not TIFF pixels.
    for position in positions:
        (source / f"Position{position:03d}.tif").write_bytes(b"synthetic acquisition name")
    match_args = [] if maf_match_mode is None else ["--maf_match_mode", maf_match_mode]
    result = subprocess.run(
        ["bash", str(FOV / "12_prepare_tile_config.sh"),
         "--project_root", str(root), "--project_name", "Sample",
         "--reg_dir_suffix", "_test", "--stitching_workdir", method,
         "--source_channel_dir", source_channel_dir, "--match_string", "Position",
         "--pixel_size_um", "1", "--image_xy", "16", "--overlap_ratio", "0.1",
         "--output_config", "TileConfiguration.initial.txt",
         "--maf_file", str(maf), "--position_offset", str(position_offset), *match_args,
         "--round_manifest", str(manifest), "--script_dir", str(FOV),
         "--conda_sh", str(conda)],
        env=environment, capture_output=True, text=True, timeout=60,
    )
    return work, result


def coordinate_rows(path):
    pattern = re.compile(r"(Position\d+\.tif)\s*;\s*;\s*\(([^)]+)\)")
    return [
        (match.group(1), tuple(float(value) for value in match.group(2).split(",")))
        for line in path.read_text().splitlines()
        if (match := pattern.fullmatch(line.strip()))
    ]


def test_one_method_initial_source_and_real_consumers(layout_inputs):
    initial_files = []
    for method in ("A_Fiji", "A_Ashlar"):
        work, result = run_initial(layout_inputs, method)
        assert result.returncode == 0, result.stdout + result.stderr
        initial = work / "TileConfiguration.initial.txt"
        summary = work / "tile_summary.csv"
        initial_files.append(initial)
        assert initial.is_file() and not initial.is_symlink()
        assert not (work / "TileConfiguration.txt").exists()
        assert coordinate_rows(initial) == [
            ("Position001.tif", (0.0, 0.0, 0.0)),
            ("Position002.tif", (10.0, 20.0, 0.0)),
        ]
        with summary.open() as handle:
            rows = list(csv.DictReader(handle))
        assert [int(row["real_id"]) for row in rows] == [1, 2]
        assert [float(row["center_x_px"]) for row in rows] == pytest.approx([8, 18])
        assert [float(row["center_y_px"]) for row in rows] == pytest.approx([8, 28])
        assert json.loads((work / "fiji_fusion_preflight.json").read_text())["fiji_fusion_safe"]
        assert (work / "tile_layout_leica.png").is_file()
        assert (work / "tile_centers_distribution_leica.png").is_file()
        for role in ("ref", "IF", "seqE"):
            for source in (initial, summary):
                link = work / role / source.name
                assert link.is_symlink()
                assert not os.path.isabs(os.readlink(link))
                assert link.resolve(strict=True) == source
                assert link.read_bytes() == source.read_bytes()
        assert len(list(work.rglob("TileConfiguration.initial.txt"))) == 4
    assert not os.path.samefile(*initial_files)

    root, registration, _, _, _, environment = layout_inputs
    work = registration / "A_Fiji"
    initial = work / "TileConfiguration.initial.txt"
    before = initial.read_bytes()
    fiji = root / "Fiji"
    fiji.mkdir()
    executable = fiji / "ImageJ-linux64"
    executable.write_text(
        '#!/bin/bash\nset -euo pipefail\n'
        'cp "$INPUT_DIR/$LAYOUT_FILE" "$INPUT_DIR/TileConfiguration.registered.txt"\n'
        'printf "synthetic rendered image" > "$OUTPUT_DIRECTORY/${OUTPUT_NAME}_2d_Fiji.ome.tif"\n'
    )
    executable.chmod(0o755)
    result = subprocess.run(
        ["bash", str(FOV / "15_fiji_stitch_initial.sh"),
         "--project_root", str(root), "--project_name", "Sample",
         "--reg_dir_suffix", "_test", "--stitching_workdir", "A_Fiji/ref",
         "--source_channel", "raw-refDAPI", "--input_config", initial.name,
         "--output_config", "TileConfiguration.registered.round001.Fiji.txt",
         "--output_name", "DAPI", "--save_format", "ome_tiff",
         "--script_dir", str(FOV), "--fiji_dir", str(fiji)],
        env=environment, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    registered = work / "ref/TileConfiguration.registered.round001.Fiji.txt"
    assert registered.is_file() and not registered.is_symlink()
    for position in ("Position001", "Position002"):
        logs = registration / position / "log"
        logs.mkdir(parents=True)
        (logs / "IF.txt").write_text("Shifted by 3 4 0\n")
    moving_name = "IF/TileConfiguration.moving.IF.Fiji.txt"
    result = subprocess.run(
        [sys.executable, "-B", str(FOV / "p23_prepare_moveImages_tileconfig.py"),
         "--work_dir", str(work), "--registered_config", str(registered),
         "--registration_dir", str(registration), "--registration_log_name", "IF.txt",
         "--shifted_config_name", moving_name],
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    moving = work / moving_name
    assert moving.is_file() and not moving.is_symlink()
    assert coordinate_rows(moving) == [
        ("Position001.tif", (4.0, 3.0, 0.0)),
        ("Position002.tif", (14.0, 23.0, 0.0)),
    ]
    assert initial.read_bytes() == before
    assert (work / "IF/TileConfiguration.initial.txt").read_bytes() == before


def test_existing_initial_is_not_overwritten(layout_inputs):
    _, registration, *_ = layout_inputs
    work = registration / "A_Fiji"
    work.mkdir(parents=True)
    protected = work / "TileConfiguration.initial.txt"
    protected.write_bytes(b"preserve an existing coordinate source")
    _, result = run_initial(layout_inputs, "A_Fiji")
    assert result.returncode != 0
    assert protected.read_bytes() == b"preserve an existing coordinate source"


def test_foreign_round_link_is_not_replaced(layout_inputs):
    root, registration, *_ = layout_inputs
    target = registration / "A_Fiji/IF/TileConfiguration.initial.txt"
    target.parent.mkdir(parents=True)
    foreign = root / "different-method-initial.txt"
    foreign.write_bytes(b"preserve another method's source")
    target.symlink_to(foreign)
    _, result = run_initial(layout_inputs, "A_Fiji")
    assert result.returncode != 0
    assert target.is_symlink()
    assert target.resolve(strict=True) == foreign
    assert foreign.read_bytes() == b"preserve another method's source"


@pytest.mark.parametrize("round_coverage", ["extra", "missing_required"])
def test_shared_initial_requires_selected_fovs_but_allows_extra_acquisitions(layout_inputs, round_coverage):
    root, *_ = layout_inputs
    raw_round = root / "Sample/01_data/round011"
    if round_coverage == "extra":
        (raw_round / "Position003").mkdir()
    else:
        (raw_round / "Position002").rename(raw_round / "Position003")
    work, result = run_initial(layout_inputs, "A_Fiji")
    initial = work / "TileConfiguration.initial.txt"
    assert coordinate_rows(initial) == [
        ("Position001.tif", (0.0, 0.0, 0.0)),
        ("Position002.tif", (10.0, 20.0, 0.0)),
    ]
    if round_coverage == "extra":
        assert result.returncode == 0, result.stdout + result.stderr
        assert (work / "seqE/TileConfiguration.initial.txt").resolve(strict=True) == initial
    else:
        assert result.returncode != 0


def test_position_id_matches_offset_plus_nonconsecutive_acquisition_numbers(position_id_layout_inputs):
    work, result = run_initial(
        position_id_layout_inputs, "A_Fiji", positions=(7, 3),
        position_offset=10, maf_match_mode="position_id",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    initial = work / "TileConfiguration.initial.txt"
    assert coordinate_rows(initial) == [
        ("Position003.tif", (0.0, 0.0, 0.0)),
        ("Position007.tif", (40.0, 80.0, 0.0)),
    ]
    with (work / "tile_summary.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert [int(row["real_id"]) for row in rows] == [3, 7]
    assert [float(row["phys_x"]) for row in rows] == pytest.approx([1130, 1170])
    assert [float(row["phys_y"]) for row in rows] == pytest.approx([2260, 2340])
    for role in ("ref", "IF", "seqE"):
        assert (work / role / initial.name).resolve(strict=True) == initial


@pytest.mark.parametrize("replacement_id", [None, 13, 117],
                         ids=["missing_id_attribute", "duplicate_maf_id", "missing_required_maf_id"])
def test_position_id_rejects_missing_or_ambiguous_maf_identity(position_id_layout_inputs, replacement_id):
    _, _, _, maf, *_ = position_id_layout_inputs
    attribute = "" if replacement_id is None else f'PositionID="{replacement_id}"'
    maf.write_text(maf.read_text().replace('PositionID="17"', attribute))
    work, result = run_initial(
        position_id_layout_inputs, "A_Fiji", positions=(7, 3),
        position_offset=10, maf_match_mode="position_id",
    )
    assert result.returncode != 0
    assert not (work / "TileConfiguration.initial.txt").exists()


def test_existing_layout_plot_is_not_overwritten(layout_inputs):
    _, registration, *_ = layout_inputs
    work = registration / "A_Fiji"
    work.mkdir(parents=True)
    protected = work / "tile_layout_leica.png"
    protected.write_bytes(b"preserve an existing layout figure")
    _, result = run_initial(layout_inputs, "A_Fiji")
    assert result.returncode != 0
    assert protected.read_bytes() == b"preserve an existing layout figure"


@pytest.mark.parametrize("original_board_ids", [False, True], ids=["no_position_id", "derived_submaf"])
def test_root_layout_manifest_does_not_link_source_to_itself(layout_inputs, original_board_ids):
    _, _, manifest, *_ = layout_inputs
    if original_board_ids:
        maf = layout_inputs[3]
        maf.write_text(
            '<MAF><XYZStagePointDefinition PositionID="13" StageXPos="0.001" StageYPos="0.002"/>'
            '<XYZStagePointDefinition PositionID="17" StageXPos="0.00101" StageYPos="0.00202"/></MAF>'
        )
    with manifest.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["role", "rawdata_round", "channel_mode", "subdir"])
        writer.writerow(["ref", "round001", "LeicaRef", ""])
    work, result = run_initial(layout_inputs, "A_Fiji", "raw-refDAPI")
    assert result.returncode == 0, result.stdout + result.stderr
    assert coordinate_rows(work / "TileConfiguration.initial.txt") == [
        ("Position001.tif", (0.0, 0.0, 0.0)),
        ("Position002.tif", (10.0, 20.0, 0.0)),
    ]
    for name in ("TileConfiguration.initial.txt", "tile_summary.csv"):
        assert (work / name).is_file()
        assert not (work / name).is_symlink()


def test_vsi_output_collision_propagates_failure_and_stops_vm(tmp_path, monkeypatch):
    # Substitute only the external Java/metadata boundary; execute the real VSI main.
    stopped = []
    monkeypatch.setitem(sys.modules, "bioformats", SimpleNamespace(JARS=[]))
    monkeypatch.setitem(sys.modules, "javabridge", SimpleNamespace(
        start_vm=lambda **kwargs: None,
        static_call=lambda *args: None,
        kill_vm=lambda: stopped.append(True),
    ))
    spec = importlib.util.spec_from_file_location(
        "vsi_layout_test", FOV / "p12_vsi2Stitching_configuration.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "get_vsi_position", lambda path: (10, 20))
    source = tmp_path / "input"
    source.mkdir()
    (source / "C1-1.vsi").touch()
    output = tmp_path / "output"
    output.mkdir()
    initial = output / "TileConfiguration.initial.txt"
    initial.write_text("keep existing coordinates")
    monkeypatch.setattr(sys, "argv", [
        str(FOV / "p12_vsi2Stitching_configuration.py"),
        "--input_dir", str(source), "--output_dir", str(output),
        "--output_config", initial.name,
    ])
    with pytest.raises(FileExistsError):
        module.main()
    assert initial.read_text() == "keep existing coordinates"
    assert stopped == [True]
