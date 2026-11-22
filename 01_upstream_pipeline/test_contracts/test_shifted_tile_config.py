"""Coordinate-only contracts for step 23 and the new registration entry points."""

import configparser
import csv
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "02_FovIntegration" / "p23_prepare_moveImages_tileconfig.py"
spec = importlib.util.spec_from_file_location("shifted_tile_config", RUNNER)
shifted = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shifted)


def inputs(tmp_path):
    work = tmp_path / "method"
    work.mkdir()
    reference = work / "reference.txt"
    reference.write_text("dim = 3\nPosition002.tif; ; (100, 200, 3)\nPosition001.tif; ; (0, 0, 0)\n")
    registration = tmp_path / "registration"
    for position in ("Position001", "Position002", "Position003"):
        log = registration / position / "log"
        log.mkdir(parents=True)
        (log / "IF.txt").write_text("Shifted by 1 2 0\nShifted by 39 53 -6\n")
        (log / "seqE.txt").write_text("Shifted by -2 7\n")
    return work, reference, registration


def execute(work, reference, registration, output, log="IF.txt", extra=()):
    return subprocess.run(
        [
            sys.executable, "-B", str(RUNNER),
            "--work_dir", str(work),
            "--registered_config", str(reference),
            "--registration_dir", str(registration),
            "--registration_log_name", log,
            "--shifted_config_name", output,
            *extra,
        ],
        capture_output=True, text=True, timeout=20,
    )


@pytest.mark.parametrize(
    ("extra", "first"),
    [
        ((), (153, 239, -3)),
        (("--shift_sign", "-1"), (47, 161, 9)),
        (("--rotate90",), (61, 253, -3)),
    ],
)
def test_shifts_update_coordinates_without_raw_images(tmp_path, extra, first):
    work, reference, registration = inputs(tmp_path)
    result = execute(work, reference, registration, "IF.moving.txt", extra=extra)
    assert result.returncode == 0, result.stdout + result.stderr
    records = shifted.parse_tile_config(work / "IF.moving.txt")
    assert [row["position"] for row in records] == ["Position002", "Position001"]
    assert tuple(records[0][axis] for axis in ("x", "y", "z")) == first
    with (work / "IF.moving.shifts.csv").open() as handle:
        shifts = list(csv.DictReader(handle))
    assert [row["position"] for row in shifts] == ["Position002", "Position001"]
    assert float(shifts[0]["moving_x"]) == first[0]
    assert not list(work.glob("raw-*"))
    assert not (tmp_path / "01_data").exists()


def test_if_and_seqe_use_independent_logs_and_output_names(tmp_path):
    work, reference, registration = inputs(tmp_path)
    for log, name in (("IF.txt", "IF.moving.txt"), ("seqE.txt", "seqE.moving.txt")):
        result = execute(work, reference, registration, name, log=log)
        assert result.returncode == 0, result.stderr
    seqe = shifted.parse_tile_config(work / "seqE.moving.txt")
    assert tuple(seqe[0][axis] for axis in ("x", "y", "z")) == (107, 198, 3)
    assert (work / "IF.moving.shifts.csv").is_file()
    assert (work / "seqE.moving.shifts.csv").is_file()


@pytest.mark.parametrize("existing", ["IF.moving.txt", "IF.moving.shifts.csv"])
def test_existing_output_is_preserved(tmp_path, existing):
    work, reference, registration = inputs(tmp_path)
    protected = work / existing
    protected.write_bytes(b"keep")
    result = execute(work, reference, registration, "IF.moving.txt")
    assert result.returncode != 0
    assert protected.read_bytes() == b"keep"


def test_missing_shift_does_not_publish_coordinates(tmp_path):
    work, reference, registration = inputs(tmp_path)
    result = execute(work, reference, registration, "IF.moving.txt", log="missing.txt")
    assert result.returncode != 0
    assert not (work / "IF.moving.txt").exists()
    assert not (work / "IF.moving.shifts.csv").exists()


def test_removed_image_options_are_rejected(tmp_path):
    work, reference, registration = inputs(tmp_path)
    result = execute(
        work, reference, registration, "IF.moving.txt",
        extra=("--raw_round_dir", str(tmp_path), "--channel_names", "DAPI"),
    )
    assert result.returncode != 0
    help_result = subprocess.run(
        [sys.executable, "-B", str(RUNNER), "--help"], capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": ""}, timeout=10,
    )
    assert help_result.returncode == 0
    for option in ("--raw_round_dir", "--channel_names", "--output_format"):
        assert option not in help_result.stdout


def test_new_default_config_uses_renamed_entries_and_raw_reference():
    config = configparser.ConfigParser(inline_comment_prefixes=(";",))
    config.read(ROOT / "batch_config.upstream.ini")
    values = config["DEFAULT"]
    assert values["script_nuclei_registration"].endswith("/11a_nuclei_registration.sh")
    assert values["script_prepare_layout"].endswith("/11b_prepare_layout.sh")
    assert not values.getboolean("nuclei_reg_apply_and_save_images")
    assert values["prepare_layout_mode"] == "symlink"
    assert values["prepare_layout_output_format"] == "preserve"
    assert values["prepare_tile_config_source_channel_dir"] == "raw-refDAPI"
    assert values["fiji_stitch_initial_source_channel"] == "raw-refDAPI"
    for name in ("11_nuclei_registration.sh", "21_prepare_layout.sh", "p21_prepare_noRef_layout.py"):
        assert not (ROOT / "02_FovIntegration" / name).exists()


def test_three_round_layout_and_shift_wrapper_chain(tmp_path):
    sample = tmp_path / "Sample"
    for round_name, channels in (("round001", (3,)), ("IF", range(4)), ("round011", range(4))):
        position = sample / "01_data" / round_name / "Position003"
        position.mkdir(parents=True)
        for channel in channels:
            (position / f"source_ch{channel:02d}.tif").write_bytes(b"source pixels")
    manifest = tmp_path / "rounds.csv"
    manifest.write_text(
        "role,rawdata_round,channel_mode,subdir\n"
        "ref,round001,LeicaRef,ref\n"
        "IF,IF,LeicaIF,IF\n"
        "seqE,round011,LeicaSeqE,seqE\n"
    )
    conda = tmp_path / "conda.sh"
    conda.write_text("conda() { :; }\n")
    environment = {
        **os.environ,
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        "SLURMD_NODENAME": "test",
    }
    for name in ("JOB_ID", "JOB_NAME", "JOB_USER", "SUBMIT_HOST", "SUBMIT_DIR",
                 "NODELIST", "JOB_NUM_NODES", "JOB_PARTITION", "CPUS_PER_TASK",
                 "JOB_CPUS_PER_NODE"):
        environment["SLURM_" + name] = "test"
    common = [
        "--project_root", str(tmp_path), "--project_name", "Sample",
        "--reg_dir_suffix", "_new", "--script_dir", str(RUNNER.parent),
        "--conda_sh", str(conda), "--stitching_workdir", "A_Fiji",
    ]
    layout = subprocess.run(
        ["bash", str(RUNNER.parent / "11b_prepare_layout.sh"), *common,
         "--round_manifest", str(manifest)],
        env=environment, capture_output=True, text=True, timeout=30,
    )
    assert layout.returncode == 0, layout.stdout + layout.stderr
    registration = sample / "02_registration_new"
    method = registration / "A_Fiji"
    links = list(method.rglob("Position*.tif"))
    assert len(links) == 9
    targets = {path: path.resolve(strict=True) for path in links}
    assert all(path.is_symlink() for path in links)
    reference = method / "reference.txt"
    reference.write_text("dim = 3\nPosition003.tif; ; (100, 200, 0)\n")
    logs = registration / "Position003" / "log"
    logs.mkdir(parents=True)
    for role, shift in (("IF", "39 53 -6"), ("seqE", "-2 7 0")):
        log_name = f"log_protein_registration_{role}.txt"
        (logs / log_name).write_text(f"Shifted by {shift}\n")
        result = subprocess.run(
            ["bash", str(RUNNER.parent / "23_prepare_moveImages_tileconfig.sh"), *common,
             "--registration_log_name", log_name, "--input_config", reference.name,
             "--output_config", f"{role}.moving.txt"],
            env=environment, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert (method / f"{role}.moving.shifts.csv").is_file()
    assert {path: path.resolve(strict=True) for path in links} == targets
    assert all(path.read_bytes() == b"source pixels" for path in targets.values())


def test_generator_forwards_new_semantic_options(tmp_path):
    config = configparser.ConfigParser()
    config.read(ROOT / "batch_config.upstream.ini")
    for section in config.sections():
        config.remove_section(section)
    for key in tuple(config.defaults()):
        if key.startswith("run_"):
            config["DEFAULT"][key] = "false"
    config["DEFAULT"].update({
        "samples": '{"Sample": 1}',
        "fovIntegration": str(ROOT / "02_FovIntegration"),
        "stitch_log": str(tmp_path / "logs"),
        "run_nuclei_registration": "true",
        "run_prepare_layout": "true",
        "run_prepare_moveimages": "true",
        "nuclei_reg_aligned_round_outdir": "IF_ref001",
        "prepare_layout_round_manifest": str(tmp_path / "rounds.csv"),
        "prepare_moveimages_registration_log_name": "log_protein_registration_IF_ref001.txt",
    })
    config["JOB_TEST"] = {
        "project_name": "Sample", "regDir_suffix": "_new", "job_suffix": "test",
    }
    ini = tmp_path / "full.ini"
    with ini.open("x") as handle:
        config.write(handle)
    output = tmp_path / "submit.sh"
    generated = subprocess.run(
        [sys.executable, "-B", str(ROOT / "generator_upstream_pipeline.py"),
         "--config", str(ini), "--output", str(output)],
        capture_output=True, text=True, timeout=20,
    )
    assert generated.returncode == 0, generated.stderr
    script = output.read_text()
    assert script.index("11a_nuclei_registration.sh") < script.index("11b_prepare_layout.sh")
    assert script.index("11b_prepare_layout.sh") < script.index("23_prepare_moveImages_tileconfig.sh")
    assert "--apply_and_save_images false" in script
    assert "--layout_mode symlink" in script
    assert "--round_manifest" in script
    assert "--registration_log_name log_protein_registration_IF_ref001.txt" in script
    subprocess.run(["bash", "-n", str(output)], check=True)
