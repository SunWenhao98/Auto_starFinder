import importlib.util
import tempfile
import unittest
from pathlib import Path

import xml.etree.ElementTree as ET


MODULE_PATH = Path(__file__).resolve().parents[1] / "extract_maf_intervals_CLI.py"
ROOT_MARKER = b"<XYZStagePointDefinitionList"
PREAMBLE = (
    b'<?xml version="1.0"?>\n'
    b"<!--Leica Application Suite X (LAS X)-->\n"
    b"<!--Leica Microsystems CMS GmbH-->\n"
    b"<!--http://www.confocal-microscopy.com-->\n"
    b"<!--LAS X 4.6.1.27508-->\n"
)


def load_module():
    spec = importlib.util.spec_from_file_location("extract_maf_intervals_CLI", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_synthetic_maf(path: Path) -> bytes:
    points = "".join(
        f'<XYZStagePointDefinition PositionIdentifier="Position{position}" '
        f'PositionID="{position}" StageXPos="{position}.0" StageYPos="{position}.0" />'
        for position in range(1, 7)
    )
    raw_bytes = PREAMBLE + f"<XYZStagePointDefinitionList>{points}</XYZStagePointDefinitionList>".encode()
    path.write_bytes(raw_bytes)
    return raw_bytes


class ExtractMafIntervalsCliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_parse_position_ranges_accepts_singletons_ranges_and_spaces(self):
        result = self.module.parse_position_ranges("1, 3-4, 4 - 5")
        self.assertEqual(result, {1, 3, 4, 5})

    def test_parse_position_ranges_rejects_reversed_range(self):
        with self.assertRaises(ValueError):
            self.module.parse_position_ranges("5-3")

    def test_extracts_union_and_preserves_original_preamble(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.maf"
            output_path = temp_path / "selected.maf"
            input_bytes = write_synthetic_maf(input_path)

            stats = self.module.extract_maf_positions(input_path, output_path, {1, 3, 4, 6})

            output_bytes = output_path.read_bytes()
            root = ET.fromstring(output_bytes)
            position_ids = [int(point.get("PositionID")) for point in root]
            input_preamble = input_bytes[:input_bytes.find(ROOT_MARKER)]
            output_preamble = output_bytes[:output_bytes.find(ROOT_MARKER)]
            self.assertEqual(position_ids, [1, 3, 4, 6])
            self.assertEqual(input_preamble, output_preamble)
            self.assertEqual(stats["initial_count"], 6)
            self.assertEqual(stats["requested_count"], 4)
            self.assertEqual(stats["kept_count"], 4)
            self.assertEqual(stats["removed_count"], 2)

    def test_missing_position_and_existing_output_fail_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.maf"
            missing_output_path = temp_path / "missing.maf"
            write_synthetic_maf(input_path)

            with self.subTest("missing position"):
                with self.assertRaises(ValueError):
                    self.module.extract_maf_positions(input_path, missing_output_path, {1, 7})
                self.assertFalse(missing_output_path.exists())

            with self.subTest("existing output"):
                existing_output_path = temp_path / "existing.maf"
                existing_output_path.write_bytes(b"keep this file")
                with self.assertRaises(FileExistsError):
                    self.module.extract_maf_positions(input_path, existing_output_path, {1})
                self.assertEqual(existing_output_path.read_bytes(), b"keep this file")


if __name__ == "__main__":
    unittest.main()
