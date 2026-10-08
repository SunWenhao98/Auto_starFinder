"""通过实际 CLI 验证坐标变化、字节保留和禁止覆盖边界。"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "shift_maf_coordinates_CLI.py"
RAW = (
    b'\xef\xbb\xbf<?xml version="1.0"?>\r\n'
    b'<!--keep <XYZStagePointDefinition StageXPos="99" StageYPos="88"/>-->\r\n'
    b'<XYZStagePointDefinitionList StageOrderNumber="0">\r\n'
    b'<XYZStagePointDefinition StageYPos = \'0.040296\' StageXPos="0.041478" '
    b'PositionID="1" Note="StageXPos= &quot;9&quot; >">'
    b'<AdditionalZPosition ZPosition="0.001851927745"/>'
    b'</XYZStagePointDefinition>\r\n'
    b'</XYZStagePointDefinitionList>\r\n'
)


class ShiftMafCoordinatesCliTest(unittest.TestCase):
    def test_zero_shift_preserves_every_byte(self) -> None:
        self.check_success([], RAW)

    def test_signed_shifts_only_change_coordinates(self) -> None:
        expected = RAW.replace(b"0.040296", b"0.040096").replace(b"0.041478", b"0.041578")
        self.check_success(["--x_shift", "0.0001", "--y_shift", "-0.0002"], expected)

    def test_x_only_shift_preserves_y_text(self) -> None:
        self.check_success(["--x_shift", "1e-7"], RAW.replace(b"0.041478", b"0.0414781"))

    def check_success(self, shifts: list[str], expected: bytes) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.maf"
            output = Path(directory) / "output.maf"
            source.write_bytes(RAW)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--input_file", str(source),
                 "--output_file", str(output), *shifts], capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), expected)
            self.assertEqual(source.read_bytes(), RAW)

    def test_invalid_input_does_not_publish_output(self) -> None:
        cases = [
            (RAW, ["--x_shift", "NaN"]),
            (RAW, ["--y_shift", "Infinity"]),
            (RAW.replace(b"0.041478", b"invalid"), []),
            (RAW.replace(b' StageXPos="0.041478"', b""), []),
            (RAW[:-20], []),
        ]
        for raw, shifts in cases:
            with self.subTest(raw=raw, shifts=shifts), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "input.maf"
                output = Path(directory) / "output.maf"
                source.write_bytes(raw)
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--input_file", str(source),
                     "--output_file", str(output), *shifts], capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())
                self.assertEqual(source.read_bytes(), raw)

    def test_existing_output_and_in_place_write_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.maf"
            other = Path(directory) / "existing.maf"
            source.write_bytes(RAW)
            other.write_bytes(b"existing result")
            for output in (source, other):
                with self.subTest(output=output):
                    before = output.read_bytes()
                    result = subprocess.run(
                        [sys.executable, str(SCRIPT), "--input_file", str(source),
                         "--output_file", str(output), "--x_shift", "0.1"],
                        capture_output=True, text=True,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
