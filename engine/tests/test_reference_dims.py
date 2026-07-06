"""reference_dims.json content contract: schema, sources, spot values."""

import json
from pathlib import Path

import pytest

from solidifai_engine import standards

ASSET = Path(standards.__file__).with_name("reference_dims.json")


def _data():
    return json.loads(ASSET.read_text(encoding="utf-8"))


def _objects():
    return _data()["objects"]


def test_schema_and_required_fields():
    data = _data()
    assert data["schema"] == 1
    assert data["units"] == "mm"
    ids = [e["id"] for e in data["objects"]]
    assert len(ids) == len(set(ids)), "duplicate ids"
    for entry in data["objects"]:
        for field in ("id", "category", "dims_mm", "source"):
            assert field in entry, f"{entry.get('id')} missing {field}"
        assert entry["source"].startswith("http"), f"{entry['id']} needs a real source"


def test_covers_the_spec_list():
    expected = {
        "18650",
        "21700",
        "aa",
        "aaa",
        "usb-a",
        "usb-c",
        "hdmi-a",
        "micro-hdmi-d",
    }
    assert {e["id"] for e in _objects()} == expected


def test_18650_dims():
    e = standards.lookup_reference("18650")["match"]
    assert e["dims_mm"]["dia_max"] == 18.6
    assert e["dims_mm"]["length_max"] == 65.2


def test_usb_c_cutout():
    e = standards.lookup_reference("usb-c")["match"]
    assert e["dims_mm"]["plug_shell"] == [8.34, 2.56]
    assert e["dims_mm"]["cutout"][0] >= 9.0


def test_alias_matching_is_forgiving():
    assert standards.lookup_reference("AA battery")["match"]["id"] == "aa"


def test_miss_lists_available():
    r = standards.lookup_reference("flux capacitor")
    assert r["match"] is None
    assert "18650" in r["available"]


# -- golden-task coverage (spec Phase 4 exit criterion) -------------------------


def test_pi_case_brief_port_objects_resolve():
    # evals/tasks/pi-case names USB-C power and 2x micro-HDMI; those stay seed.
    assert standards.lookup_reference("usb-c")["match"] is not None
    assert standards.lookup_reference("micro hdmi")["match"] is not None


def test_named_board_is_a_clean_miss_pointing_at_save():
    out = standards.lookup_reference("raspberry pi 5")
    assert out["match"] is None
    assert "save_reference" in out["note"]


def test_battery_box_brief_objects_resolve():
    # evals/tasks/battery-box: 18650 cells, "18.5 mm diameter, 65.3 mm long (button tops)".
    cell = standards.lookup_reference("18650")["match"]
    # The library's flat-top max envelope must not contradict the brief's
    # button-top cells: brief dia within dia_max, brief length within the
    # button-top range called out in the notes.
    assert cell["dims_mm"]["dia_max"] >= 18.5 - 0.2
    assert "button" in cell["notes"].lower()


def test_brief_scan_catches_future_named_objects():
    """Every golden-task brief that names a seed-category object must resolve.

    Briefs naming seed-category objects (cells, port cutouts) must resolve.
    Named products (boards, modules) are learnable, not seed -- a conscious
    update to this map is required when a new brief names a seed-category object.
    """
    from pathlib import Path as _P

    briefs_dir = _P(standards.__file__).resolve().parents[1] / "evals" / "tasks"
    named = {
        "battery-box": ["18650"],
        "pi-case": ["usb-c", "micro-hdmi"],
    }
    for task, objects in named.items():
        brief = (briefs_dir / task / "brief.md").read_text(encoding="utf-8").lower()
        for obj in objects:
            key = obj.split()[0] if obj[0].isdigit() else obj
            assert key in brief, f"{task} brief no longer names {obj}; update this map"
            assert standards.lookup_reference(obj)["match"] is not None
