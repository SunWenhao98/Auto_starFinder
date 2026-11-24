"""Submission wiring for a route B application followed by mosaic display."""

import configparser
from pathlib import Path
import shlex
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_generated_display_depends_on_requested_route_b_application(tmp_path):
    config = configparser.ConfigParser()
    config.read(ROOT / "batch_config.upstream.ini")
    for section in config.sections():
        config.remove_section(section)
    defaults = config["DEFAULT"]
    for key in defaults:
        if key.startswith("run_"):
            defaults[key] = "false"
    defaults["samples"] = '{"sample": 1}'
    defaults["fovIntegration"] = str(ROOT / "02_FovIntegration")
    defaults["stitch_log"] = str(tmp_path / "stitch logs")
    config["JOB_REVIEW"] = {
        "project_name": "sample",
        "job_suffix": "review",
        "regDir_suffix": "_review",
        "run_apply_mosaic_transform": "true",
        "transform_apply_channel_manifest": "IF/extra planes.json",
        "run_mosaic_display": "true",
        "mosaic_display_input_manifest": "aligned planes.json",
        "mosaic_display_subtract_background": "true",
        "mosaic_display_apply_display_mapping": "false",
    }
    ini = tmp_path / "config.ini"
    with ini.open("x") as handle:
        config.write(handle)
    generated = tmp_path / "submit.sh"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "generator_upstream_pipeline.py"),
            "--config", str(ini),
            "--output", str(generated),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["bash", "-n", str(generated)], check=True)
    script = generated.read_text()
    assert script.index("29_apply_mosaic_transform.sh") < script.index("33_prepare_mosaic_display.sh")
    apply = script.split("TRANSFORM_APPLY_OUTPUT=$(submit_when_ready ", 1)[1]
    display = script.split("MOSAIC_DISPLAY_OUTPUT=$(submit_when_ready ", 1)[1]
    apply_argv = shlex.split(apply.split(")\n", 1)[0].replace("\\\n", ""))
    display_argv = shlex.split(display.split(")\n", 1)[0].replace("\\\n", ""))
    assert display_argv[4] == "${TRANSFORM_APPLY_JOB_ID}"
    assert apply_argv[apply_argv.index("--channel_manifest") + 1] == "IF/extra planes.json"
    assert display_argv[display_argv.index("--input_manifest") + 1] == "aligned planes.json"
    assert display_argv[display_argv.index("--subtract_background") + 1] == "true"
    assert display_argv[display_argv.index("--apply_display_mapping") + 1] == "false"


def test_generated_if_and_seqe_mip_reviews_keep_round_jobs_separate(tmp_path):
    config = configparser.ConfigParser()
    config.read(ROOT / "batch_config.upstream.ini")
    for section in config.sections():
        config.remove_section(section)
    defaults = config["DEFAULT"]
    for key in defaults:
        if key.startswith("run_"):
            defaults[key] = "false"
    defaults["samples"] = '{"sample": 1}'
    defaults["fovIntegration"] = str(ROOT / "02_FovIntegration")
    defaults["stitch_log"] = str(tmp_path / "stitch logs")
    for round_name in ("IF", "seqE"):
        config[f"JOB_REVIEW_{round_name}"] = {
            "project_name": "sample",
            "job_suffix": f"review_{round_name}",
            "regDir_suffix": "_review",
            "run_apply_mosaic_transform": "true",
            "transform_apply_channel_manifest": f"{round_name}/channels.json",
            "transform_apply_output_label": f"{round_name}_to_ref",
            "run_mosaic_display": "true",
            "mosaic_display_stitching_workdir": "B_Ashlar",
            "mosaic_display_input_manifest": f"{round_name}/display_mip_inputs.json",
            "mosaic_display_profile": f"{round_name}/display_profile.json",
            "mosaic_display_output_dirname": f"{round_name}/display_review",
        }
    ini = tmp_path / "round_reviews.ini"
    with ini.open("x") as handle:
        config.write(handle)
    generated = tmp_path / "submit_round_reviews.sh"
    subprocess.run(
        [
            sys.executable, str(ROOT / "generator_upstream_pipeline.py"),
            "--config", str(ini), "--output", str(generated),
        ],
        check=True, capture_output=True, text=True,
    )
    subprocess.run(["bash", "-n", str(generated)], check=True)
    script = generated.read_text()
    applications = script.split("TRANSFORM_APPLY_OUTPUT=$(submit_when_ready ")[1:]
    assert len(applications) == 2
    for round_name, application in zip(("IF", "seqE"), applications):
        apply_argv = shlex.split(application.split(")\n", 1)[0].replace("\\\n", ""))
        displays = application.split("MOSAIC_DISPLAY_OUTPUT=$(submit_when_ready ")
        assert len(displays) == 2
        display_argv = shlex.split(displays[1].split(")\n", 1)[0].replace("\\\n", ""))
        assert display_argv[4] == "${TRANSFORM_APPLY_JOB_ID}"
        assert apply_argv[apply_argv.index("--channel_manifest") + 1] == f"{round_name}/channels.json"
        assert display_argv[display_argv.index("--stitching_workdir") + 1] == "B_Ashlar"
        assert display_argv[display_argv.index("--input_manifest") + 1] == f"{round_name}/display_mip_inputs.json"
        assert display_argv[display_argv.index("--display_profile") + 1] == f"{round_name}/display_profile.json"
        assert display_argv[display_argv.index("--output_dirname") + 1] == f"{round_name}/display_review"
