"""Test isolation for module globals that production code sets per build.

Several tests reconfigure `materials.RESOLVER` (via configure_resolver / Server),
and any test that runs a Session build sets `solidifai.imports._WORKSPACE_ROOT`
(the engine sets it before every build and never clears it, since in production
the next build always re-sets it). A test that leaves either mutated would leak
into later tests — e.g. a leaked workspace root with a tight-fit manufacturing
profile changes `std`/`hardware` clearance holes. Snapshot and restore both
around every test."""

import pytest

from solidifai import imports as solidifai_imports
from solidifai_engine import materials


@pytest.fixture(autouse=True)
def _isolate_module_globals():
    saved_resolver = materials.RESOLVER
    saved_root = solidifai_imports.workspace_root()
    try:
        yield
    finally:
        materials.RESOLVER = saved_resolver
        solidifai_imports.set_workspace_root(saved_root)
