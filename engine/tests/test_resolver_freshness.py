import json
import os
import textwrap

from solidifai_engine.server import Server

MODEL = textwrap.dedent("""
    from build123d import Box
    from solidifai import show
    PARAMS = {"w": {"value": 10.0, "min": 5.0, "max": 20.0, "step": 1.0}}
    def build(w):
        show(Box(w, 10, 10), name="Block")
    if __name__ == "__main__":
        build(**{k: v["value"] for k, v in PARAMS.items()})
""")


def _ws(tmp):
    root = os.path.join(tmp, "ws")
    os.makedirs(os.path.join(root, ".solidifai", "artifacts"), exist_ok=True)
    with open(os.path.join(root, "model.py"), "w", encoding="utf-8") as f:
        f.write(MODEL)
    return root


def test_material_created_after_start_is_accepted(tmp_path, monkeypatch):
    # Isolate the global library under the tmp HOME so the test is hermetic.
    monkeypatch.setenv("HOME", str(tmp_path))
    root = _ws(str(tmp_path))
    art = os.path.join(root, ".solidifai", "artifacts")
    srv = Server(
        os.path.join(root, ".solidifai", "engine.sock"),
        art,
        model_path=os.path.join(root, "model.py"),
    )
    srv._load_startup_model()

    # Create a workspace material AFTER the engine started.
    with open(os.path.join(root, "materials.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "default": None,
                "materials": [
                    {
                        "id": "teal-petg",
                        "label": "Teal PETG",
                        "base": "petg",
                        "colorHex": "#0aa6a0",
                        "finish": "gloss",
                    }
                ],
            },
            f,
        )

    res = srv._dispatch("set_part_material", {"part_id": "block", "material": "teal-petg"})
    assert res.get("ok") is True, res
