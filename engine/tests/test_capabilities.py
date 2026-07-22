import importlib.util
import json
import re
from pathlib import Path

import pytest

from solidifai_engine.capabilities import assess_design_plan, engine_capabilities
from solidifai_engine.server import _HANDLERS, _PARENT_READ_METHODS, Server


def _mcp_tool_names() -> set[str]:
    spec = importlib.util.find_spec("solidifai_mcp.server")
    assert spec and spec.origin, "cannot locate solidifai_mcp.server"
    src = Path(spec.origin).read_text(encoding="utf-8")
    return set(re.findall(r"@mcp\.tool\(\)\s*\ndef ([a-z_]+)", src))


def test_engine_capabilities_exposes_versioned_contract_sections():
    capabilities = engine_capabilities()

    assert capabilities["version"] == 1
    assert capabilities["geometry"]["representation"] == "parametric-solid-modeling"
    assert capabilities["assemblies"]["placement"] == "frame-driven"
    assert capabilities["parameters"]["supported"] == ["numeric", "boolean", "enum"]
    assert capabilities["verification"]["motion"]["continuousProof"] is False
    assert capabilities["fallbacks"]["unsupported"][0] == "approximate_with_parametric_primitives"


def test_engine_capabilities_documents_schema_shapes_operations_io_and_verification_levels():
    capabilities = engine_capabilities()

    assert capabilities["parameters"]["schemas"] == {
        "numeric": {
            "value": "number",
            "min": "number",
            "max": "number",
            "step": "number",
            "unit": "string?",
            "desc": "string?",
        },
        "boolean": {"type": "boolean", "value": "bool", "desc": "string?"},
        "enum": {
            "type": "enum",
            "value": "string",
            "choices": "list[string]",
            "desc": "string?",
        },
    }
    operations = capabilities["operations"]
    assert set(operations) == {"families", "excludedFamilies"}
    assert set(operations["families"]) == {
        "capability",
        "modeling",
        "inspection",
        "requirements",
        "search",
        "imports",
        "assemblies",
        "async",
        "support",
    }
    assert set(operations["excludedFamilies"]) == {"metadata", "history", "fabrication"}
    assert "get_engine_capabilities" in operations["families"]["capability"]
    assert "assess_design_plan" in operations["families"]["capability"]
    assert "execute_script" in operations["families"]["modeling"]
    assert "capture_views" in operations["families"]["modeling"]
    assert "create_drawing" in operations["families"]["modeling"]
    assert "measure_between" in operations["families"]["inspection"]
    assert "query_faces" in operations["families"]["inspection"]
    assert "check_motion" in operations["families"]["inspection"]
    assert "set_requirements" in operations["families"]["requirements"]
    assert "check_requirements" in operations["families"]["requirements"]
    assert "get_conformance" in operations["families"]["requirements"]
    assert "lookup_standard" in operations["families"]["search"]
    assert "lookup_reference" in operations["families"]["search"]
    assert "save_reference" in operations["families"]["search"]
    assert "stage_import" in operations["families"]["imports"]
    assert "set_skeleton" in operations["families"]["assemblies"]
    assert "check_interfaces" in operations["families"]["assemblies"]
    assert "submit_operation" in operations["families"]["async"]
    assert "cancel_operation" in operations["families"]["async"]
    assert operations["families"]["support"] == ["report_issue"]


def test_engine_capability_operations_match_intended_mcp_tool_surface():
    capabilities = engine_capabilities()
    operations = capabilities["operations"]
    documented = {name for family in operations["families"].values() for name in family}
    excluded = {name for family in operations["excludedFamilies"].values() for name in family}
    mcp_tools = _mcp_tool_names()

    assert documented & excluded == set()
    assert documented | excluded == mcp_tools, (
        "capability catalog must account for the full intended MCP tool surface via either "
        "semantic operation families or explicit exclusions"
    )
    assert "get_workspace_meta" in excluded and "set_workspace_meta" in excluded
    assert "cad_history" in excluded and "fab_detect" in excluded
    assert capabilities["imports"] == {
        "roles": {
            "reference": "supported",
            "modifiable_brep_step": "conditional",
            "svg_3d_reference": "unsupported",
        },
        "limitations": [
            "reference imports are measurable fixtures but are never directly edited",
            "editable import workflows require a supported solid CAD import plus"
            " model-script reconstruction",
        ],
    }
    assert capabilities["exports"] == {
        "roles": {
            "exchange": ["step", "brep"],
            "manufacturing": ["stl", "3mf"],
            "visualization": ["glb", "gltf"],
        }
    }
    assert capabilities["verification"] == {
        "geometry": {
            "level": "exact-brep",
            "checks": ["measure", "measure_between", "thickness_at"],
        },
        "assemblies": {
            "level": "exact-placement-with-sampled-motion",
            "checks": ["check_interferences", "check_interfaces"],
        },
        "motion": {
            "level": "sampled",
            "continuousProof": False,
            "verifiedJoints": ["rigid", "revolute", "slider"],
            "unsupportedJoints": ["ball", "cylindrical", "planar"],
        },
        "dfm": {"fdm": "supported", "non_fdm": "unsupported"},
        "structural": {"fea": "unsupported"},
    }


def test_engine_capabilities_exposes_stable_initial_intent_taxonomy():
    capabilities = engine_capabilities()

    assert sorted(capabilities["intents"]) == [
        "ball_joint_articulation",
        "boolean_enum_editable_params",
        "continuous_collision_proof",
        "controlled_organic_loft",
        "fdm_dfm_validation",
        "frame_assembly",
        "freeform_fitted_surface",
        "mesh_editing",
        "non_fdm_dfm_validation",
        "revolute_sampled_motion",
        "sculpt_subd_modeling",
        "simple_prismatic_part",
        "solved_mates_constraint_solver",
        "step_brep_modification",
        "structural_fea",
        "svg_3d_reference",
    ]


def test_assess_design_plan_classifies_supported_and_conditional_and_unsupported_and_unknown():
    assessment = assess_design_plan(
        [
            "simple_prismatic_part",
            "step_brep_modification",
            "continuous_collision_proof",
            "totally_new_intent",
        ]
    )

    assert assessment["summary"] == {
        "status": "unsupported",
        "counts": {"supported": 1, "conditional": 1, "unsupported": 1, "unknown": 1},
    }
    assert assessment["intents"] == [
        {
            "intent": "simple_prismatic_part",
            "status": "supported",
            "limitations": [],
            "fallbacks": [],
        },
        {
            "intent": "step_brep_modification",
            "status": "conditional",
            "limitations": [
                "imported solids can be staged and rebuilt around, but direct feature"
                " editing is not guaranteed"
            ],
            "fallbacks": ["rebuild_parametrically_around_import", "author_externally_and_import"],
        },
        {
            "intent": "continuous_collision_proof",
            "status": "unsupported",
            "limitations": ["motion verification is sampled and cannot prove continuous clearance"],
            "fallbacks": ["accept_sampled_motion_check", "decline_request"],
        },
        {
            "intent": "totally_new_intent",
            "status": "unknown",
            "limitations": ["intent is not recognized by the deterministic capability catalog"],
            "fallbacks": ["map_request_to_known_intents", "decline_request"],
        },
    ]


def test_assess_design_plan_covers_requested_audit_scenarios():
    assessment = assess_design_plan(
        [
            "simple_prismatic_part",
            "controlled_organic_loft",
            "freeform_fitted_surface",
            "sculpt_subd_modeling",
            "mesh_editing",
            "frame_assembly",
            "solved_mates_constraint_solver",
            "revolute_sampled_motion",
            "ball_joint_articulation",
            "continuous_collision_proof",
            "fdm_dfm_validation",
            "non_fdm_dfm_validation",
            "structural_fea",
            "step_brep_modification",
            "svg_3d_reference",
            "boolean_enum_editable_params",
        ]
    )

    statuses = {item["intent"]: item["status"] for item in assessment["intents"]}
    assert statuses == {
        "simple_prismatic_part": "supported",
        "controlled_organic_loft": "conditional",
        "freeform_fitted_surface": "unsupported",
        "sculpt_subd_modeling": "unsupported",
        "mesh_editing": "unsupported",
        "frame_assembly": "supported",
        "solved_mates_constraint_solver": "unsupported",
        "revolute_sampled_motion": "supported",
        "ball_joint_articulation": "unsupported",
        "continuous_collision_proof": "unsupported",
        "fdm_dfm_validation": "supported",
        "non_fdm_dfm_validation": "unsupported",
        "structural_fea": "unsupported",
        "step_brep_modification": "conditional",
        "svg_3d_reference": "unsupported",
        "boolean_enum_editable_params": "supported",
    }
    assert assessment["summary"] == {
        "status": "unsupported",
        "counts": {"supported": 5, "conditional": 2, "unsupported": 9, "unknown": 0},
    }


def test_get_engine_capabilities_handler_returns_the_same_catalog_shape():
    server = Server("/tmp/engine.sock", "/tmp/artifacts")
    try:
        assert _HANDLERS["get_engine_capabilities"](server, {}) == engine_capabilities()
    finally:
        server.shutdown()


def test_assess_design_plan_handler_rejects_invalid_intents_payload(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    try:
        response = server._handle_line(
            b'{"id":1,"method":"assess_design_plan","params":{"intents":"not-a-list"}}'
        )
        assert response == {
            "id": 1,
            "ok": False,
            "error": "ValueError: intents must be a list of strings",
        }
    finally:
        server.shutdown()


def test_assess_design_plan_handler_rejects_non_string_intents(tmp_path):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    try:
        response = server._handle_line(
            b'{"id":1,"method":"assess_design_plan","params":{"intents":["simple_prismatic_part",7]}}'
        )
        assert response == {
            "id": 1,
            "ok": False,
            "error": "ValueError: intents must be a list of strings",
        }
    finally:
        server.shutdown()


@pytest.mark.parametrize(
    ("intents", "message"),
    [
        ([""] * 257, "intents must contain at most 256 entries"),
        (["x" * 129], "each intent must be at most 128 characters"),
    ],
)
def test_assess_design_plan_handler_bounds_intent_expansion(tmp_path, intents, message):
    server = Server(str(tmp_path / "engine.sock"), str(tmp_path / "artifacts"))
    try:
        payload = json.dumps(
            {"id": 1, "method": "assess_design_plan", "params": {"intents": intents}}
        ).encode()
        response = server._handle_line(payload)
        assert response == {"id": 1, "ok": False, "error": f"ValueError: {message}"}
    finally:
        server.shutdown()


def test_capability_methods_are_registered_as_parent_owned_reads():
    assert "get_engine_capabilities" in _HANDLERS
    assert "assess_design_plan" in _HANDLERS
    assert "get_engine_capabilities" in _PARENT_READ_METHODS
    assert "assess_design_plan" in _PARENT_READ_METHODS
