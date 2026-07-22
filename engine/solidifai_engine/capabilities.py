"""Machine-readable engine capability catalog and deterministic intent assessment."""

from __future__ import annotations

from copy import deepcopy
from typing import Final, Literal, TypedDict

CapabilityStatus = Literal["supported", "conditional", "unknown", "unsupported"]


class IntentAssessment(TypedDict):
    status: CapabilityStatus
    limitations: list[str]
    fallbacks: list[str]


class AssessedIntent(IntentAssessment):
    intent: str


class AssessmentCounts(TypedDict):
    supported: int
    conditional: int
    unsupported: int
    unknown: int


_INTENT_ASSESSMENTS: Final[dict[str, IntentAssessment]] = {
    "simple_prismatic_part": {
        "status": "supported",
        "limitations": [],
        "fallbacks": [],
    },
    "controlled_organic_loft": {
        "status": "conditional",
        "limitations": [
            "organic forms must still be approximated with deterministic lofts,"
            " sweeps, and guide geometry"
        ],
        "fallbacks": ["decompose_into_guided_lofts", "approximate_with_parametric_primitives"],
    },
    "freeform_fitted_surface": {
        "status": "unsupported",
        "limitations": [
            "freeform fitted surfaces require direct surface control beyond the"
            " parametric solid toolchain"
        ],
        "fallbacks": ["approximate_with_parametric_primitives", "author_externally_and_import"],
    },
    "sculpt_subd_modeling": {
        "status": "unsupported",
        "limitations": [
            "subdivision and sculpt workflows are outside the engine's solid-modeling contract"
        ],
        "fallbacks": ["approximate_with_parametric_primitives", "author_externally_and_import"],
    },
    "mesh_editing": {
        "status": "unsupported",
        "limitations": [
            "mesh push-pull and direct triangle editing are not supported authoring modes"
        ],
        "fallbacks": ["rebuild_parametrically_around_import", "author_externally_and_import"],
    },
    "frame_assembly": {
        "status": "supported",
        "limitations": [],
        "fallbacks": [],
    },
    "solved_mates_constraint_solver": {
        "status": "unsupported",
        "limitations": [
            "assembly placement is explicit and frame-driven; there is no solved"
            " mate or constraint solver"
        ],
        "fallbacks": ["encode_frames_explicitly", "decline_request"],
    },
    "revolute_sampled_motion": {
        "status": "supported",
        "limitations": ["motion results are sampled rather than continuous proofs"],
        "fallbacks": ["increase_samples", "accept_sampled_motion_check"],
    },
    "ball_joint_articulation": {
        "status": "unsupported",
        "limitations": ["multi-axis articulation is not verified by the current motion checker"],
        "fallbacks": ["approximate_with_single_axis_checks", "decline_request"],
    },
    "continuous_collision_proof": {
        "status": "unsupported",
        "limitations": ["motion verification is sampled and cannot prove continuous clearance"],
        "fallbacks": ["accept_sampled_motion_check", "decline_request"],
    },
    "fdm_dfm_validation": {
        "status": "supported",
        "limitations": [],
        "fallbacks": [],
    },
    "non_fdm_dfm_validation": {
        "status": "unsupported",
        "limitations": ["automated DFM checks are only available for FDM workflows"],
        "fallbacks": ["perform_manual_review", "decline_request"],
    },
    "structural_fea": {
        "status": "unsupported",
        "limitations": ["the engine does not provide finite-element structural analysis"],
        "fallbacks": ["perform_manual_review", "author_externally_and_import"],
    },
    "step_brep_modification": {
        "status": "conditional",
        "limitations": [
            "imported solids can be staged and rebuilt around, but direct feature"
            " editing is not guaranteed"
        ],
        "fallbacks": ["rebuild_parametrically_around_import", "author_externally_and_import"],
    },
    "svg_3d_reference": {
        "status": "unsupported",
        "limitations": [
            "2D vector artwork is not a native 3D reference or surface-authoring input"
        ],
        "fallbacks": ["convert_to_supported_cad_reference", "author_externally_and_import"],
    },
    "boolean_enum_editable_params": {
        "status": "supported",
        "limitations": [],
        "fallbacks": [],
    },
}

_STATUS_PRIORITY: Final[dict[str, int]] = {
    "supported": 0,
    "conditional": 1,
    "unknown": 2,
    "unsupported": 3,
}


def engine_capabilities() -> dict[str, object]:
    return {
        "version": 1,
        "geometry": {
            "representation": "parametric-solid-modeling",
            "supported": ["extrude", "revolve", "sweep", "loft", "boolean", "fillet", "chamfer"],
            "unsupported": [
                "subd_sculpting",
                "mesh_push_pull",
                "direct_nurbs_control_point_editing",
            ],
        },
        "assemblies": {
            "placement": "frame-driven",
            "joints": {
                "declared": ["rigid", "revolute", "slider", "cylindrical", "planar", "ball"],
                "verified": ["rigid", "revolute", "slider"],
            },
        },
        "parameters": {
            "supported": ["numeric", "boolean", "enum"],
            "schemas": {
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
            },
        },
        "operations": {
            "families": {
                "capability": ["get_engine_capabilities", "assess_design_plan"],
                "modeling": [
                    "execute_script",
                    "run_file",
                    "get_params",
                    "get_model_info",
                    "list_materials",
                    "get_manufacturing_profile",
                    "set_manufacturing_profile",
                    "inspect_features",
                    "set_feature",
                    "feature_at",
                    "render",
                    "export",
                    "capture_views",
                    "create_drawing",
                    "set_params",
                ],
                "inspection": [
                    "check_interferences",
                    "analyze_dfm",
                    "measure",
                    "measure_between",
                    "query_faces",
                    "thickness_at",
                    "stress_check",
                    "tolerance_stack",
                    "check_motion",
                ],
                "requirements": [
                    "set_requirements",
                    "check_requirements",
                    "propose_build",
                    "get_build_brief",
                    "update_build_brief",
                    "get_conformance",
                    "get_readiness",
                    "converge_to_spec",
                    "sweep",
                    "optimize",
                ],
                "search": ["lookup_standard", "lookup_reference", "save_reference"],
                "imports": [
                    "analyze_import",
                    "import_reference",
                    "stage_import",
                    "import_capabilities",
                    "list_imports",
                    "remove_import",
                ],
                "assemblies": [
                    "set_skeleton",
                    "set_part",
                    "get_assembly_tree",
                    "get_part_info",
                    "attach",
                    "set_occurrences",
                    "set_inputs",
                    "remove_part",
                    "add_subassembly",
                    "build_part",
                    "begin_round",
                    "end_round",
                    "abort_round",
                    "export_flat_model",
                    "check_interfaces",
                ],
                "async": ["get_operation", "submit_operation", "cancel_operation"],
                "support": ["report_issue"],
            },
            "excludedFamilies": {
                "metadata": ["get_workspace_meta", "set_workspace_meta"],
                "history": [
                    "diff_against",
                    "build_report",
                    "cad_history",
                    "cad_undo",
                    "cad_redo",
                    "cad_checkpoint",
                    "cad_goto",
                ],
                "fabrication": [
                    "fab_detect",
                    "fab_profiles",
                    "fab_estimate",
                    "fab_orient",
                    "fab_open",
                ],
            },
        },
        "imports": {
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
        },
        "exports": {
            "roles": {
                "exchange": ["step", "brep"],
                "manufacturing": ["stl", "3mf"],
                "visualization": ["glb", "gltf"],
            }
        },
        "verification": {
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
        },
        "intents": deepcopy(_INTENT_ASSESSMENTS),
        "fallbacks": {
            "unsupported": [
                "approximate_with_parametric_primitives",
                "author_externally_and_import",
                "decline_request",
            ]
        },
    }


def assess_design_plan(intents: list[str]) -> dict[str, object]:
    counts: AssessmentCounts = {"supported": 0, "conditional": 0, "unsupported": 0, "unknown": 0}
    assessed_intents: list[AssessedIntent] = []
    worst_status: CapabilityStatus = "supported"

    for intent in intents:
        base = _INTENT_ASSESSMENTS.get(intent)
        if base is None:
            assessed: AssessedIntent = {
                "intent": intent,
                "status": "unknown",
                "limitations": ["intent is not recognized by the deterministic capability catalog"],
                "fallbacks": ["map_request_to_known_intents", "decline_request"],
            }
        else:
            assessed = {"intent": intent, **base}
        status = assessed["status"]
        counts[status] += 1
        if _STATUS_PRIORITY[status] > _STATUS_PRIORITY[worst_status]:
            worst_status = status
        assessed_intents.append(assessed)

    return {
        "summary": {"status": worst_status, "counts": counts},
        "intents": assessed_intents,
    }
