"""Top-level: build a workspace's assembly and render it. The single call the
session/server makes for an assembly-mode workspace."""

from __future__ import annotations

import time

from solidifai_engine import render
from solidifai_engine.assembly import compose, graph


def build_workspace(
    root: str, artifacts_dir: str, *, build_id: int, params: dict | None = None
) -> dict:
    started = time.perf_counter()
    objects = graph.build_node(root, params=params or {}, parent=None)
    duration_ms = int((time.perf_counter() - started) * 1000)
    render.render_to(
        artifacts_dir,
        build_id,
        objects=objects,
        node_ids=compose.path_ids(objects),
        duration_ms=duration_ms,
    )
    return {"ok": True, "buildId": build_id}
