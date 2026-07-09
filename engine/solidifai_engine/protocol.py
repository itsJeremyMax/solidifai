"""RPC contract revision shared between the engine and the Rust host shell.

The Rust supervisor probes ``PROTOCOL_VERSION`` at startup and refuses to run an
engine whose value does not match the one it was built against (see
``EXPECTED_ENGINE_PROTOCOL`` in ``src-tauri/src/engine.rs``). That turns a stale
engine -- typically an out-of-date ``engine-dist`` bundle that predates a feature
-- into a loud, actionable error instead of new RPC methods silently failing as
"unknown method" at call time.

Bump this AND ``EXPECTED_ENGINE_PROTOCOL`` in engine.rs together whenever the RPC
method contract changes (a handler added, removed, or renamed in
``server.py`` ``_HANDLERS``).
"""

from __future__ import annotations

PROTOCOL_VERSION = 11
