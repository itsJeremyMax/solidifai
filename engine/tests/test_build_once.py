import textwrap

import solidifai
from solidifai_engine.session import Session

# Legacy model: unguarded module-level build(). Count build() runs via show() calls.
LEGACY = textwrap.dedent("""
    from build123d import Box
    from solidifai import show
    PARAMS = {"w": {"value": 10.0, "min": 5.0, "max": 20.0, "step": 1.0}}
    def build(w):
        show(Box(w, 10, 10), name="Block")
    build(**{k: v["value"] for k, v in PARAMS.items()})
""")


def test_execute_script_builds_once(tmp_path, monkeypatch):
    calls = {"n": 0}
    real_show = solidifai.show

    def counting(*a, **k):
        calls["n"] += 1
        return real_show(*a, **k)

    monkeypatch.setattr(solidifai, "show", counting)
    s = Session(str(tmp_path))
    res = s.execute_script(LEGACY)
    assert res.get("ok") is True, res
    assert calls["n"] == 1, f"build() ran {calls['n']}x (expected 1)"
