"""Lock the MCP tool surface against the engine RPC dispatch table.

The MCP bridge (solidifai_mcp/server.py) and the engine RPC dispatch
(solidifai_engine/server.py _HANDLERS) are two hand-maintained surfaces. These
tests fail if they drift: an MCP tool that forwards to a non-existent engine
method, or a new engine method that is neither exposed as an MCP tool nor
explicitly marked RPC-only.
"""

import importlib.util
import re
from pathlib import Path

from solidifai_engine.server import _HANDLERS

# Engine methods intentionally reachable only over the Rust UI RPC, not exposed
# as agent-facing MCP tools. Adding a new engine method forces a conscious choice:
# expose it as an MCP tool, or add it to this allowlist.
RPC_ONLY = {
    "get_protocol_info",
    "ping",
    "set_part_material",
    "list_destinations",
    "set_destinations",
    "dismiss_proposed_name",
    "set_workspace_name",
}


def _mcp_forwarded_methods() -> set[str]:
    """Every engine method the MCP server forwards, parsed from its `_call(...)`
    sites (multiline-aware). Read with explicit utf-8 because OCC/lib3mf can flip
    the process locale to ASCII mid-suite."""
    spec = importlib.util.find_spec("solidifai_mcp.server")
    assert spec and spec.origin, "cannot locate solidifai_mcp.server"
    src = Path(spec.origin).read_text(encoding="utf-8")
    return set(re.findall(r'_call\(\s*["\']([a-z_]+)["\']', src))


def test_every_mcp_tool_targets_a_real_engine_method():
    forwarded = _mcp_forwarded_methods()
    assert forwarded, "no _call targets found; the parser drifted"
    unknown = forwarded - set(_HANDLERS)
    assert not unknown, f"MCP tools call engine methods that do not exist: {sorted(unknown)}"


def test_engine_methods_are_exposed_or_explicitly_rpc_only():
    forwarded = _mcp_forwarded_methods()
    missing = set(_HANDLERS) - forwarded - RPC_ONLY
    assert not missing, (
        "engine methods are neither exposed via MCP nor on the RPC-only allowlist: "
        f"{sorted(missing)}. Add an MCP tool, or list them in RPC_ONLY."
    )


def test_rpc_only_allowlist_is_accurate():
    # The allowlist must not name methods that no longer exist or that are in fact
    # exposed via MCP (which would make the allowlist misleading).
    forwarded = _mcp_forwarded_methods()
    assert set(_HANDLERS) >= RPC_ONLY, "RPC_ONLY names a method not in the dispatch table"
    assert not (RPC_ONLY & forwarded), "RPC_ONLY names a method that IS exposed via MCP"


def test_cad_goto_forwards_to_goto():
    # The solidifai-history skill tells agents to "goto" a history index; the MCP
    # layer must expose a callable tool for it. cad_goto forwards to the goto
    # handler (which Session.goto now implements for assemblies too).
    forwarded = _mcp_forwarded_methods()
    assert "goto" in forwarded, "cad_goto must forward to the engine 'goto' method"
    assert "goto" not in RPC_ONLY, "goto is now MCP-exposed; drop it from RPC_ONLY"
