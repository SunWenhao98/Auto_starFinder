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
    for channel in ("refDAPI", "DAPI", "561-CA9", "488-CD144", "647-CD31", "647-GCnt", "561-GTrb"):
        (work_dir / f"raw-{channel}").mkdir(parents=True)
    for name in ("initial.txt", "joint_ref.txt", "joint_IF.txt", "joint_summary.json"):
        (work_dir / name).write_text("input\n", encoding="utf-8")
    script_dir = tmp_path / "runners"
    script_dir.mkdir()
    for runner in (
        "p24_ashlar_stitch_mosaic.py",
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

        if sys.argv[1] == "-":
            sys.argv = sys.argv[1:]
            exec(compile(sys.stdin.read(), "<stdin>", "exec"))
            sys.exit()
        runner = Path(sys.argv[2]).name
        argv = sys.argv[3:]
        options = {}
        index = 0
        while index < len(argv):
            flag = argv[index]
            if flag in ("--rotate90", "--rotate_positions", "--blend_rounding"):
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
            if "--seqe_dir" in options:
                outputs["seqe"] = output_dir / options["--seqe_config_name"]
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
        assert options["--round_name"] == "ref"
        assert options["--tile_transform_json"] == str(work_dir / "joint_summary.json")
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


@pytest.mark.parametrize("three_round", (False, True))
def test_generated_joint_chain_creates_logs_before_submission_and_keeps_dependencies(
    tmp_path: Path, three_round: bool,
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
    optional_values = {
        "ashlar_joint_stitch_if_input_config": "IF/initial.txt",
        "ashlar_joint_stitch_seqe_channel_dir": "seqE/raw-DAPI",
        "ashlar_joint_stitch_seqe_input_config": "seqE/initial.txt",
        "ashlar_joint_stitch_output_seqe_config": "joint_seqE.txt",
        "ashlar_joint_mosaic_seqe_channel_dir_prefix": "seqE/raw-",
        "ashlar_joint_mosaic_seqe_input_config": "joint_seqE.txt",
    }
    for key, value in optional_values.items():
        if three_round:
            defaults[key] = value
        else:
            parser.remove_option("DEFAULT", key)
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
    if three_round:
        assert calls[1]["argv"][calls[1]["argv"].index("--seqe_input_config") + 1] == "seqE/initial.txt"
        assert calls[2]["argv"][calls[2]["argv"].index("--seqe_channel_dir_prefix") + 1] == "seqE/raw-"
    else:
        assert "--seqe_channel_dir" not in calls[1]["argv"]


def test_three_round_wrappers_keep_independent_inputs_and_eight_outputs(wrapper_runtime):
    work_dir, common, environment = wrapper_runtime
    result = run_wrapper(
        "31_ashlar_stitch_joint.sh", common,
        ["--ref_channel_dir", "ref/raw-refDAPI", "--if_channel_dir", "IF/raw-DAPI",
         "--input_config", "ref/initial.txt", "--if_input_config", "IF/initial.txt",
         "--seqe_channel_dir", "seqE/raw-DAPI", "--seqe_input_config", "seqE/initial.txt"],
        environment,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    options = read_calls(Path(environment["CAPTURE"]))[0]["options"]
    assert options["--if_config_file"] == str(work_dir / "IF/initial.txt")
    assert options["--seqe_dir"] == str(work_dir / "seqE/raw-DAPI")
    assert options["--seqe_config_file"] == str(work_dir / "seqE/initial.txt")
    assert options["--ref_config_name"] == "TileConfiguration.registered.round001.AshlarJoint.txt"
    assert options["--if_config_name"] == "TileConfiguration.registered.IF.AshlarJoint.txt"
    assert options["--seqe_config_name"] == "TileConfiguration.registered.round011.AshlarJoint.txt"
    assert (work_dir / options["--seqe_config_name"]).is_file()
    result = run_wrapper(
        "32_ashlar_stitch_mosaic_joint.sh", common,
        ["--channel_mode", "LeicaIF", "--input_config", "TileConfiguration.registered.IF.AshlarJoint.txt",
         "--channel_dir_prefix", "IF/raw-", "--ref_channel_dir", "ref/raw-refDAPI",
         "--ref_input_config", "TileConfiguration.registered.round001.AshlarJoint.txt",
         "--seqe_channel_dir_prefix", "seqE/raw-", "--tile_transform_json", "joint_ref-IF_summary.json"],
        environment,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    calls = read_calls(Path(environment["CAPTURE"]))[1:]
    assert [c["options"]["--round_name"] for c in calls] == ["ref"] + ["IF"] * 4 + ["seqE"] * 3
    assert [Path(c["options"]["--input_dir"]).name for c in calls[5:]] == [
        "raw-647-GCnt", "raw-561-GTrb", "raw-DAPI",
    ]
    prefixes = [c["options"]["--output_image_prefix"] for c in calls]
    assert len(set(prefixes)) == 8
    assert all(Path(p + "_2d.ome.tif").is_file() for p in prefixes)
    assert all(c["options"]["--tile_transform_json"] == str(work_dir / "joint_ref-IF_summary.json") for c in calls)
    assert all(c["options"]["--config_file"] == str(work_dir / "TileConfiguration.registered.round011.AshlarJoint.txt") for c in calls[5:])


def test_joint_mosaic_uses_round_specific_flat_field_and_shared_options(wrapper_runtime):
    work_dir, common, environment = wrapper_runtime
    manifest = work_dir / "profile list.csv"
    manifest.write_text(
        "round,channel,profile_tif\nIF,DAPI,IF field.tif\nseqE,DAPI,seqE field.tif\n",
        encoding="utf-8",
    )
    result = run_wrapper(
        "32_ashlar_stitch_mosaic_joint.sh", common,
        ["--channel_mode", "LeicaIF", "--input_config", "joint_IF.txt",
         "--ref_channel_dir", "ref/raw-refDAPI", "--ref_input_config", "joint_ref.txt",
         "--seqe_channel_dir_prefix", "seqE/raw-", "--flat_field_manifest", manifest.name,
         "--blend_rounding", "true", "--canvas_mode", "ref",
         "--tile_transform_json", "joint_ref-IF_summary.json"],
        environment,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [call["options"] for call in read_calls(Path(environment["CAPTURE"]))]
    corrected = {call["--round_name"]: call["--flat_field"] for call in calls if "--flat_field" in call}
    assert len(calls) == 8
    assert corrected == {"IF": str(work_dir / "IF field.tif"), "seqE": str(work_dir / "seqE field.tif")}
    assert all(call["--blend_rounding"] and call["--canvas_mode"] == "ref" for call in calls)
    assert {call["--ref_canvas_config"] for call in calls} == {str(work_dir / "joint_ref.txt")}


@pytest.mark.parametrize(
    "wrapper", ("24_ashlar_stitch_mosaic.sh", "32_ashlar_stitch_mosaic_joint.sh"),
)
def test_seqe_mosaic_wrappers_export_three_real_channels_without_placeholder(
    wrapper, wrapper_runtime,
):
    work_dir, common, environment = wrapper_runtime
    assert not (work_dir / "raw-Padlayer").exists()
    result = run_wrapper(
        wrapper, common,
        ["--channel_mode", "LeicaSeqE", "--input_config", "initial.txt",
         "--output_prefix", "seqe"],
        environment,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    calls = read_calls(Path(environment["CAPTURE"]))
    assert [Path(call["options"]["--input_dir"]).name for call in calls] == [
        "raw-647-GCnt", "raw-561-GTrb", "raw-DAPI",
    ]
    outputs = [
        Path(call["options"]["--output_image_prefix"] + "_2d.ome.tif")
        for call in calls
    ]
    assert len(set(outputs)) == 3
    assert all(path.is_file() for path in outputs)


@pytest.mark.parametrize(
    "channel_mode,expected_channels",
    [
        ("LeicaSeqE", ["raw-647-GCnt", "raw-561-GTrb", "raw-DAPI"]),
        ("DAPI", ["raw-DAPI"]),
    ],
)
def test_fiji_mosaic_exports_selected_real_channels(
    wrapper_runtime, channel_mode, expected_channels,
):
    work_dir, common, environment = wrapper_runtime
    assert not (work_dir / "raw-Padlayer").exists()
    script_dir = Path(common[common.index("--script_dir") + 1])
    (script_dir / "fiji_grid_collection_stitch.bsh").touch()
    fiji_dir = Path(environment["CAPTURE"]).parent / "fiji"
    fiji_dir.mkdir()
    write_executable(
        fiji_dir / "ImageJ-linux64",
        """
        import json
        import os
        from pathlib import Path

        input_dir = Path(os.environ["INPUT_DIR"])
        assert input_dir.is_dir()
        assert (input_dir / os.environ["LAYOUT_FILE"]).is_file()
        with open(os.environ["CAPTURE"], "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"input_dir": str(input_dir)}) + "\\n")
        output = input_dir / (os.environ["OUTPUT_NAME"] + "_2d_Fiji.tif")
        output.write_text("synthetic fusion\\n", encoding="utf-8")
        """,
    )
    fiji_common = list(common)
    index = fiji_common.index("--conda_sh")
    del fiji_common[index:index + 2]
    result = run_wrapper(
        "16_fiji_stitch_mosaic.sh", fiji_common,
        ["--fiji_dir", str(fiji_dir), "--channel_mode", channel_mode,
         "--input_config", "initial.txt", "--output_prefix", "seqe"],
        environment,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    calls = read_calls(Path(environment["CAPTURE"]))
    assert [Path(call["input_dir"]).name for call in calls] == expected_channels
    outputs = list((work_dir / "stitched_contract").glob("sample_seqe_*_2d_Fiji.tif"))
    assert len(outputs) == len(expected_channels)
