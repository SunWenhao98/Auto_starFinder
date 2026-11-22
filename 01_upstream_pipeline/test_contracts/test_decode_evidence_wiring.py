"""验证 evidence 开关与 PR 经完整配置、wrapper 实际传入 MATLAB。"""

import configparser
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest


RUN_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = RUN_ROOT
WRAPPER = SOURCE_ROOT / "01_spotDecoding" / "04_global_reads_decoding.sh"
GENERATOR = SOURCE_ROOT / "generator_upstream_pipeline.py"


@pytest.mark.parametrize("evidence_value", [None, "true"])
def test_complete_config_preserves_pr_and_evidence_default(tmp_path, evidence_value):
    parser = configparser.ConfigParser()
    parser.read(SOURCE_ROOT / "batch_config.upstream.ini")
    for section in parser.sections():
        parser.remove_section(section)
    for key in tuple(parser.defaults()):
        if key.startswith("run_"):
            parser["DEFAULT"][key] = "false"
    parser["DEFAULT"].update({
        "samples": '{"StudySample": 1}',
        "project_root": str(tmp_path / "project root"),
        "auto_starfinder": str(SOURCE_ROOT),
        "decode_log": str(tmp_path / "decode logs"),
        "run_decoding": "true",
        "gd_intensityThresh_PR": "324",
    })
    if evidence_value is None:
        parser.remove_option("DEFAULT", "gd_save_decode_evidence")
    else:
        parser["DEFAULT"]["gd_save_decode_evidence"] = evidence_value
    parser["JOB_001"] = {
        "project_name": "StudySample",
        "job_suffix": "_evidence",
        "regDir_suffix": "_evidence",
    }
    config_path = tmp_path / "full_config.ini"
    with config_path.open("x", encoding="utf-8") as handle:
        parser.write(handle)
    output_path = tmp_path / "generated.sh"
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--config", str(config_path),
         "--output", str(output_path)],
        text=True, capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    generated = output_path.read_text(encoding="utf-8")
    command_lines = [line for line in generated.replace("\\\n", " ").splitlines()
                     if str(WRAPPER) in line]
    assert len(command_lines) == 1
    arguments = shlex.split(command_lines[0])
    assert arguments[arguments.index("--intensityThresh_PR") + 1] == "324"
    assert arguments[arguments.index("--save_decode_evidence") + 1] == (evidence_value or "false")
    assert arguments[arguments.index("--reg_dir_suffix") + 1] == "_evidence"
    assert arguments[arguments.index("--core_matlab_dir") + 1] == str(SOURCE_ROOT / "core_programs")
    # 只生成命令；测试过程中不执行生成的提交脚本。
    assert not (tmp_path / "decode logs").exists()


@pytest.mark.parametrize("evidence_value,pr", [(None, None), (None, "72"), ("TrUe", "72")])
def test_wrapper_passes_matlab_logical_and_pr(tmp_path, evidence_value, pr):
    project_root = tmp_path / "project root"
    position = project_root / "StudySample" / "01_data" / "round001" / "Position003"
    position.mkdir(parents=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture_path = tmp_path / "matlab_arguments.txt"
    for name, body in {
        "module": "#!/bin/bash\nexit 0\n",
        "matlab": '#!/bin/bash\nprintf "%s\\n" "$@" > "$DECODE_CAPTURE_FILE"\n',
    }.items():
        executable = fake_bin / name
        executable.write_text(body, encoding="utf-8")
        executable.chmod(0o755)
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.startswith("BASH_FUNC_module"):
            environment.pop(key)
    environment.update({
        "PATH": str(fake_bin) + os.pathsep + environment["PATH"],
        "DECODE_CAPTURE_FILE": str(capture_path),
        "SLURM_ARRAY_TASK_ID": "1",
        "SLURM_JOB_ID": "1",
        "SLURM_JOB_NAME": "gRD_test",
        "SLURM_JOB_USER": "test_user",
        "SLURM_JOB_SUBMIT_HOST": "test_host",
        "SLURM_SUBMIT_HOST": "test_host",
        "SLURM_SUBMIT_DIR": str(tmp_path),
        "SLURM_NODELIST": "test_node",
        "SLURMD_NODENAME": "test_node",
        "SLURM_JOB_NUM_NODES": "1",
        "SLURM_JOB_PARTITION": "test_partition",
        "SLURM_CPUS_PER_TASK": "8",
        "SLURM_JOB_CPUS_PER_NODE": "8",
    })
    arguments = [
        "bash", str(WRAPPER),
        "--project_root", str(project_root),
        "--project_name", "StudySample",
        "--reg_dir_suffix", "_evidence",
        "--core_matlab_dir", str(SOURCE_ROOT / "core_programs"),
    ]
    if pr is not None:
        arguments += ["--intensityThresh_PR", pr]
    if evidence_value is not None:
        arguments += ["--save_decode_evidence", evidence_value]
    result = subprocess.run(arguments, env=environment, cwd=tmp_path,
                            text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    captured = capture_path.read_text(encoding="utf-8").splitlines()
    assert captured[0] == "-batch"
    assert len(captured) == 2
    assert f"'IntensityThresh_perRound', {pr or 0}" in captured[1]
    assert "'voxel_size', [1,1,1]" in captured[1]
    logical = "true" if evidence_value is not None else "false"
    assert f"'save_decode_evidence', {logical}" in captured[1]
    assert "'global_reads_decoding', 'Position003'" in captured[1]
    assert "'02_registration_evidence'" in captured[1]
    assert "STATUS: SUCCESS" in result.stdout
