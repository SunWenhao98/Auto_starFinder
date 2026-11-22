"""Small TIFF contracts for the independent mosaic display step."""

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from xml.etree import ElementTree

import numpy as np
from PIL import Image
from scipy.ndimage import white_tophat
import tifffile


RUNNER = (
    Path(__file__).resolve().parents[1]
    / "02_FovIntegration"
    / "p33_prepare_mosaic_display.py"
)


class MosaicDisplayContracts(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        yy, xx = np.indices((519, 1031))
        self.ref = (2000 + yy * 3 + xx * 2).astype(np.uint16)
        self.ref[505:514, 508:519] += 1400
        self.ref[-1, -1] = 16000
        self.if_dapi = np.full(self.ref.shape, 113, dtype=np.uint8)
        self.if_dapi[511, 513] = 172
        with tifffile.TiffWriter(self.root / "ref.ome.tif", ome=True, bigtiff=True) as tif:
            tif.write(
                self.ref,
                tile=(256, 256),
                subifds=1,
                photometric="minisblack",
                compression="deflate",
            )
            tif.write(self.ref[::2, ::2], tile=(128, 128), subfiletype=1)
        tifffile.imwrite(self.root / "if_dapi.tif", self.if_dapi, tile=(256, 256))
        self.manifest = self.root / "inputs.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "pixel_size_um": 0.142,
                    "planes": {
                        "mip": {"ref_DAPI": "ref.ome.tif", "IF_DAPI": "if_dapi.tif"},
                        "z020": {"IF_DAPI": "if_dapi.tif", "ref_DAPI": "ref.ome.tif"},
                    },
                }
            )
        )
        self.profile = self.root / "profile.json"
        self.profile.write_text(
            json.dumps(
                {
                    "channels": {
                        "ref_DAPI": {
                            "background_radius_px": 7,
                            "color": [0, 114, 178],
                            "limits": [100, 4000],
                        },
                        "IF_DAPI": {"color": [230, 159, 0], "limits": [12, 220]},
                    },
                    "planes": {
                        "z020": {
                            "channels": {"ref_DAPI": {"background_radius_px": 0}},
                            "overlays": {"reference": ["ref_DAPI"]},
                        }
                    },
                    "overlays": {"DAPI": ["ref_DAPI", "IF_DAPI"]},
                }
            )
        )

    def run_display(self, output, *flags):
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(RUNNER),
                "--input_manifest",
                str(self.manifest),
                "--display_profile",
                str(self.profile),
                "--output_dir",
                str(output),
                *flags,
            ],
            cwd=self.root,
            env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
            capture_output=True,
            text=True,
            timeout=45,
        )

    def test_background_and_mapping_are_independent(self):
        expected_background_subtraction = white_tophat(self.ref, size=(15, 15))
        for background, mapping in ((False, False), (False, True), (True, False), (True, True)):
            with self.subTest(background=background, mapping=mapping):
                flags = []
                if background:
                    flags.append("--subtract_background")
                if mapping:
                    flags.append("--apply_display_mapping")
                output = self.root / f"out_{background}_{mapping}"
                result = self.run_display(output, *flags)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                with tifffile.TiffFile(output / "mip.ome.tif") as tif:
                    self.assertTrue(tif.is_ome and tif.is_bigtiff)
                    series = tif.series[0]
                    self.assertEqual(series.axes, "CYX")
                    self.assertEqual(series.dtype, np.dtype("uint16"))
                    self.assertGreaterEqual(len(series.levels), 3)
                    self.assertTrue(all(level.pages[0].is_tiled for level in series.levels))
                    self.assertEqual(series.levels[1].shape, (2, 260, 516))
                    self.assertEqual(series.levels[2].shape, (2, 130, 258))
                    pixels = series.asarray()
                    expected = expected_background_subtraction if background else self.ref
                    np.testing.assert_array_equal(pixels[0], expected)
                    np.testing.assert_array_equal(pixels[1], self.if_dapi)
                    first_level = series.levels[1].asarray()
                    np.testing.assert_array_equal(first_level[:, -1, -1], pixels[:, -1, -1])
                    xml = ElementTree.fromstring(tif.ome_metadata)
                    ome_pixels = xml.find(".//{*}Pixels")
                    self.assertEqual(float(ome_pixels.attrib["PhysicalSizeX"]), 0.142)
                    self.assertEqual(
                        [channel.attrib["Name"] for channel in ome_pixels.findall("{*}Channel")],
                        ["ref_DAPI", "IF_DAPI"],
                    )
                np.testing.assert_array_equal(
                    tifffile.imread(output / "z020.ome.tif"),
                    np.stack((self.if_dapi, self.ref)),
                )
                presets = json.loads((output / "display_presets.json").read_text())
                overlay = presets["planes"]["mip"]["overlays"]["DAPI"]
                self.assertEqual(overlay["selections"], [{"c": 0, "z": 0, "t": 0}, {"c": 1, "z": 0, "t": 0}])
                self.assertEqual(overlay["channelsVisible"], [True, True])
                self.assertEqual(overlay["contrastLimits"][0], [100, 4000] if mapping else [0, 65535])
                self.assertEqual(overlay["colors"][0], [0, 114, 178] if mapping else [255, 255, 255])
                diagnostic_overlay = presets["planes"]["z020"]["overlays"]["reference"]
                self.assertEqual(diagnostic_overlay["selections"], [{"c": 1, "z": 0, "t": 0}])
                with Image.open(output / "mip_01_DAPI.png") as png:
                    self.assertEqual((png.format, png.mode, png.size), ("PNG", "RGB", (1031, 519)))
                    if mapping:
                        self.assertEqual(png.getpixel((1030, 518)), (112, 191, 178))
                    else:
                        value = round(113 + int(expected[-1, -1]) / 257)
                        self.assertEqual(png.getpixel((1030, 518)), (value,) * 3)
                with Image.open(output / "z020_01_reference.png") as png:
                    self.assertEqual(png.getpixel((1030, 518)), (0, 114, 178) if mapping else (62,) * 3)

    def test_large_mosaic_png_uses_a_pyramid_level(self):
        pixels = np.full((65, 2305), 200, dtype=np.uint8)
        tifffile.imwrite(self.root / "large.tif", pixels)
        self.manifest.write_text(json.dumps({
            "pixel_size_um": 0.142, "planes": {"mip": {"DAPI": "large.tif"}},
        }))
        self.profile.write_text("{}")
        output = self.root / "large_preview"
        result = self.run_display(output)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        np.testing.assert_array_equal(tifffile.imread(output / "mip.ome.tif"), pixels)
        with Image.open(output / "mip_01_DAPI.png") as png:
            self.assertEqual(png.size, (1153, 33))
            self.assertEqual(png.getpixel((1152, 32)), (200, 200, 200))

    def test_mismatched_shape_and_existing_directory_are_rejected(self):
        tifffile.imwrite(self.root / "if_dapi.tif", self.if_dapi[:-1])
        output = self.root / "mismatch"
        self.assertNotEqual(self.run_display(output).returncode, 0)
        self.assertFalse((output / "display_presets.json").exists())
        output = self.root / "protected"
        output.mkdir()
        sentinel = output / "mip.ome.tif"
        sentinel.write_bytes(b"previous")
        self.assertNotEqual(self.run_display(output).returncode, 0)
        self.assertEqual(sentinel.read_bytes(), b"previous")


if __name__ == "__main__":
    unittest.main()
