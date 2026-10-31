"""验证旧参考轮/新全轮日志均保持计数 schema 和流式解析语义。"""

import importlib.util
from pathlib import Path
import sys

import pytest


RUN_ROOT = Path(__file__).resolve().parents[1]
RELATIVE_PARSER = Path("00_utils/99_logExtraction/parse_pipeline_logs.py")


def load_parser():
    module_name = 'decoding_log_contract'
    spec = importlib.util.spec_from_file_location(module_name, RUN_ROOT / RELATIVE_PARSER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


CANDIDATE = load_parser()
EXPECTED_COLUMNS = ['submit_directory', 'FOV_name', 'SpotsFound_Total', 'Crosstalk_Total', 'Crosstalk_Ratio', 'QCCount_Total', 'QCCount_Total_Ratio', 'ValidQCCount_Total', 'ValidSpots_Total', 'ValidQC_Total_Ratio', 'IntensityQC_Count', 'IntensityQC_Total_Ratio', 'SeqD_SingleCheck_Count_Total', 'SeqF_SingleCheck_Count_Total', 'SeqD_SingleCheck_Prop_Total', 'SeqF_SingleCheck_Prop_Total', 'seqEnd_Count_Total', 'seqEnd_Total_Ratio', 'StrictMatch_Count_Total', 'StrictMatch_Total_Ratio', 'StrictMatch_vs_seqEnd_Ratio']
LEGACY_EXPECTED = [{'submit_directory': 'submit_old', 'FOV_name': 'Position007', 'SpotsFound_Total': '100', 'Crosstalk_Total': '20', 'Crosstalk_Ratio': '0.2', 'QCCount_Total': '70', 'QCCount_Total_Ratio': '0.7', 'ValidQCCount_Total': '70', 'ValidSpots_Total': '80', 'ValidQC_Total_Ratio': '0.875', 'IntensityQC_Count': '42', 'IntensityQC_Total_Ratio': '0.6', 'SeqD_SingleCheck_Count_Total': '30', 'SeqF_SingleCheck_Count_Total': '28', 'SeqD_SingleCheck_Prop_Total': '0.714286', 'SeqF_SingleCheck_Prop_Total': '0.666667', 'seqEnd_Count_Total': '25', 'seqEnd_Total_Ratio': '0.3125', 'StrictMatch_Count_Total': '20', 'StrictMatch_Total_Ratio': '0.25', 'StrictMatch_vs_seqEnd_Ratio': '0.8'}]

def decoding_log(header, new_format):
    timing = "PHASE_TIMING: score_calling_seconds=0.02\n" if new_format else ""
    intensity = (
        "0.600000 [42 / 70] percent of reads have intensity at least 324.000000 in all 11 decoding rounds"
        if new_format else
        "0.600000 [42 / 70] percent of reads have intensity above 324.000000 in Reference Round (Round 1)"
    )
    return (
        f"{header}\n"
        "Geting color sequence for each voxel...\n"
        "Geting max color...\n"
        f"{timing}20 \n"
        "Decoding...\n"
        "PHASE_TIMING: string_decoding_seconds=0.03\n"
        "0.700000 [70 / 100] percent of reads are below score thresh 0.5\n"
        "0.875000 [70 / 80] percent of reads are below score thresh 0.5 of all valid spots\n"
        f"{intensity}\n"
        "0.714286 [30 / 42] percent of reads match seqD barcode pattern NN - ANNNNG - NNNNNN\n"
        "0.666667 [28 / 42] percent of reads match seqF barcode pattern NN - NNNNNN - ANNNNA\n"
        "0.595238 [25 / 42] percent of good reads match barcode pattern NG - ANNNNG - ANNNNA\n"
        "0.476190 [20 / 42] percent of good reads are in codebook\n"
        "0.800000 [20 / 25] percent of form matched reads are in codebook\n"
    )


@pytest.mark.parametrize("header", [
    "选中的 Position 文件夹名称: Position007",
    "POSITION_NAME=Position007",
])
@pytest.mark.parametrize("new_format", [False, True])
def test_full_and_stream_decoding_preserve_counts(tmp_path, header, new_format):
    text = decoding_log(header, new_format)
    path = tmp_path / "synthetic.out"
    path.write_text(text, encoding="utf-8")
    full_rows = CANDIDATE.parse_decoding(text, "submit_test")
    stream_rows = CANDIDATE.parse_decoding_log_stream(path, "submit_test")
    assert len(full_rows) == len(stream_rows) == 1
    assert full_rows == stream_rows
    row = full_rows[0]
    assert list(row) == EXPECTED_COLUMNS
    assert row["SpotsFound_Total"] == "100"
    assert row["Crosstalk_Total"] == "20"
    assert row["IntensityQC_Count"] == "42"
    assert row["IntensityQC_Total_Ratio"] == "0.6"
    assert row["StrictMatch_Count_Total"] == "20"
    assert row["StrictMatch_Total_Ratio"] == "0.25"
    assert row["StrictMatch_vs_seqEnd_Ratio"] == "0.8"


def test_legacy_decoding_remains_identical(tmp_path):
    text = decoding_log("选中的 Position 文件夹名称: Position007", False)
    path = tmp_path / "legacy.out"
    path.write_text(text, encoding="utf-8")
    assert CANDIDATE.parse_decoding(text, "submit_old") == LEGACY_EXPECTED
    assert CANDIDATE.parse_decoding_log_stream(path, "submit_old") == LEGACY_EXPECTED


def test_inline_legacy_crosstalk_is_still_supported(tmp_path):
    text = decoding_log("选中的 Position 文件夹名称: Position007", False)
    text = text.replace("Geting max color...\n20 \nDecoding...", "Geting max color... 20 Decoding...")
    path = tmp_path / "inline.out"
    path.write_text(text, encoding="utf-8")
    assert CANDIDATE.parse_decoding(text, "submit_old") == CANDIDATE.parse_decoding_log_stream(path, "submit_old")
    assert CANDIDATE.parse_decoding(text, "submit_old")[0]["Crosstalk_Total"] == "20"
