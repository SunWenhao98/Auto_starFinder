"""Synthetic contracts for round layouts, links and explicit image conversion."""

import csv
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import tifffile


PIPELINE = Path(__file__).resolve().parents[1]
RUNNER = PIPELINE / "02_FovIntegration" / "p11b_prepare_layout.py"
WRAPPER = PIPELINE / "02_FovIntegration" / "11b_prepare_layout.sh"


class LayoutContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.raw = self.root / "source" / "round001"
        self.output = self.root / "method" / "ref"

    def acquisition(self, round_dir, positions=(1, 3), channels=(3,)):
        for number in positions:
            position = round_dir / f"Position{number:03d}"
            position.mkdir(parents=True)
            for channel in channels:
                path = position / f"sample_Position{number:03d}_ch{channel:02d}.tif"
                tifffile.imwrite(path, np.full((5, 7), 1000 * number + channel, dtype=np.uint16))

    def run_layout(self, *options, raw=None, output=None):
        raw = raw or self.raw
        output = output or self.output
        return subprocess.run(
            [sys.executable, str(RUNNER), "--raw_round_dir", str(raw),
             "--output_dir", str(output), "--channels", "ch03=raw-refDAPI",
             "--manifest_path", str(output / "layout.csv"), *options],
            capture_output=True, text=True, timeout=30,
        )

    def test_links_preserve_fov_identity_pixels_and_idempotence(self):
        self.acquisition(self.raw)
        result = self.run_layout()
        self.assertEqual(result.returncode, 0, result.stderr)
        channel = self.output / "raw-refDAPI"
        self.assertEqual([path.name for path in sorted(channel.iterdir())], ["Position001.tif", "Position003.tif"])
        manifest = self.output / "layout.csv"
        before = manifest.stat().st_mtime_ns
        for path in channel.iterdir():
            self.assertTrue(path.is_symlink())
            source = path.resolve(strict=True)
            np.testing.assert_array_equal(tifffile.imread(path), tifffile.imread(source))
        result = self.run_layout()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(manifest.stat().st_mtime_ns, before)
        with manifest.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([row["position"] for row in rows], ["Position001", "Position003"])
        self.assertEqual({row["layout_mode"] for row in rows}, {"symlink"})

    def test_source_alias_is_resolved_before_link_creation(self):
        self.acquisition(self.raw, positions=(1,))
        alias = self.root / "home_alias"
        alias.symlink_to(self.raw, target_is_directory=True)
        result = self.run_layout(raw=alias)
        self.assertEqual(result.returncode, 0, result.stderr)
        link = self.output / "raw-refDAPI" / "Position001.tif"
        self.assertNotIn("home_alias", os.readlink(link))
        self.assertFalse(link.resolve().is_symlink())

    def test_existing_foreign_targets_and_broken_links_are_preserved(self):
        self.acquisition(self.raw, positions=(1,))
        foreign = self.root / "foreign.tif"
        foreign.write_bytes(b"foreign")
        for kind in ("file", "foreign_link", "broken_link"):
            with self.subTest(kind=kind):
                output = self.root / kind
                target = output / "raw-refDAPI" / "Position001.tif"
                target.parent.mkdir(parents=True)
                if kind == "file":
                    target.write_bytes(b"keep")
                else:
                    target.symlink_to(foreign if kind == "foreign_link" else self.root / "missing")
                result = self.run_layout(output=output)
                self.assertNotEqual(result.returncode, 0)
                if kind == "file":
                    self.assertEqual(target.read_bytes(), b"keep")
                else:
                    self.assertTrue(target.is_symlink())
                    self.assertEqual(os.readlink(target), str(foreign if kind == "foreign_link" else self.root / "missing"))

    def test_channel_directory_symlink_cannot_redirect_output_to_source(self):
        self.acquisition(self.raw, positions=(1,))
        self.output.mkdir(parents=True)
        (self.output / "raw-refDAPI").symlink_to(self.raw / "Position001", target_is_directory=True)
        result = self.run_layout()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.raw / "Position001" / "Position001.tif").exists())

    def test_ambiguous_channel_fails_without_selecting_an_acquisition(self):
        self.acquisition(self.raw, positions=(1,))
        (self.raw / "Position001" / "repeat_ch03.tif").write_bytes(b"second acquisition")
        result = self.run_layout()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.output / "raw-refDAPI" / "Position001.tif").exists())

    def test_unreadable_source_fails(self):
        if os.geteuid() == 0:
            self.skipTest("root can read mode-000 files")
        self.acquisition(self.raw, positions=(1,))
        source, = (self.raw / "Position001").glob("*.tif")
        source.chmod(0)
        try:
            result = self.run_layout()
        finally:
            source.chmod(0o600)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.output / "raw-refDAPI" / "Position001.tif").exists())

    def test_copy_and_explicit_conversion(self):
        self.acquisition(self.raw, positions=(1,))
        source, = (self.raw / "Position001").glob("*.tif")
        for output_format in ("preserve", "uint8"):
            with self.subTest(output_format=output_format):
                output = self.root / output_format
                result = self.run_layout("--layout_mode", "copy", "--output_format", output_format, output=output)
                self.assertEqual(result.returncode, 0, result.stderr)
                target = output / "raw-refDAPI" / "Position001.tif"
                self.assertFalse(target.is_symlink())
                expected = tifffile.imread(source)
                if output_format == "uint8":
                    expected = (expected.astype(np.float32) / 65535 * 255).astype(np.uint8)
                np.testing.assert_array_equal(tifffile.imread(target), expected)
                result = self.run_layout("--layout_mode", "copy", "--output_format", output_format, output=output)
                self.assertNotEqual(result.returncode, 0)

    def test_symlink_cannot_request_conversion(self):
        self.acquisition(self.raw, positions=(1,))
        result = self.run_layout("--output_format", "uint8")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_copy_conversion_preserves_grayscale_z_pages(self):
        position = self.raw / "Position001"
        position.mkdir(parents=True)
        image = np.arange(3 * 5 * 7, dtype=np.uint16).reshape(3, 5, 7)
        tifffile.imwrite(position / "sample_ch03.tif", image, photometric="minisblack")
        result = self.run_layout("--layout_mode", "copy", "--output_format", "uint8")
        self.assertEqual(result.returncode, 0, result.stderr)
        with tifffile.TiffFile(self.output / "raw-refDAPI/Position001.tif") as handle:
            self.assertEqual(len(handle.pages), 3)
            self.assertTrue(all(page.samplesperpixel == 1 for page in handle.pages))

    def test_three_round_wrapper_preserves_each_round_coverage(self):
        sample = self.root / "sample"
        for name, positions, channels in [
            ("round005", (1, 3), (3,)), ("IF", (1, 2, 3), (0, 1, 2, 3)),
            ("round011", (1, 3, 7), (0, 1, 2, 3)),
        ]:
            self.acquisition(sample / "01_data" / name, positions, channels)
        manifest = self.root / "rounds with spaces.csv"
        with manifest.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["role", "rawdata_round", "channel_mode", "subdir"])
            writer.writerows([("ref", "round005", "LeicaRef", "ref"), ("IF", "IF", "LeicaIF", "IF"), ("seqE", "round011", "LeicaSeqE", "seqE")])
        conda = self.root / "conda.sh"
        conda.write_text("conda() { :; }\n")
        environment = os.environ.copy()
        environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment["PATH"]
        environment.update({f"SLURM_{key}": "test" for key in ("JOB_ID", "JOB_NAME", "JOB_USER", "SUBMIT_HOST", "SUBMIT_DIR", "NODELIST", "JOB_NUM_NODES", "JOB_PARTITION", "CPUS_PER_TASK", "JOB_CPUS_PER_NODE")})
        environment["SLURMD_NODENAME"] = "test"
        result = subprocess.run(
            ["bash", str(WRAPPER), "--project_root", str(self.root), "--project_name", "sample",
             "--reg_dir_suffix", "_new", "--stitching_workdir", "A_Fiji", "--round_manifest", str(manifest),
             "--script_dir", str(RUNNER.parent), "--conda_sh", str(conda)],
            env=environment, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = sample / "02_registration_new" / "A_Fiji"
        self.assertEqual(sorted(path.name for path in (output / "ref").iterdir()), ["channel_manifest_round005_preserve.csv", "raw-refDAPI"])
        self.assertEqual(len(list((output / "ref/raw-refDAPI").glob("*.tif"))), 2)
        self.assertEqual(len(list((output / "IF/raw-DAPI").glob("*.tif"))), 3)
        self.assertEqual(len(list((output / "seqE/raw-DAPI").glob("*.tif"))), 3)
        self.assertTrue((output / "IF/raw-488-CD144/Position002.tif").is_symlink())
        self.assertFalse((output / "seqE/raw-Padlayer").exists())
        self.assertEqual(
            {path.name for path in (output / "seqE").iterdir() if path.is_dir()},
            {"raw-647-GCnt", "raw-561-GTrb", "raw-DAPI"},
        )
        for position in (1, 3, 7):
            source_dir = sample / "01_data/round011" / f"Position{position:03d}"
            placeholder = source_dir / f"sample_Position{position:03d}_ch02.tif"
            self.assertTrue(placeholder.is_file())
            np.testing.assert_array_equal(
                tifffile.imread(placeholder), np.full((5, 7), 1000 * position + 2, dtype=np.uint16),
            )
            dapi = output / "seqE/raw-DAPI" / f"Position{position:03d}.tif"
            self.assertEqual(
                dapi.resolve(), (source_dir / f"sample_Position{position:03d}_ch03.tif").resolve(),
            )


    def test_wrapper_rejects_linked_method_path_components(self):
        sample = self.root / "sample"
        for round_name, channels in [("round001", (3,)), ("IF", (0, 1, 2, 3)), ("round011", (0, 1, 2, 3))]:
            self.acquisition(sample / "01_data" / round_name, positions=(1,), channels=channels)
        source_root = sample / "01_data" / "round001"
        before = sorted(str(path.relative_to(source_root)) for path in source_root.rglob("*"))
        method_root = sample / "02_registration_new" / "A_Fiji"
        method_root.parent.mkdir()
        method_root.symlink_to(source_root, target_is_directory=True)
        manifest = self.root / "rounds.csv"
        with manifest.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["role", "rawdata_round", "channel_mode", "subdir"])
            writer.writerows([("ref", "round001", "LeicaRef", "ref"), ("IF", "IF", "LeicaIF", "IF"), ("seqE", "round011", "LeicaSeqE", "seqE")])
        conda = self.root / "conda.sh"
        conda.write_text("conda() { :; }\n")
        environment = os.environ.copy()
        environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment["PATH"]
        environment.update({f"SLURM_{key}": "test" for key in ("JOB_ID", "JOB_NAME", "JOB_USER", "SUBMIT_HOST", "SUBMIT_DIR", "NODELIST", "JOB_NUM_NODES", "JOB_PARTITION", "CPUS_PER_TASK", "JOB_CPUS_PER_NODE")})
        environment["SLURMD_NODENAME"] = "test"
        for workdir, round_options in [
            ("A_Fiji", ["--round_manifest", str(manifest)]),
            ("A_Fiji/child", ["--rawdata_round", "round001", "--channel_mode", "LeicaRef"]),
        ]:
            with self.subTest(workdir=workdir):
                result = subprocess.run(
                    ["bash", str(WRAPPER), "--project_root", str(self.root), "--project_name", "sample",
                     "--reg_dir_suffix", "_new", "--stitching_workdir", workdir, *round_options,
                     "--script_dir", str(RUNNER.parent), "--conda_sh", str(conda)],
                    env=environment, capture_output=True, text=True, timeout=30,
                )
                self.assertNotEqual(result.returncode, 0)
                after = sorted(str(path.relative_to(source_root)) for path in source_root.rglob("*"))
                self.assertEqual(after, before)
                self.assertTrue(method_root.is_symlink())


if __name__ == "__main__":
    unittest.main()
