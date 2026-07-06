import os

import solidifai
from solidifai import build_scope


def test_import_cad_records_asset_path(tmp_path):
    from build123d import Box, export_brep

    asset = tmp_path / "fixture.brep"
    export_brep(Box(3, 3, 3), str(asset))
    solidifai.set_workspace_root(str(tmp_path))
    with build_scope() as scope:
        solidifai.import_cad("fixture.brep")
        assert os.path.abspath(str(asset)) in [os.path.abspath(p) for p in scope.assets]


def test_assets_empty_without_import():
    with build_scope() as scope:
        assert scope.assets == []
