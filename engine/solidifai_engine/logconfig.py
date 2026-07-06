"""Engine logging configuration.

Logs go to ``<workspace>/.solidifai/logs/engine.log`` (size-rotated) plus stderr,
so a field failure leaves a trail next to the workspace it happened in. Level is
INFO by default, overridable via the ``SOLIDIFAI_LOG`` env var. Best-effort: if
the log directory cannot be created, stderr logging still works.

Tests do not call ``setup_logging`` (they run module loggers at Python defaults),
so this never interferes with the suite.
"""

from __future__ import annotations

import logging
import logging.handlers
import os

_CONFIGURED = False
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(artifacts_dir: str) -> None:
    """Configure the ``solidifai_engine`` logger once, at engine startup."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    level_name = os.environ.get("SOLIDIFAI_LOG", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    log = logging.getLogger("solidifai_engine")
    log.setLevel(level)
    log.propagate = False
    formatter = logging.Formatter(_FORMAT)

    stderr = logging.StreamHandler()
    stderr.setFormatter(formatter)
    log.addHandler(stderr)

    # Artifacts live at <root>/.solidifai/artifacts; put logs alongside at
    # <root>/.solidifai/logs so they travel with the workspace.
    try:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(artifacts_dir)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, "engine.log"),
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        log.addHandler(file_handler)
    except OSError:
        log.warning("could not open engine log file; logging to stderr only", exc_info=True)
