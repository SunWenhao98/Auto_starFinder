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
    assert "STATUS:" not in result.stdout + result.stderr
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("image_option,matlab_value", [(None, "false"), ("TrUe", "true")])
def test_offset_log_tag_and_single_image_switch(tmp_path, image_option, matlab_value):
    result, capture, log_file, image_dir = run_wrapper(tmp_path, image_option)
    assert result.returncode == 0, result.stdout + result.stderr
    expression = capture.read_text()
    assert "'Position010'" in expression
    assert "'apply_and_save_images', " + matlab_value in expression
    assert "'aligned_round_outdir', 'A_Fiji/IF'" in expression
    assert "'input_format', 'uint16', 'norm_out_format', 'uint8'" in expression
    assert "'channel_panel', {'561-CA9', '488-CD144', '647-CD31', 'DAPI'}" in expression
    assert "POSITION_NAME=Position010" in result.stdout
    assert str(log_file) in result.stdout
    assert "STATUS: SUCCESS" in result.stdout
    assert not image_dir.exists()


def test_matlab_failure_is_reported(tmp_path):
    result, _, log_file, _ = run_wrapper(tmp_path, fail=True)
    assert result.returncode != 0
    assert "STATUS: FAILED" in result.stdout
    assert not log_file.exists()


def run_wrapper(tmp_path, image_option=None, fail=False):
    project = tmp_path / "project"
    sample = project / "Sample"
    for position in ("Position010", "Position002"):
        (sample / "01_data" / "round001" / position).mkdir(parents=True)
    log_file = sample / "02_registration_case" / "Position010" / "log" / "log_protein_registration_A_Fiji_IF.txt"
    capture = tmp_path / "matlab_expression.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_matlab = fake_bin / "matlab"
    fake_matlab.write_text("#!/usr/bin/env python3\nimport os, sys\nfrom pathlib import Path\nPath(os.environ['NUCLEI_CAPTURE']).write_text(sys.argv[-1])\nif os.environ['NUCLEI_FAIL'] == 'true':\n    raise SystemExit(9)\npath = Path(os.environ['NUCLEI_LOG'])\npath.parent.mkdir(parents=True, exist_ok=True)\npath.write_text('Shifted by -2 3 -1' + chr(10))\n")
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
    result = subprocess.run(command, env=environment, capture_output=True, text=True)
    return result, capture, log_file, sample / "02_registration_case" / "A_Fiji"
