from solidifai_engine.assembly.cache import NodeCache, part_key


def test_part_key_stable_for_same_inputs():
    k1 = part_key("def build(i): ...", {"body_w": 80.0, "wall": 2.4})
    k2 = part_key("def build(i): ...", {"wall": 2.4, "body_w": 80.0})  # order-independent
    assert k1 == k2


def test_part_key_differs_on_source_or_inputs():
    base = part_key("SRC-A", {"w": 1.0})
    assert part_key("SRC-B", {"w": 1.0}) != base  # source changed
    assert part_key("SRC-A", {"w": 2.0}) != base  # input value changed
    assert part_key("SRC-A", {"w": 1.0, "x": 0.0}) != base  # input set changed


def test_cache_get_put_and_counters():
    c = NodeCache()
    assert c.get("k") is None
    assert c.misses == 1 and c.hits == 0
    c.put("k", ["obj"])
    assert c.get("k") == ["obj"]
    assert c.hits == 1


def test_key_includes_assets():
    from solidifai_engine.assembly.cache import part_key

    base = part_key("SRC", {"w": 1.0}, path="parts/a.py", assets={})
    assert part_key("SRC", {"w": 1.0}, path="parts/a.py", assets={"a.brep": "h1"}) != base
    assert part_key("SRC", {"w": 1.0}, path="parts/a.py", assets={"a.brep": "h2"}) != part_key(
        "SRC", {"w": 1.0}, path="parts/a.py", assets={"a.brep": "h1"}
    )


def test_key_non_numeric_scalar_does_not_crash():
    from solidifai_engine.assembly.cache import part_key

    k = part_key("SRC", {"mode": "fast", "w": 2.0})  # string scalar tolerated
    assert isinstance(k, str)


def test_asset_fingerprint_changes_with_content(tmp_path):
    from solidifai_engine.assembly.cache import asset_fingerprint

    f = tmp_path / "a.brep"
    f.write_text("one", encoding="utf-8")
    fp1 = asset_fingerprint([str(f)])
    f.write_text("two", encoding="utf-8")
    fp2 = asset_fingerprint([str(f)])
    assert fp1 != fp2
