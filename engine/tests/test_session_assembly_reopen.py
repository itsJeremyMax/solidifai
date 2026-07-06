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


def test_reopen_reuses_disk_cache(tmp_path):
    root, artifacts = _ws(tmp_path)
    s1 = Session(str(artifacts), model_path=str(root / "assembly.json"))
    s1.startup()  # builds 4 parts, populates disk cache
    s2 = Session(str(artifacts), model_path=str(root / "assembly.json"))
    s2.startup()  # fresh in-memory cache, same disk
    assert s2.last_ok is True
    assert s2._disk_cache.hits >= 4  # all 4 parts served from disk
    assert s2._node_cache.misses == 4  # L1 missed (fresh), L2 served them
