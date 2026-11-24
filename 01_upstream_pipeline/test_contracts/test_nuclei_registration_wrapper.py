"""Synthetic entry-point contracts for DAPI-only nuclei registration."""

import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "02_FovIntegration" / "11a_nuclei_registration.sh"


def test_new_entrypoint_help_is_runtime_free(tmp_path):
    assert not (WRAPPER.parent / "11_nuclei_registration.sh").exists()
    result = subprocess.run(
        ["bash", str(WRAPPER), "--help"],
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "11a_nuclei_registration.sh" in result.stdout
    assert "--apply_and_save_images" in result.stdout
    assert "--ref_input_format" in result.stdout
    assert "--moving_input_format" in result.stdout
    assert "--norm_out_format" in result.stdout
    assert "--input_format" not in result.stdout
    assert "STATUS:" not in result.stdout + result.stderr
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "image_option,matlab_value,formats,expected_formats",
    [
        (None, "false", (), ("uint16", "uint16", "uint16")),
        ("TrUe", "true", ("--moving_input_format", "uint8"), ("uint16", "uint8", "uint16")),
        (None, "false", ("--moving_input_format", "uint8", "--norm_out_format", "uint8"),
         ("uint16", "uint8", "uint8")),
    ],
)
def test_offset_round_formats_and_single_image_switch(
    tmp_path, image_option, matlab_value, formats, expected_formats,
):
    result, capture, log_file, image_dir = run_wrapper(tmp_path, image_option, options=formats)
    assert result.returncode == 0, result.stdout + result.stderr
    expression = capture.read_text()
    assert "'Position010'" in expression
    assert "'apply_and_save_images', " + matlab_value in expression
    assert "'aligned_round_outdir', 'A_Fiji/IF'" in expression
    for option, value in zip(("ref_input_format", "moving_input_format", "norm_out_format"), expected_formats):
        assert f"'{option}', '{value}'" in expression
    assert "'channel_panel', {'561-CA9', '488-CD144', '647-CD31', 'DAPI'}" in expression
    assert "POSITION_NAME=Position010" in result.stdout
    assert str(log_file) in result.stdout
    assert "STATUS: SUCCESS" in result.stdout
    if matlab_value == "false":
        assert not image_dir.exists()


def test_matlab_failure_is_reported(tmp_path):
    result, _, log_file, _ = run_wrapper(tmp_path, fail=True, old_log="previous completed shift\n")
    assert result.returncode != 0
    assert "STATUS: FAILED" in result.stdout
    assert log_file.read_text() == "previous completed shift\n"


def test_11a_rejects_the_removed_shared_input_format(tmp_path):
    result, capture, _, _ = run_wrapper(tmp_path, options=("--input_format", "uint16"))
    assert result.returncode != 0
    assert not capture.exists()


def run_wrapper(tmp_path, image_option=None, fail=False, options=(), old_log=None):
    project = tmp_path / "project"
    sample = project / "Sample"
    for position in ("Position010", "Position002"):
        for round_name in ("round001", "round005", "IF"):
            (sample / "01_data" / round_name / position).mkdir(parents=True)
    log_file = sample / "02_registration_case" / "Position010" / "log" / "log_protein_registration_ref-round005_moving-IF.txt"
    if old_log is not None:
        log_file.parent.mkdir(parents=True)
        log_file.write_text(old_log)
    capture = tmp_path / "matlab_expression.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_matlab = fake_bin / "matlab"
    fake_matlab.write_text("#!/usr/bin/env python3\nimport os, sys\nfrom pathlib import Path\nPath(os.environ['NUCLEI_CAPTURE']).write_text(sys.argv[-1])\nif os.environ['NUCLEI_FAIL'] == 'true':\n    raise SystemExit(9)\npath = Path(os.environ['NUCLEI_LOG'])\npath.parent.mkdir(parents=True, exist_ok=True)\npath.write_text('Shifted by -2 3 -1' + chr(10))\nprint('Protein registration log saved: ' + str(path))\n")
    fake_matlab.chmod(0o755)
    fake_module = fake_bin / "module"
    fake_module.write_text('#!/bin/bash\nexit 0\n')
    fake_module.chmod(0o755)
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.startswith("BASH_FUNC_module"):
            environment.pop(key)
    environment.update({
        "PATH": str(fake_bin) + os.pathsep + environment["PATH"],
        "NUCLEI_CAPTURE": str(capture),
        "NUCLEI_LOG": str(log_file),
        "NUCLEI_FAIL": "true" if fail else "false",
        "SLURM_ARRAY_TASK_ID": "1",
        "SLURMD_NODENAME": "test",
    })
    for name in (
        "JOB_ID", "JOB_NAME", "JOB_USER", "SUBMIT_HOST", "SUBMIT_DIR",
        "NODELIST", "JOB_NUM_NODES", "JOB_PARTITION", "CPUS_PER_TASK",
        "JOB_CPUS_PER_NODE",
    ):
        environment["SLURM_" + name] = "test"
    command = [
        "bash", str(WRAPPER), "--project_root", str(project),
        "--project_name", "Sample", "--reg_dir_suffix", "_case",
        "--core_matlab_dir", str(tmp_path / "matlab source"),
        "--offset", "1", "--ref_round", "5",
        "--aligned_round_outdir", "A_Fiji/IF", "--channel_panel", "LeicaIF",
    ]
    if image_option is not None:
        command.extend(("--apply_and_save_images", image_option))
    command.extend(options)
    result = subprocess.run(command, env=environment, capture_output=True, text=True)
    return result, capture, log_file, sample / "02_registration_case" / "A_Fiji"
