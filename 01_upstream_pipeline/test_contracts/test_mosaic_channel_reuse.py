"""Synthetic TIFF contracts for replay of one DAPI transform across channels."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import tifffile

RUNNER_DIR = Path(__file__).resolve().parents[1] / "02_FovIntegration"


def write_mosaic(path, pixels, pyramid=False):
    with tifffile.TiffWriter(path, bigtiff=True, ome=True) as writer:
        writer.write(
            pixels, photometric="minisblack", tile=(16, 16),
            metadata={"axes": "YX"}, subifds=1 if pyramid else None,
        )
        if pyramid:
            writer.write(pixels[::2, ::2], photometric="minisblack", subfiletype=1)


def identity(path, pixels):
    return {
        "image": str(path),
        "height_px": pixels.shape[0],
        "width_px": pixels.shape[1],
        "dtype": str(pixels.dtype),
        "size_bytes": path.stat().st_size,
        "mtime_epoch_s": path.stat().st_mtime_ns // 1_000_000_000,
    }


class ApplyMosaicChannelReuse(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name) / "sample" / "02_registration_test"
        self.root.mkdir(parents=True)
        self.fixed_path = self.root / "ref.ome.tif"
        self.moving_path = self.root / "DAPI.ome.tif"
        self.marker_path = self.root / "CA9.ome.tif"
        self.slice_path = self.root / "CD31.z020.ome.tif"
        self.transform_path = self.root / "dapi.transform.json"
        self.manifest_path = self.root / "channels.json"
        self.output_dir = self.root / "results"
        self.output_dapi = self.output_dir / "sample.registered_moving.ome.tif"
        self.output_marker = self.output_dir / "sample.registered_moving.CA9.ome.tif"
        self.output_slice = self.output_dir / "sample.registered_moving.CD31_z020.ome.tif"
        self.output_application = self.output_dir / "sample.application.json"
        self.moving = np.arange(1, 1 + 35 * 37, dtype=np.uint16).reshape(35, 37)
        self.marker = (60000 - 2 * self.moving).astype(np.uint16)
        self.slice = (self.moving % 251).astype(np.uint8)
        self.fixed = self.expected(self.moving)
        write_mosaic(self.fixed_path, self.fixed, pyramid=True)
        write_mosaic(self.moving_path, self.moving, pyramid=True)
        write_mosaic(self.marker_path, self.marker, pyramid=True)
        write_mosaic(self.slice_path, self.slice)
        self.transform_path.write_text(json.dumps({
            "schema_name": "starfinder_translation_registration",
            "schema_version": "1.1",
            "transform_type": "translation_2d",
            "mapping": "moving_to_reference",
            "coordinate_system": {
                "axis_order": "xy",
                "units": "pixel",
                "pixel_origin": "zero_based",
                "x_axis": "image_column_increasing_right",
                "y_axis": "image_row_increasing_down",
                "formula": {
                    "x_ref": "x_moving + shift_x_px",
                    "y_ref": "y_moving + shift_y_px",
                },
            },
            "reference": identity(self.fixed_path, self.fixed),
            "moving": identity(self.moving_path, self.moving),
            "method": {"backend": "python"},
            "quality": {"status": "PASS"},
            "transform": {"shift_x_px": -5, "shift_y_px": 3},
        }))
        self.manifest_path.write_text(json.dumps({
            "CA9": self.marker_path.name,
            "CD31_z020": str(self.slice_path),
        }))

    @staticmethod
    def expected(source):
        result = np.zeros((33, 39), dtype=source.dtype)
        result[3:, :32] = source[:30, 5:]
        return result

    def run_replay(self, with_manifest=True):
        command = [
            sys.executable, "-B", str(RUNNER_DIR / "p29_apply_mosaic_transform.py"),
            "--transform_json", self.transform_path,
            "--fixed_mosaic", self.fixed_path,
            "--moving_mosaic", self.moving_path,
            "--output_registered_mosaic", self.output_dapi,
            "--output_application_json", self.output_application,
            "--output_preview_tif", self.output_dir / "preview.tif",
            "--output_qc_png", self.output_dir / "qc.png",
            "--output_qc_pdf", self.output_dir / "qc.pdf",
            "--tile_size_px", "16",
            "--preview_downsample", "2",
            "--overview_block_px", "32",
        ]
        if with_manifest:
            command += ["--channel_manifest", self.manifest_path]
        return subprocess.run(command, check=False, capture_output=True, text=True)

    def test_same_dapi_transform_preserves_channel_pixels_and_dtype(self):
        result = self.run_replay()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for path, source in (
            (self.output_dapi, self.moving),
            (self.output_marker, self.marker),
            (self.output_slice, self.slice),
        ):
            actual = tifffile.imread(path)
            self.assertEqual(actual.dtype, source.dtype)
            np.testing.assert_array_equal(actual, self.expected(source))
        output = json.loads(self.output_application.read_text())["output"]
        self.assertEqual(output["channels"]["CA9"]["source_image"], str(self.marker_path))
        self.assertEqual(
            output["channels"]["CD31_z020"]["registered_mosaic"], str(self.output_slice)
        )

    def test_wrapper_chain_packages_registered_channels_without_rescaling(self):
        for path_mode in ("relative", "absolute"):
            with self.subTest(config_paths=path_mode):
                self.wrapper_chain(path_mode)

    def wrapper_chain(self, path_mode):
        external_configs = path_mode == "absolute"
        output_dir = self.root / f"results_{path_mode}"
        output_marker = output_dir / self.output_marker.name
        output_slice = output_dir / self.output_slice.name
        channel_manifest = self.manifest_path
        if external_configs:
            config_dir = Path(self.tempdir.name) / "formal configs"
            config_dir.mkdir()
            channel_manifest = config_dir / "channels.json"
            channel_manifest.write_text(json.dumps({
                "CA9": str(self.marker_path), "CD31_z020": str(self.slice_path),
            }))
        conda = self.root / "test conda.sh"
        if not conda.exists():
            conda.write_text("conda() { :; }\n")
        environment = os.environ.copy()
        environment["PATH"] = f"{Path(sys.executable).parent}:{environment['PATH']}"
        environment.update({
            f"SLURM_{key}": "test" for key in (
                "JOB_ID", "JOB_NAME", "JOB_USER", "SUBMIT_HOST", "SUBMIT_DIR",
                "NODELIST", "JOB_NUM_NODES", "JOB_PARTITION",
                "CPUS_PER_TASK", "JOB_CPUS_PER_NODE",
            )
        })
        environment["SLURMD_NODENAME"] = "test"
        common = [
            "--project_root", Path(self.tempdir.name),
            "--project_name", "sample", "--reg_dir_suffix", "_test",
            "--script_dir", RUNNER_DIR, "--conda_sh", conda,
        ]
        applied = subprocess.run(
            [
                "bash", RUNNER_DIR / "29_apply_mosaic_transform.sh", *common,
                "--transform_json", self.transform_path.name,
                "--fixed_path", self.fixed_path.name, "--moving_path", self.moving_path.name,
                "--channel_manifest", str(channel_manifest) if external_configs else channel_manifest.name,
                "--output_workdir", output_dir.name, "--output_label", "sample",
                "--tile_size_px", "16", "--preview_downsample", "2",
                "--overview_block_px", "32",
            ],
            env=environment, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        display_manifest = (config_dir if external_configs else output_dir) / "display inputs.json"
        display_profile = (config_dir if external_configs else output_dir) / "display profile.json"
        display_manifest.write_text(json.dumps({
            "pixel_size_um": 0.142,
            "planes": {
                "mip": {
                    "ref_DAPI": str(self.fixed_path),
                    "IF_CA9": str(output_marker) if external_configs else output_marker.name,
                },
                "z020": {"IF_CD31": str(output_slice) if external_configs else output_slice.name},
            },
        }))
        display_profile.write_text(json.dumps({
            "channels": {"IF_CA9": {"color": [230, 159, 0], "limits": [0, 63000]}},
            "planes": {"mip": {"overlays": {"review": ["ref_DAPI", "IF_CA9"]}}},
        }))
        # Exercise the legacy generated-job entry alongside the newly numbered wrapper.
        display_wrapper = (
            "35_prepare_mosaic_display.sh" if external_configs else "33_prepare_mosaic_display.sh"
        )
        display = subprocess.run(
            [
                "bash", RUNNER_DIR / display_wrapper, *common,
                "--stitching_workdir", output_dir.name,
                "--input_manifest", str(display_manifest) if external_configs else display_manifest.name,
                "--display_profile", str(display_profile) if external_configs else display_profile.name,
                "--output_dirname", "display", "--apply_display_mapping", "true",
            ],
            env=environment, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(display.returncode, 0, display.stdout + display.stderr)
        for label in ("Job ID", "Node", "CPUs per task"):
            self.assertRegex(display.stdout, rf"{label}:\s+test")
        self.assertIn("STATUS: SUCCESS", display.stdout)
        self.assertNotIn("STATUS:", display.stderr)
        output = output_dir / "display"
        np.testing.assert_array_equal(
            tifffile.imread(output / "mip.ome.tif"), np.stack((self.fixed, self.expected(self.marker)))
        )
        np.testing.assert_array_equal(
            tifffile.imread(output / "z020.ome.tif"), self.expected(self.slice)
        )
        presets = json.loads((output / "display_presets.json").read_text())
        self.assertEqual(
            presets["planes"]["mip"]["overlays"]["review"]["colors"][1], [230, 159, 0]
        )

    def test_ordinary_single_channel_replay(self):
        result = self.run_replay(with_manifest=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        np.testing.assert_array_equal(tifffile.imread(self.output_dapi), self.fixed)
        self.assertFalse(self.output_marker.exists())

    def test_mismatched_channel_shape_rejected(self):
        with tifffile.TiffWriter(self.slice_path) as writer:
            writer.write(self.slice[:-1])
        result = self.run_replay()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse(self.output_application.exists())
        self.assertFalse(self.output_dapi.exists())

    def test_existing_channel_output_blocks_batch(self):
        self.output_dir.mkdir()
        self.output_slice.write_bytes(b"keep original")
        result = self.run_replay()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.output_slice.read_bytes(), b"keep original")
        self.assertFalse(self.output_application.exists())
        self.assertFalse(self.output_dapi.exists())


if __name__ == "__main__":
    unittest.main()
