"""Per-workspace scratch directory under ``<root>/.solidifai/tmp``.

The scratch tree holds engine-generated artifacts that are NOT durable model
state: captured view images and default-location exports. It is cleared on
engine startup (= reset on workspace open) and never reaches the user's repo
(``.solidifai/`` is outside the workspace git allowlist).

This module is intentionally dependency-free (no build123d, no VTK) so it stays
trivially unit-testable. The scratch dir is derived as a sibling of the
artifacts dir, so it needs no extra launch argument.
"""

from __future__ import annotations

import os
import re
import shutil


def scratch_dir(artifacts_dir: str) -> str:
    """``<.solidifai>/tmp`` — sibling of the artifacts dir."""
    return os.path.join(os.path.dirname(os.path.abspath(artifacts_dir)), "tmp")


def views_dir(artifacts_dir: str, build_id: int) -> str:
    """``tmp/views/<build_id>`` — created on demand."""
    d = os.path.join(scratch_dir(artifacts_dir), "views", str(build_id))
    os.makedirs(d, exist_ok=True)
    return d


def exports_dir(artifacts_dir: str) -> str:
    """``tmp/exports`` — created on demand."""
    d = os.path.join(scratch_dir(artifacts_dir), "exports")
    os.makedirs(d, exist_ok=True)
    return d


def clear_scratch(artifacts_dir: str) -> None:
    """Remove and recreate ``tmp/``. Idempotent; best-effort (never raises on a
    missing tree). Only ``tmp/`` is touched — ``artifacts/`` is left alone."""
    d = scratch_dir(artifacts_dir)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)


def slug(name: str) -> str:
    """Filesystem-safe slug for export filenames. Mirrors ``render._slug``."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return s or "model"
