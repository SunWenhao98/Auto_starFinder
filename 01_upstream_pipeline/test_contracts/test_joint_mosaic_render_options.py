"""Synthetic numeric contracts for the opt-in joint mosaic render modes."""

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import tifffile


RUNNER = (
    Path(__file__).resolve().parents[1]
    / "02_FovIntegration"
    / "p32_ashlar_stitch_mosaic_joint.py"
)


class JointMosaicRenderOptions(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="0001_joint_mosaic_options_")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.tiles = self.root / "tiles"
        self.tiles.mkdir()
        self.config = self.root / "registered.txt"
        self.environment = {
            **os.environ,
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MPLCONFIGDIR": str(self.root / "matplotlib"),
        }

    def write_config(self, path, tiles):
        lines = ["dim = 3"]
        lines.extend(f"{name}; ; ({x}, {y}, 0)" for name, y, x in tiles)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_tile(self, name, pixels):
        tifffile.imwrite(self.tiles / name, pixels, photometric="minisblack")

    def render(self, name, *options, expect_success=True):
        result = subprocess.run(
            [
                sys.executable, "-B", str(RUNNER),
                "--input_dir", str(self.tiles),
                "--config_file", str(self.config),
                "--output_image_prefix", str(self.root / name),
                *map(str, options),
            ],
            env=self.environment, text=True, capture_output=True, timeout=120,
        )
        if expect_success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)

    def test_sensor_profile_precedes_rotation_for_mip_slice_and_stack(self):
        height, width = 24, 40
        yy, xx = np.indices((height, width))
        volume = np.stack([120 + yy + xx + level for level in (0, 20, 30, 40)]).astype(np.uint8)
        profile = np.where(xx < width // 2, 0.5, 1.5).astype(np.float32)
        profile_path = self.root / "profile.tif"
        tifffile.imwrite(profile_path, profile)
        self.write_tile("Position001.tif", volume)
        self.write_config(self.config, [("Position001.tif", 0, 0)])
        self.render(
            "corrected", "--flat_field", profile_path, "--rotate90",
            "--slice_indices", "2", "--make_3d", "true",
        )

        corrected = np.clip(np.rint(volume / profile), 0, 255).astype(np.uint8)
        rotated = np.rot90(corrected, -1, axes=(-2, -1))
        np.testing.assert_array_equal(
            tifffile.imread(self.root / "corrected_2d.ome.tif"), rotated.max(axis=0),
        )
        np.testing.assert_array_equal(
            tifffile.imread(self.root / "corrected_z002_2d.ome.tif"), rotated[1],
        )
        np.testing.assert_array_equal(
            tifffile.imread(self.root / "corrected_3d.ome.tif"), rotated,
        )
        np.testing.assert_array_equal(
            tifffile.imread(self.root / "corrected_flatfield.tif"), profile,
        )

        tifffile.imwrite(self.root / "wrong_shape.tif", profile.T)
        self.render(
            "wrong", "--flat_field", self.root / "wrong_shape.tif", "--rotate90",
            expect_success=False,
        )
        self.assertFalse((self.root / "wrong_2d.ome.tif").exists())

    def test_auto_uses_tiles_selected_by_configuration_and_channel(self):
        self.write_config(self.config, [("Position001_ch03.tif", 0, 0)])
        pixels = np.full((16, 18), 100, dtype=np.uint16)
        self.write_tile("Position001_ch01.tif", pixels)
        self.write_tile("Position002_ch01.tif", np.ones((24, 30), dtype=np.uint16))
        self.render(
            "auto", "--flat_field", "auto", "--channel_from", "ch03",
            "--channel_to", "ch01",
        )
        np.testing.assert_array_equal(tifffile.imread(self.root / "auto_2d.ome.tif"), pixels)
        np.testing.assert_array_equal(tifffile.imread(self.root / "auto_flatfield.tif"), 1.0)

    def test_reference_canvas_uses_reference_origin_and_crops_moving_extent(self):
        tile_size = (16, 18)
        self.write_config(self.config, [
            ("Position001.tif", 0, 0),
            ("Position002.tif", 24, 25),
        ])
        self.write_tile("Position001.tif", np.full(tile_size, 31, dtype=np.uint16))
        self.write_tile("Position002.tif", np.full(tile_size, 99, dtype=np.uint16))
        ref_config = self.root / "ref_registered.txt"
        self.write_config(ref_config, [("Position003.tif", 4, 6)])
        summary_path = self.root / "joint_summary.json"
        summary_path.write_text(json.dumps({
            "rotate90": False,
            "canvas_origin_yx": [0, 0],
            "canvas_shape_yx": [40, 43],
            "rounds": {
                "ref": {"tile_config": str(ref_config), "tile_size_yx": list(tile_size)},
                "IF": {"tile_transform": None},
            },
        }), encoding="utf-8")
        self.render("joint", "--tile_transform_json", summary_path)
        self.render("ref", "--tile_transform_json", summary_path, "--canvas_mode", "ref")
        joint = tifffile.imread(self.root / "joint_2d.ome.tif")
        ref = tifffile.imread(self.root / "ref_2d.ome.tif")
        canvas = json.loads((self.root / "ref_canvas.json").read_text(encoding="utf-8"))
        self.assertEqual(canvas["canvas_origin_yx"], [4, 6])
        self.assertEqual(canvas["canvas_shape_yx"], list(tile_size))
        self.assertEqual(ref.shape, tile_size)
        np.testing.assert_array_equal(ref, joint[4:20, 6:24])

    def test_rounding_changes_only_noninteger_overlap_values(self):
        self.write_config(self.config, [
            ("Position001.tif", 0, 0),
            ("Position002.tif", 0, 8),
        ])
        for name, value in (("Position001.tif", 11), ("Position002.tif", 12)):
            self.write_tile(name, np.full((16, 16), value, dtype=np.uint8))
        self.render("native")
        self.render("rounded", "--blend_rounding")
        native = tifffile.imread(self.root / "native_2d.ome.tif")
        rounded = tifffile.imread(self.root / "rounded_2d.ome.tif")
        difference = rounded.astype(int) - native.astype(int)
        np.testing.assert_array_equal(difference[:, :8], 0)
        np.testing.assert_array_equal(difference[:, 16:], 0)
        self.assertEqual(difference.min(), 0)
        self.assertEqual(difference.max(), 1)


if __name__ == "__main__":
    unittest.main()
