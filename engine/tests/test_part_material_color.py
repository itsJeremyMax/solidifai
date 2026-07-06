import json

from build123d import Box

import solidifai
from solidifai_engine import materials
from solidifai_engine.render import _node_ids, render_to


def test_override_color_wins_over_show_color(tmp_path):
    art = str(tmp_path)
    solidifai.reset_registry()
    # Author tints a part teal via show(color=...).
    solidifai.show(Box(10, 10, 10), name="Plate", material="nylon", color=(0.10, 0.34, 0.40))
    node = _node_ids(list(solidifai._registry()))[0]

    # A library material carrying its OWN near-black color.
    lib = tmp_path / "materials.json"
    lib.write_text(
        json.dumps(
            {
                "default": None,
                "materials": [
                    {
                        "id": "matte-black",
                        "label": "Matte Black",
                        "base": "pla",
                        "colorHex": "#101010",
                        "finish": "matte",
                    }
                ],
            }
        )
    )
    # The conftest autouse fixture restores materials.RESOLVER after the test.
    materials.RESOLVER = materials.MaterialResolver(
        [materials.BuiltinSource(), materials.JsonFileSource(str(lib))]
    )

    render_to(art, 1, overrides={node: "matte-black"})
    model = json.loads((tmp_path / "model.json").read_text())
    base = model["objects"][0]["appearance"]["baseColor"]
    # The override's own near-black color must win, not the author's teal.
    assert max(base) < 0.05, base
