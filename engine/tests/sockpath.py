"""Short AF_UNIX socket paths for tests.

macOS caps sun_path at ~104 bytes, and pytest's tmp_path under the stock
per-user TMPDIR (/var/folders/...) blows past it once pytest appends
pytest-of-<user>/pytest-N/<testname>. CI sidesteps this with a short
--basetemp, but a fresh `uv run pytest` must also work without it: bind
sockets under tmp_path only when the full path fits, else in a short
mkdtemp dir (mkdtemp honors TMPDIR, /tmp as a last resort) removed at exit.
"""

import atexit
import os
import shutil
import tempfile

_SUN_PATH_BUDGET = 100  # conservative vs the 104-byte macOS cap


def short_socket_path(tmp_path, name: str = "engine.sock") -> str:
    path = str(tmp_path / name)
    if len(path) <= _SUN_PATH_BUDGET:
        return path
    d = tempfile.mkdtemp(prefix="sfai-")
    if len(os.path.join(d, name)) > _SUN_PATH_BUDGET:
        shutil.rmtree(d, ignore_errors=True)
        d = tempfile.mkdtemp(prefix="sfai-", dir="/tmp")
    atexit.register(shutil.rmtree, d, ignore_errors=True)
    return os.path.join(d, name)
