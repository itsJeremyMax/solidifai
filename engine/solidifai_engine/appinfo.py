"""appinfo -- the single accessor for the solidifai release version inside the
engine. The host (Rust) propagates the version at launch via SOLIDIFAI_APP_VERSION,
derived from the app's package_info, which is single-sourced from the root
package.json. When the engine runs standalone (dev, tests, a bare MCP bridge), it
falls back to a dev sentinel. Nothing reads the packaging metadata at runtime.
"""

from __future__ import annotations

import os

ENV_APP_VERSION = "SOLIDIFAI_APP_VERSION"
DEV_VERSION = "0.0.0+dev"


def app_version() -> str:
    """The solidifai release version, or a dev sentinel when not launched by the app."""
    v = os.environ.get(ENV_APP_VERSION)
    return v.strip() if v and v.strip() else DEV_VERSION
