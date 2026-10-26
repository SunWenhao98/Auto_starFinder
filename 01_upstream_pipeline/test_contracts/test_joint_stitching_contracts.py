from __future__ import annotations

import configparser
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER_DIR = ROOT / "02_FovIntegration"
STAGES = (
    ("ashlar_mst_stitch", "30_ashlar_stitch_mst.sh"),
    ("ashlar_joint_stitch", "31_ashlar_stitch_joint.sh"),
    ("ashlar_joint_mosaic", "32_ashlar_stitch_mosaic_joint.sh"),
)


def write_executable(path: Path, source: str) -> None:
    path.write_text(f"#!{sys.executable}\n" + textwrap.dedent(source), encoding="utf-8")
    path.chmod(0o755)


def read_calls(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def wrapper_runtime(tmp_path: Path) -> tuple[Path, list[str], dict[str, str]]:
    project_root = tmp_path / "project root"
    work_dir = project_root / "sample" / "02_registration_contract" / "stitching"
    for channel in ("refDAPI", "DAPI", "561-CA9", "488-CD144", "647-CD31"):
        (work_dir / f"raw-{channel}").mkdir(parents=True)
    for name in ("initial.txt", "joint_ref.txt", "joint_IF.txt", "joint_summary.json"):
        (work_dir / name).write_text("input\n", encoding="utf-8")
    script_dir = tmp_path / "runners"
    script_dir.mkdir()
    for runner in (
        "p30_ashlar_stitch_mst.py",
        "p31_ashlar_stitch_joint.py",
        "p32_ashlar_stitch_mosaic_joint.py",
    ):
        (script_dir / runner).touch()
    conda_sh = tmp_path / "conda.sh"
    conda_sh.write_text("conda() { :; }\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_executable(
        fake_bin / "python",
        """
        import json
        import os
        import sys
        from pathlib import Path

        runner = Path(sys.argv[2]).name
        argv = sys.argv[3:]
        options = {}
        index = 0
        while index < len(argv):
            flag = argv[index]
            if flag in ("--rotate90", "--rotate_positions"):
                options[flag] = True
                index += 1
            else:
                options[flag] = argv[index + 1]
                index += 2
        with open(os.environ["CAPTURE"], "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"runner": runner, "options": options}) + "\\n")
        if runner.startswith("p31_"):
            output_dir = Path(options["--output_dir"])
            outputs = {
                "ref": output_dir / options["--ref_config_name"],
                "if": output_dir / options["--if_config_name"],
                "summary": output_dir / (options["--prefix"] + "_summary.json"),
            }
        else:
            outputs = {"image": Path(options["--output_image_prefix"] + "_2d.ome.tif")}
            if "--registered_config_file" in options:
                outputs["config"] = Path(options["--registered_config_file"])
        for label, path in outputs.items():
            if label != os.environ.get("OMIT_OUTPUT"):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("result\\n", encoding="utf-8")
        """,
    )
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "CAPTURE": str(tmp_path / "runner_calls.jsonl"),
            "SLURM_JOB_ID": "1001",
            "SLURM_JOB_NAME": "joint_contract",
            "SLURM_JOB_USER": "test_user",
            "SLURM_SUBMIT_HOST": "submit01",
            "SLURM_SUBMIT_DIR": str(tmp_path),
            "SLURM_NODELIST": "node01",
            "SLURMD_NODENAME": "node01",
            "SLURM_JOB_NUM_NODES": "1",
            "SLURM_JOB_PARTITION": "test",
            "SLURM_CPUS_PER_TASK": "4",
            "SLURM_JOB_CPUS_PER_NODE": "4",
        }
    )
    common = [
        "--project_root",
        str(project_root),
        "--project_name",
        "sample",
        "--reg_dir_suffix",
        "_contract",
        "--stitching_workdir",
        "stitching",
        "--script_dir",
        str(script_dir),
        "--conda_sh",
        str(conda_sh),
    ]
    return work_dir, common, environment


def run_wrapper(
    name: str, common: list[str], args: list[str], environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(WRAPPER_DIR / name), *common, *args],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
        timeout=15,
    )


@pytest.mark.parametrize("stage,wrapper", STAGES)
def test_joint_wrappers_resolve_paths_and_channel_semantics(
    stage: str, wrapper: str, wrapper_runtime: tuple[Path, list[str], dict[str, str]]
) -> None:
    work_dir, common, environment = wrapper_runtime
    args = {
        "ashlar_mst_stitch": [
            "--source_channel_dir",
            "raw-refDAPI",
            "--input_config",
            "initial.txt",
            "--output_config",
            "mst.txt",
            "--output_prefix",
            "mst",
            "--rotate90",
            "true",
        ],
        "ashlar_joint_stitch": [
            "--ref_channel_dir",
            "raw-refDAPI",
            "--if_channel_dir",
            "raw-DAPI",
            "--input_config",
            "initial.txt",
            "--output_ref_config",
            "result_ref.txt",
            "--output_if_config",
            "result_IF.txt",
            "--output_prefix",
            "joint_result",
            "--rotate90",
            "true",
        ],
        "ashlar_joint_mosaic": [
            "--channel_mode",
            "LeicaIF",
            "--input_config",
            "joint_IF.txt",
            "--ref_channel_dir",
            "raw-refDAPI",
            "--ref_input_config",
            "joint_ref.txt",
            "--tile_transform_json",
            "joint_summary.json",
            "--output_prefix",
            "mosaic",
        ],
    }[stage]
    result = run_wrapper(wrapper, common, args, environment)
    assert result.returncode == 0, result.stdout + result.stderr
    calls = read_calls(Path(environment["CAPTURE"]))
    assert {call["runner"] for call in calls} == {"p" + wrapper.replace(".sh", ".py")}
    options = calls[0]["options"]
    if stage == "ashlar_mst_stitch":
        assert options["--input_dir"] == str(work_dir / "raw-refDAPI")
        assert options["--config_file"] == str(work_dir / "initial.txt")
        assert options["--registered_config_file"] == str(work_dir / "mst.txt")
        assert options["--rotate90"] is True
        assert (work_dir / "stitching_results/mst_2d.ome.tif").is_file()
    elif stage == "ashlar_joint_stitch":
        assert options["--ref_dir"] == str(work_dir / "raw-refDAPI")
        assert options["--if_dir"] == str(work_dir / "raw-DAPI")
        assert options["--config_file"] == str(work_dir / "initial.txt")
        assert options["--output_dir"] == str(work_dir)
        assert options["--rotate90"] is True
        assert all(
            (work_dir / name).stat().st_size
            for name in ("result_ref.txt", "result_IF.txt", "joint_result_summary.json")
        )
    else:
        assert [Path(call["options"]["--input_dir"]).name for call in calls] == [
            "raw-refDAPI",
            "raw-561-CA9",
            "raw-488-CD144",
            "raw-647-CD31",
            "raw-DAPI",
        ]
        assert options["--config_file"] == str(work_dir / "joint_ref.txt")
        assert "--tile_transform_json" not in options
        for call in calls[1:]:
            assert call["options"]["--config_file"] == str(work_dir / "joint_IF.txt")
            assert call["options"]["--tile_transform_json"] == str(
                work_dir / "joint_summary.json"
            )
        assert (
            len(list((work_dir / "stitching_results").glob("mosaic_*_2d.ome.tif"))) == 5
        )


@pytest.mark.parametrize("missing", ("ref", "if", "summary"))
def test_joint_stitch_requires_each_of_its_three_outputs(
    missing: str, wrapper_runtime: tuple[Path, list[str], dict[str, str]]
) -> None:
    _, common, environment = wrapper_runtime
    environment["OMIT_OUTPUT"] = missing
    result = run_wrapper(
        "31_ashlar_stitch_joint.sh",
        common,
        [
            "--ref_channel_dir",
            "raw-refDAPI",
            "--if_channel_dir",
            "raw-DAPI",
            "--input_config",
            "initial.txt",
            "--output_ref_config",
            "new_ref.txt",
            "--output_if_config",
            "new_IF.txt",
            "--output_prefix",
            "new_joint",
        ],
        environment,
    )
    assert len(read_calls(Path(environment["CAPTURE"]))) == 1
    assert result.returncode != 0


def test_generated_joint_chain_creates_logs_before_submission_and_keeps_dependencies(
    tmp_path: Path,
) -> None:
    parser = configparser.ConfigParser(interpolation=configparser.BasicInterpolation())
    parser.read(ROOT / "batch_config.upstream.ini")
    for section in parser.sections():
        parser.remove_section(section)
    defaults = parser["DEFAULT"]
    for key in defaults:
        if key.startswith("run_"):
            defaults[key] = "false"
    defaults["samples"] = '{"sample": 1}'
    defaults["stitch_log"] = str(tmp_path / "stitch logs")
    defaults["fovIntegration"] = str(WRAPPER_DIR)
    for stage, _ in STAGES:
        defaults[f"run_{stage}"] = "true"
    parser["JOB_TEST"] = {
        "project_name": "sample",
        "job_suffix": "contract",
        "regDir_suffix": "_contract",
    }
    config = tmp_path / "config.ini"
    with config.open("w", encoding="utf-8") as handle:
        parser.write(handle)
    generated = tmp_path / "submit.sh"
    rendering = subprocess.run(
        [
            sys.executable,
            str(ROOT / "generator_upstream_pipeline.py"),
            "--config",
            str(config),
            "--output",
            str(generated),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert rendering.returncode == 0, rendering.stderr
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_executable(fake_bin / "id", 'print("test_user")\n')
    write_executable(
        fake_bin / "squeue",
        """
        import os
        from pathlib import Path
        counter = Path(os.environ["COUNTER"])
        last = int(counter.read_text()) if counter.exists() else 5000
        for job_id in range(5001, last + 1):
            print(f"{job_id}|{job_id}|test_user|RUNNING")
        """,
    )
    write_executable(
        fake_bin / "sbatch",
        """
        import json
        import os
        import shlex
        import sys
        from pathlib import Path

        argv = sys.argv[1:]
        wrapper = Path(next(token for token in argv if token.endswith(".sh")))
        for line in wrapper.read_text().splitlines():
            if line.startswith(("#SBATCH -o ", "#SBATCH -e ")):
                assert Path(shlex.split(line)[2]).parent.is_dir(), line
        counter = Path(os.environ["COUNTER"])
        job_id = int(counter.read_text()) + 1 if counter.exists() else 5001
        counter.write_text(str(job_id))
        with open(os.environ["CAPTURE"], "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"argv": argv, "cwd": os.getcwd()}) + "\\n")
        print(f"{job_id};fake-cluster")
        """,
    )
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "COUNTER": str(tmp_path / "counter"),
            "CAPTURE": str(tmp_path / "sbatch.jsonl"),
        }
    )
    result = subprocess.run(
        ["bash", str(generated)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    calls = read_calls(Path(environment["CAPTURE"]))
    assert [call["argv"][call["argv"].index("-J") + 1] for call in calls] == [
        stage for stage, _ in STAGES
    ]
    assert not any(token.startswith("--dependency=") for token in calls[0]["argv"])
    for index, call in enumerate(calls[1:], start=1):
        assert f"--dependency=afterok:{5000 + index}" in call["argv"]
    assert {call["cwd"] for call in calls} == {
        str(tmp_path / "stitch logs/submitcontract")
    }
