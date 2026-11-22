"""Real grayscale TIFF contracts for the Ashlar readers.

Run in the activated ashlar environment on a compute node. These tests use
single-channel YX images and ZYX page stacks, including generic page metadata.
"""

import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
import tifffile


ROOT = Path(__file__).resolve().parents[1] / "02_FovIntegration"
READER_SPECS = (
    ("p22_ashlar_stitch_initial.py", "TiffTxtReader"),
    ("p24_ashlar_stitch_mosaic.py", "TiffDirectReader"),
    ("p30_ashlar_stitch_mst.py", "TiffTxtReader"),
    ("p32_ashlar_stitch_mosaic_joint.py", "TiffDirectReader"),
)


class AshlarTiffReaderContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readers = {}
        for filename, reader_name in READER_SPECS:
            spec = importlib.util.spec_from_file_location(Path(filename).stem, ROOT / filename)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            cls.readers[filename] = getattr(module, reader_name)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ashlar_gray_reader_")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.config = self.work / "initial.txt"
        self.config.write_text("dim = 3\n\nPosition001.tif; ; (17, 23, 0)\n")

    def write_input(self, depth, dtype, explicit_axes=False):
        yy, xx = np.indices((48, 80))
        volume = np.stack([
            (yy * (z + 1) + xx * (z + 3) + z * 19) % 200 + 20
            for z in range(depth or 1)
        ])
        if dtype == np.uint16:
            volume *= 127
        volume = volume.astype(dtype)
        image = volume[0] if depth is None else volume
        metadata = {"axes": "ZYX"} if explicit_axes else None
        tifffile.imwrite(
            self.work / "Position001.tif", image,
            photometric="minisblack", metadata=metadata,
        )
        return volume

    def test_depth_tile_size_and_all_read_modes_preserve_gray_pixels(self):
        cases = (
            (None, np.uint8, False),
            (3, np.uint16, True),
            (4, np.uint8, False),
            (5, np.uint16, True),
            (45, np.uint16, False),
        )
        for depth, dtype, explicit_axes in cases:
            volume = self.write_input(depth, dtype, explicit_axes)
            for filename, reader_type in self.readers.items():
                with self.subTest(reader=filename, depth=depth, dtype=np.dtype(dtype).name):
                    mip = reader_type(self.work, self.config, mode="mip")
                    self.assertEqual(mip.z_depth, len(volume))
                    np.testing.assert_array_equal(mip.metadata.size, (48, 80))
                    np.testing.assert_array_equal(mip.metadata.positions, [[23, 17]])
                    self.assertEqual(mip.metadata.num_channels, 1)
                    self.assertEqual(mip.metadata.pixel_dtype, volume.dtype)
                    np.testing.assert_array_equal(mip.read(0, 0), volume.max(axis=0))

                    slice_index = (len(volume) + 1) // 2
                    selected = reader_type(
                        self.work, self.config, mode="slice", slice_index=slice_index,
                    )
                    np.testing.assert_array_equal(
                        selected.read(0, 0), volume[slice_index - 1],
                    )

                    stack = reader_type(self.work, self.config, mode="stack")
                    self.assertEqual(stack.metadata.num_channels, len(volume))
                    for z_index, plane in enumerate(volume):
                        np.testing.assert_array_equal(stack.read(0, z_index), plane)

    def test_three_plane_nonsquare_images_rotate_clockwise_after_z_selection(self):
        volume = self.write_input(3, np.uint16, True)
        for filename, reader_type in self.readers.items():
            for mode, kwargs, channel, expected in (
                ("mip", {}, 0, volume.max(axis=0)),
                ("slice", {"slice_index": 2}, 0, volume[1]),
                ("stack", {}, 1, volume[1]),
            ):
                with self.subTest(reader=filename, mode=mode):
                    reader = reader_type(
                        self.work, self.config, mode=mode, rotate90=True, **kwargs,
                    )
                    np.testing.assert_array_equal(reader.metadata.size, (80, 48))
                    np.testing.assert_array_equal(
                        reader.read(0, channel), np.rot90(expected, k=-1),
                    )


if __name__ == "__main__":
    unittest.main()
