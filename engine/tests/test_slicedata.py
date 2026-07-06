# engine/tests/test_slicedata.py
"""Parsing of OrcaSlicer's exported .3mf metadata into an Estimate dict."""

from pathlib import Path

from solidifai_engine.fabrication import slicedata

FIXTURE = Path(__file__).parent / "fixtures" / "orca" / "sliced_cube_petg.3mf"

# Verified excerpts from the real slice (spike 2026-06-07).
SLICE_INFO = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <plate>
    <metadata key="prediction" value="1685"/>
    <metadata key="weight" value="3.95"/>
    <metadata key="outside" value="false"/>
    <metadata key="support_used" value="false"/>
    <filament id="1" type="PETG" used_m="1.31" used_g="3.95" />
  </plate>
</config>"""

GCODE = """; total layer number: 100
; max_z_height: 20.00
; filament_cost = 24.99
; filament used [g] = 3.95
"""


def test_parse_slice_info():
    out = slicedata.parse_slice_info(SLICE_INFO)
    assert out["timeSeconds"] == 1685
    assert out["filamentGrams"] == 3.95
    assert out["filamentLengthMm"] == 1310.0  # used_m * 1000
    assert out["supportUsed"] is False
    assert out["fitsBed"] is True  # outside == "false"


def test_parse_slice_info_outside_true_means_off_bed():
    xml = SLICE_INFO.replace('key="outside" value="false"', 'key="outside" value="true"')
    assert slicedata.parse_slice_info(xml)["fitsBed"] is False


def test_parse_gcode_footer():
    out = slicedata.parse_gcode_footer(GCODE)
    assert out["layerCount"] == 100
    assert out["heightMm"] == 20.0
    assert out["pricePerKg"] == 24.99


def test_parse_tolerates_missing_fields():
    assert slicedata.parse_slice_info("<config/>") == {}
    assert slicedata.parse_gcode_footer("; nothing here") == {}


def test_build_estimate_computes_cost_and_prefers_real_price():
    info = slicedata.parse_slice_info(SLICE_INFO)
    footer = slicedata.parse_gcode_footer(GCODE)
    est = slicedata.build_estimate(info, footer, price_fallback=99.0)
    assert est["source"] == "slice"
    assert est["timeSeconds"] == 1685
    assert est["layerCount"] == 100
    assert est["heightMm"] == 20.0
    assert est["supportUsed"] is False
    assert est["fitsBed"] is True
    # cost = 3.95 g / 1000 * 24.99 (real filament price wins over fallback)
    assert round(est["cost"], 4) == round(3.95 / 1000 * 24.99, 4)
    assert est["currency"] == "USD"


def test_build_estimate_falls_back_to_provided_price():
    info = {"filamentGrams": 10.0}
    est = slicedata.build_estimate(info, {}, price_fallback=20.0)
    assert est["cost"] == 10.0 / 1000 * 20.0


def test_read_3mf_against_real_fixture():
    xml, gcode = slicedata.read_3mf(str(FIXTURE))
    info = slicedata.parse_slice_info(xml)
    footer = slicedata.parse_gcode_footer(gcode)
    assert info["timeSeconds"] == 1685
    assert info["filamentGrams"] == 3.95
    assert footer["layerCount"] == 100
    assert footer["pricePerKg"] == 24.99
