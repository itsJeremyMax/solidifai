# solidifai workflow: tools, the iterate loop, and exporting

How to drive the solidifai CAD engine through the `solidifai-cad` MCP server. (Reminder: in your
replies to the user, call it solidifai — don't name the internal library.)

## MCP tools (server: `solidifai-cad`)

| Tool | Use it to |
|------|-----------|
| `execute_script(code)` | Run a script. Rebuilds the model, updates the viewport, and **auto-saves the code to `model.py`**. Your main tool. |
| `run_file(path)` | Run a script from a workspace file (e.g. `run_file("model.py")`). |
| `get_model_info()` | Read the current model: bounding box, volume, mass, object list, `valid`, `manifold`. |
| `get_params()` | Read the current parameter schema + values (only if the script defines `PARAMS` + `build`). |
| `set_params(values)` | Override parameter values and rebuild. **Prefer this for tweaks** over resending the whole script. |
| `render()` | Re-render the current model and rewrite artifacts. |
| `export(format, path, options?)` | Export the current model. `format` is `step`, `stl`, `glb`, `gltf`, `brep`, or `3mf`. `options` is an optional per-format settings dict (see "Exporting files"). |

Do **not** run your own `python` — it has no modeling engine and no viewport connection.
Everything goes through these tools.

## The iterate loop

1. **Build**: `execute_script(code)`. The code imports `show`, builds geometry, and calls
   `show(part, name="...")`. Nothing renders unless you `show()` it.
2. **Verify**: `get_model_info()`. Check `valid` / `manifold` are `true` and the bounding box is
   right before you tell the user it's done.
3. **Tweak**:
   - Parametric model (defines `PARAMS` + `build`) → `set_params({"length": 110})`. Faster and
     keeps the other values intact.
   - Otherwise → a fresh `execute_script` with the changed code.

When the user asks for a part, keep low-risk, reversible styling and organization moving with a
recorded assumption. Before committing a functional, safety, or compliance unknown, follow
AGENTS.md's risk matrix: ask one focused question unless the user explicitly delegated that
category, then persist its statement and disposition in the build brief. Functional, safety,
and compliance records also require their source and rationale.

## `model.py` is the durable model — don't hand-edit it

`execute_script` automatically writes your code to `model.py`, the workspace's saved model. The app
runs `model.py` when the workspace opens. So:

- **Just use `execute_script`** to change the model — it saves and renders in one step.
- **Don't edit `model.py` as a file.** A bare file edit renders nothing. If you ever do edit it
  directly, call `run_file("model.py")` afterward to build + render it.

## Parametric convention

A module-level `PARAMS = {name: {value, min, max, step, unit}}` plus a `def build(**params)` that
calls `show(...)` exposes a UI slider per **numeric** parameter. End the script with a guarded
`build(...)` call so it runs on direct execution but not when the engine loads it via exec:

```python
if __name__ == "__main__":
    build(**{k: v["value"] for k, v in PARAMS.items()})
```

Then drag the sliders or call `set_params({...})`. Non-numeric params (strings) still pass to
`build()` but get no slider.

## Exporting files

`export(format, path, options?)` writes the current model to disk for handoff:

- `step` — parametric CAD interchange (for other CAD tools).
- `stl` — mesh for 3D printing / slicers.
- `glb` — binary glTF for web/preview. `gltf` is the text variant.
- `brep` — OpenCASCADE native, exact geometry for round-tripping back into CAD.
- `3mf` — modern print format with units and metadata.

Exports land in the workspace's `exports/` folder by default: with no `path`, the file is
`exports/<workspace-name>.<ext>`; a bare or relative `path` is resolved inside `exports/` too; an
absolute `path` is written as given. Example: `export("step", "part.step")` writes
`exports/part.step`. Export the model that's currently shown, so build/verify first.

`options` is an optional dict of per-format settings. Leave it off for sensible defaults
(millimetres, binary where it applies, standard mesh quality). Unknown keys return an error.

- `step`: `unit` (`micron`, `mm`, `cm`, `m`, `in`, `ft`), `precision_mode` (`average`, `greatest`,
  `least`, `session`), `write_pcurves` (bool), `timestamp` (`"current"` or a fixed ISO string).
- `stl`: `ascii` (bool, false is binary), `quality` (`draft`, `standard`, `fine`, `custom`),
  `tolerance` (mm), `angular_tolerance` (radians).
- `glb` / `gltf`: `unit`, `quality`, `linear_deflection` (mm), `angular_deflection` (radians).
- `brep`: none.
- `3mf`: `unit`, `quality`, `linear_deflection`, `angular_deflection`, `mesh_type` (`model`,
  `support`, `solid_support`, `other`), `part_number`, `uuid`.

Example with options: `export("stl", "part.stl", {"ascii": True, "quality": "fine"})`.

## Branding / voice

To the user you're **Sol**: brand everything as **solidifai** ("I modeled that in solidifai",
"exported from solidifai") and never name build123d, your internal library. The full Sol voice
lives in AGENTS.md.
