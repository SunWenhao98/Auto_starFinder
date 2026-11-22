"""Real TIFF/CLI contracts for joint ref, IF and seqE stitching.

Run after activating the ashlar conda environment (its Java variables are
required). All images are synthetic; use one CPU task for the full suite.
JOINT_STITCH_RUNNER_DIR can select a preserved baseline for RED verification.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from scipy import ndimage
import tifffile


ROOT = Path(__file__).resolve().parents[1]
RUNNERS = Path(os.environ.get("JOINT_STITCH_RUNNER_DIR", ROOT / "02_FovIntegration"))
THREAD_ENV = {
    **os.environ,
    **{key: "1" for key in (
        "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
    )},
    "PYTHONDONTWRITEBYTECODE": "1",
}
TILE_SIZE = 256
NOMINAL = {
    f"Position{index + 1:03d}.tif": (96 + row * 160, 96 + col * 160)
    for index, (row, col) in enumerate((
        (0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2),
    ))
}


def textured_scene():
    """A nonperiodic field with one bright, spatially isolated landmark."""
    rng = np.random.default_rng(9517)
    fine = ndimage.gaussian_filter(rng.random((768, 896)), 1.1)
    coarse = ndimage.gaussian_filter(rng.random((768, 896)), 7.0)
    scene = 1500 + 10000 * (fine - fine.min()) / np.ptp(fine)
    scene += 9000 * (coarse - coarse.min()) / np.ptp(coarse)
    yy, xx = np.ogrid[:768, :896]
    scene += 42000 * np.exp(-((yy - 290) ** 2 + (xx - 290) ** 2) / 8)
    return np.rint(scene).astype(np.uint16)


def write_config(path, coordinates):
    lines = ["dim = 3", ""]
    lines.extend(f"{name}; ; ({x}, {y}, 0)" for name, (y, x) in coordinates.items())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_config(path):
    coordinates = {}
    for line in path.read_text().splitlines():
        match = re.match(r"([^;]+);\s*;\s*\(([^)]+)\)", line)
        if match:
            x, y, *_ = map(float, match[2].split(","))
            coordinates[match[1].strip()] = np.array([y, x])
    return coordinates


class JointThreeRoundContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="0001_261119_joint_contract_")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.environment = {**THREAD_ENV, "MPLCONFIGDIR": str(self.work / "matplotlib")}

    def run_cli(self, runner, arguments):
        return subprocess.run(
            [sys.executable, "-B", str(RUNNERS / runner), *map(str, arguments)],
            env=self.environment, text=True, capture_output=True, timeout=180,
        )

    def require_success(self, result):
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-6000:])

    def prepare_rounds(self, selections, shifts=None, rotations=None, blank=None, stack_depth=None):
        scene = textured_scene()
        shifts = shifts or {name: (0, 0) for name in selections}
        rotations = rotations or {}
        directories, configs, actual = {}, {}, {}
        for round_name, names in selections.items():
            directory = self.work / round_name
            directory.mkdir()
            directories[round_name] = directory
            config = self.work / f"{round_name}.initial.txt"
            configs[round_name] = config
            write_config(config, {name: NOMINAL[name] for name in names})
            image = scene
            if round_name in rotations:
                # Independent image generation: rotate the whole scene before
                # cropping, rather than calling the implementation's transform.
                image = ndimage.rotate(scene, rotations[round_name], reshape=False, order=1)
            actual[round_name] = {}
            for name in names:
                y, x = np.array(NOMINAL[name]) + shifts[round_name]
                tile = image[y:y + TILE_SIZE, x:x + TILE_SIZE]
                if round_name == blank:
                    tile = np.zeros_like(tile)
                if stack_depth is not None:
                    # Distinct Z planes retain the original scene as their MIP.
                    tile = np.stack([tile // divisor for divisor in range(stack_depth, 0, -1)])
                tifffile.imwrite(directory / name, tile, photometric="minisblack")
                actual[round_name][name] = np.array([y, x], dtype=float)
        return directories, configs, actual

    def joint_arguments(self, directories, configs):
        return [
            "--ref_dir", directories["ref"], "--if_dir", directories["IF"],
            "--seqe_dir", directories["seqE"], "--config_file", configs["ref"],
            "--if_config_file", configs["IF"], "--seqe_config_file", configs["seqE"],
            "--output_dir", self.work / "joint", "--prefix", "three_rounds",
            "--filter_sigma", "1.0", "--max_shift_frac", "0.2",
            "--rotation_threshold_mdeg", "50",
        ]

    def render_rounds(self, directories, summary_path, summary):
        outputs, arguments = {}, {}
        for round_name in ("ref", "IF", "seqE"):
            prefix = self.work / "mosaics" / f"{round_name}_DAPI"
            args = [
                "--input_dir", directories[round_name],
                "--config_file", summary["rounds"][round_name]["tile_config"],
                "--tile_transform_json", summary_path, "--round_name", round_name,
                "--output_image_prefix", prefix, "--output_format", "preserve",
                "--pixel_size_um", "0.142",
            ]
            result = self.run_cli("p32_ashlar_stitch_mosaic_joint.py", args)
            self.require_success(result)
            outputs[round_name] = Path(str(prefix) + "_2d.ome.tif")
            arguments[round_name] = args
        images = {name: tifffile.imread(path) for name, path in outputs.items()}
        expected_shape = tuple(summary["canvas_shape_yx"])
        self.assertTrue(all(image.shape == expected_shape for image in images.values()))
        reference_peak = np.array(np.unravel_index(images["ref"].argmax(), expected_shape))
        for name in ("IF", "seqE"):
            peak = np.array(np.unravel_index(images[name].argmax(), expected_shape))
            self.assertLessEqual(np.linalg.norm(peak - reference_peak), 2.0, name)
        return outputs, arguments, images

    def test_different_fov_lists_recover_positions_and_render_one_canvas_without_overwrite(self):
        names = list(NOMINAL)
        selections = {
            "ref": [names[i] for i in (0, 1, 3, 4)],
            "IF": names,
            "seqE": [names[i] for i in (1, 2, 4, 5)],
        }
        shifts = {"ref": (0, 0), "IF": (16, -16), "seqE": (-16, 16)}
        directories, configs, actual = self.prepare_rounds(selections, shifts=shifts)
        args = self.joint_arguments(directories, configs)
        self.require_success(self.run_cli("p31_ashlar_stitch_joint.py", args))
        summary_path = self.work / "joint/three_rounds_summary.json"
        summary = json.loads(summary_path.read_text())
        self.assertEqual(set(summary["rounds"]), set(selections))
        self.assertFalse(summary["rotate90"])
        solved = {
            name: read_config(Path(summary["rounds"][name]["tile_config"]))
            for name in selections
        }
        anchor = names[0]
        for round_name, selected in selections.items():
            self.assertEqual(list(solved[round_name]), selected)
            for name in selected:
                observed = solved[round_name][name] - solved["ref"][anchor]
                expected = actual[round_name][name] - actual["ref"][anchor]
                np.testing.assert_allclose(observed, expected, atol=1.0)
        outputs, mosaic_arguments, images = self.render_rounds(directories, summary_path, summary)
        self.assertEqual(len(set(outputs.values())), 3)
        self.assertFalse(np.array_equal(images["IF"], images["seqE"]))
        before = {path: path.read_bytes() for path in (self.work / "joint").iterdir() if path.is_file()}
        repeated = self.run_cli("p31_ashlar_stitch_joint.py", args)
        self.assertNotEqual(repeated.returncode, 0)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        image_bytes = {path: path.read_bytes() for path in outputs.values()}
        repeated = self.run_cli("p32_ashlar_stitch_mosaic_joint.py", mosaic_arguments["seqE"])
        self.assertNotEqual(repeated.returncode, 0)
        self.assertEqual({path: path.read_bytes() for path in image_bytes}, image_bytes)

    def test_three_plane_gray_stacks_recover_positions_and_render_one_canvas(self):
        names = [list(NOMINAL)[i] for i in (0, 1, 3, 4)]
        shifts = {"ref": (0, 0), "IF": (16, -16), "seqE": (-16, 16)}
        directories, configs, actual = self.prepare_rounds(
            {name: names for name in shifts}, shifts=shifts, stack_depth=3,
        )
        scene = textured_scene()
        with tifffile.TiffFile(directories["ref"] / names[0]) as image:
            self.assertEqual(len(image.pages), 3)
            volume = image.asarray()
        self.assertEqual(volume.shape, (3, TILE_SIZE, TILE_SIZE))
        self.assertFalse(np.array_equal(volume[0], volume[-1]))
        y, x = NOMINAL[names[0]]
        np.testing.assert_array_equal(volume.max(axis=0), scene[y:y + TILE_SIZE, x:x + TILE_SIZE])

        self.require_success(self.run_cli("p31_ashlar_stitch_joint.py", self.joint_arguments(directories, configs)))
        summary_path = self.work / "joint/three_rounds_summary.json"
        summary = json.loads(summary_path.read_text())
        solved = {
            name: read_config(Path(summary["rounds"][name]["tile_config"]))
            for name in shifts
        }
        anchor = names[0]
        for round_name in shifts:
            self.assertEqual(list(solved[round_name]), names)
            for name in names:
                observed = solved[round_name][name] - solved["ref"][anchor]
                expected = actual[round_name][name] - actual["ref"][anchor]
                np.testing.assert_allclose(observed, expected, atol=1.0)

        positions = np.vstack([list(values.values()) for values in actual.values()])
        origin = positions.min(axis=0)
        expected_shape = positions.max(axis=0) + TILE_SIZE - origin
        np.testing.assert_allclose(summary["canvas_shape_yx"], expected_shape, atol=2.0)
        _, _, images = self.render_rounds(directories, summary_path, summary)
        expected_peak = np.array(np.unravel_index(scene.argmax(), scene.shape)) - origin
        for name, image in images.items():
            observed_peak = np.array(np.unravel_index(image.argmax(), image.shape))
            self.assertLessEqual(np.linalg.norm(observed_peak - expected_peak), 2.0, name)
            self.assertEqual(image.dtype, np.uint16)

    def test_round_without_cross_round_image_evidence_fails(self):
        names = [list(NOMINAL)[i] for i in (0, 1, 3, 4)]
        directories, configs, _ = self.prepare_rounds(
            {name: names for name in ("ref", "IF", "seqE")}, blank="seqE",
        )
        result = self.run_cli("p31_ashlar_stitch_joint.py", self.joint_arguments(directories, configs))
        self.assertNotIn("unrecognized arguments", result.stderr)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.work / "joint/three_rounds_summary.json").exists())

    def test_small_round_rotations_are_estimated_and_resampled_in_the_shared_canvas(self):
        names = [list(NOMINAL)[i] for i in (0, 1, 3, 4)]
        rotations = {"IF": 1.0, "seqE": -0.6}
        directories, configs, _ = self.prepare_rounds(
            {name: names for name in ("ref", "IF", "seqE")}, rotations=rotations,
        )
        self.require_success(self.run_cli("p31_ashlar_stitch_joint.py", self.joint_arguments(directories, configs)))
        summary_path = self.work / "joint/three_rounds_summary.json"
        summary = json.loads(summary_path.read_text())
        for round_name, expected_angle in rotations.items():
            transform = summary["rounds"][round_name]["tile_transform"]
            self.assertIsNotNone(transform)
            actual_angle = np.degrees(np.angle(complex(*transform["complex_a"])))
            self.assertAlmostEqual(actual_angle, expected_angle, delta=0.35)
        _, _, images = self.render_rounds(directories, summary_path, summary)
        reference_peak = np.unravel_index(images["ref"].argmax(), images["ref"].shape)
        y, x = reference_peak
        patch = np.s_[y - 12:y + 13, x - 12:x + 13]
        for name in ("IF", "seqE"):
            correlation = np.corrcoef(images["ref"][patch].ravel(), images[name][patch].ravel())[0, 1]
            self.assertGreater(correlation, 0.95, name)


if __name__ == "__main__":
    unittest.main()
