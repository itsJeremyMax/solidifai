import os

from solidifai_engine import scratch


def _artifacts(tmp_path):
    # Mirror the real layout: <root>/.solidifai/artifacts. The scratch dir is a
    # sibling: <root>/.solidifai/tmp.
    dot = tmp_path / ".solidifai"
    artifacts = dot / "artifacts"
    os.makedirs(artifacts, exist_ok=True)
    return str(artifacts)


def test_scratch_dir_is_sibling_of_artifacts(tmp_path):
    artifacts = _artifacts(tmp_path)
    assert scratch.scratch_dir(artifacts) == os.path.join(os.path.dirname(artifacts), "tmp")


def test_views_and_exports_dirs_created_on_demand(tmp_path):
    artifacts = _artifacts(tmp_path)
    v = scratch.views_dir(artifacts, 7)
    e = scratch.exports_dir(artifacts)
    assert v.endswith(os.path.join("tmp", "views", "7"))
    assert e.endswith(os.path.join("tmp", "exports"))
    assert os.path.isdir(v)
    assert os.path.isdir(e)


def test_clear_scratch_empties_tmp_but_not_artifacts(tmp_path):
    artifacts = _artifacts(tmp_path)
    # Put a file in artifacts (must survive) and one in scratch (must be cleared).
    keep = os.path.join(artifacts, "model.glb")
    open(keep, "w").close()
    junk = os.path.join(scratch.views_dir(artifacts, 1), "old.png")
    open(junk, "w").close()

    scratch.clear_scratch(artifacts)

    assert os.path.exists(keep), "artifacts must not be touched"
    assert not os.path.exists(junk), "scratch must be cleared"
    assert os.path.isdir(scratch.scratch_dir(artifacts)), "tmp recreated empty"


def test_clear_scratch_idempotent_on_missing_dir(tmp_path):
    artifacts = _artifacts(tmp_path)
    # No tmp/ yet -> must not raise.
    scratch.clear_scratch(artifacts)
    scratch.clear_scratch(artifacts)
    assert os.path.isdir(scratch.scratch_dir(artifacts))


def test_slug_is_filesystem_safe(tmp_path):
    assert scratch.slug("My Part v2!") == "my_part_v2"
    assert scratch.slug("") == "model"
