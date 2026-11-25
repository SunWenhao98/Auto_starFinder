"""Profile estimation from actual grayscale TIFF and manifest inputs."""

import csv
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import tifffile


RUNNER = Path(__file__).resolve().parents[1] / "02_FovIntegration" / "p33_estimate_flat_field.py"


class FlatFieldEstimatorContracts(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.manifest = self.work / "sources.csv"
        self.output = self.work / "profiles"
        self.command = [
            sys.executable, str(RUNNER),
            "--input_manifest", str(self.manifest),
            "--output_dir", str(self.output),
            "--sigma", "0",
        ]

    def write_manifest(self, rows):
        with self.manifest.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(("round", "channel", "source_tiff"))
            writer.writerows(rows)

    def test_fov_mips_are_pooled_by_round_and_channel(self):
        y, x = np.indices((5, 7), dtype=np.uint16)
        if_first = 10 + 2 * x + y
        if_second = 30 + x + 3 * y
        seqe = 40 + 4 * x + y
        sources = {
            "first.tif": np.stack([if_first - 3, if_first, if_first - 1]),
            "second.tif": np.stack([if_second - 1, if_second - 3, if_second, if_second - 4]),
            "seqe.tif": seqe,
        }
        for name, image in sources.items():
            tifffile.imwrite(self.work / name, image, photometric="minisblack")
        self.write_manifest([
            ("IF", "DAPI", "first.tif"),
            ("IF", "DAPI", "second.tif"),
            ("seqE", "DAPI", self.work / "seqe.tif"),
        ])

        result = subprocess.run(self.command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        with (self.output / "profiles.csv").open(encoding="utf-8", newline="") as handle:
            profiles = {(row["round"], row["channel"]): Path(row["profile_tif"]) for row in csv.DictReader(handle)}
        self.assertEqual(set(profiles), {("IF", "DAPI"), ("seqE", "DAPI")})
        for role, expected in [("IF", if_first + if_second), ("seqE", seqe)]:
            path = profiles[(role, "DAPI")]
            self.assertEqual(path, self.output / role / "DAPI.tif")
            data = tifffile.imread(path)
            self.assertEqual(data.dtype, np.float32)
            np.testing.assert_allclose(data, expected / expected.mean(), rtol=1e-7)

        retry = subprocess.run(self.command, capture_output=True, text=True)
        self.assertNotEqual(retry.returncode, 0)
        np.testing.assert_array_equal(tifffile.imread(profiles[("seqE", "DAPI")]), data)

    def test_rgb_source_cannot_be_pooled_as_a_z_stack(self):
        tifffile.imwrite(self.work / "rgb.tif", np.ones((5, 7, 3), dtype=np.uint8), photometric="rgb")
        self.write_manifest([("IF", "DAPI", "rgb.tif")])

        result = subprocess.run(self.command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.output / "profiles.csv").exists())


if __name__ == "__main__":
    unittest.main()
