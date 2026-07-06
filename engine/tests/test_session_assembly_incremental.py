import os
import shutil

from solidifai_engine.session import Session

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "assembly_enclosure")


def _ws(tmp_path):
    root = tmp_path / "ws"
    shutil.copytree(FIXTURE, root)
    artifacts = root / ".solidifai" / "artifacts"
    artifacts.mkdir(parents=True)
    return root, artifacts


def test_body_h_change_rebuilds_nothing(tmp_path):
    # body_h only moves lid_frame/hinge_frame; no part consumes body_h -> 0 rebuilds
    root, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(root / "assembly.json"))
    sess.startup()
    misses0 = sess._node_cache.misses
    sess.set_params({"body_h": 50.0})
    assert sess._node_cache.misses == misses0  # no kernel rebuilds
    assert sess.last_ok is True


def test_wall_change_rebuilds_base_and_lid_only(tmp_path):
    # base/lid consume wall; pin/knuckle consume pin_d (from body_w) -> only 2 rebuild
    root, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(root / "assembly.json"))
    sess.startup()
    misses0 = sess._node_cache.misses
    sess.set_params({"wall": 3.0})
    assert sess._node_cache.misses == misses0 + 2  # exactly base + lid
