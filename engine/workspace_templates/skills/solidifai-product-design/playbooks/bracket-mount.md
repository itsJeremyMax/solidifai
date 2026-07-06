# bracket-mount playbook

A load-bearing bracket or mount that **fastens one thing to another** — a shelf bracket, a
wall mount for a router, an L-bracket tying a panel to a frame. The job is a stiff path from
the fastened surface to the mounted object: bolt it down solidly, route the load through filleted
corners and a gusset, and stand the mounted part off the mating face. Numbers come from the lenses
and the cookbook below — this playbook composes them, it does not restate them.

## Scope

A **bracket / mount** that carries a real load between two things: a foot or flange bolted to one
surface (wall, frame, plate) and a face or boss that holds the other (a device, a shelf, a rail).
It bends or shears under that load, so it lives or dies on its **load path** — fillet the root,
gusset the corner, size the wall to the force — and on its **fastener features** — clearance holes,
counterbores, the right pattern. Use this when the part's job is to *hold something under load*. If
the part is mostly a thing a hand grabs, use `grip-handle.md`; if it just sits a device at an angle
with little load, use `stand-cradle.md`; if it's a box with a lid, use `container-lid.md`.

## Lenses it pulls

- [structure](../references/structure.md#decision-rules) — the load path itself: **fillet the
  internal load root** (radius ≥ ~0.5× the adjoining wall), **gusset a cantilevered corner**, size
  **ribs to the load** (rib ≈ 0.5–0.8× wall), and reach for **depth/triangulation over bulk**.
  Every structural ratio is owned here.
- [structure — load-path heuristics](../references/structure.md#data--defaults) — depth-beats-thickness,
  triangulate, fillet every corner the load turns, and on layered processes (FDM) run the build **along** the load (interlayer adhesion
  is the weak axis).
- [manufacturability — fasteners](../references/manufacturability.md#data--defaults) — which fastening
  *strategy* to choose (clearance bolt-through vs. heat-set insert vs. captive nut) and the manufacturability
  layer (wall ≥ the active process's minimum, overhangs on the upstand/gusset).
- [dfm-additive](../references/dfm-additive.md#decision-rules) — the active **DFM family lens** (additive/FDM by default; swap to the subtractive/formative/sheet lens if the user names that process). The manufacturability hub above routes by process.
- **Fastener clearance & counterbore dimensions →
  [cookbook §11 — Threads & fasteners](../../solidifai-modeling/references/build123d-cookbook.md#11-threads--fasteners).**
  The actual numbers — metric clearance-hole diameters (close/normal/free), socket-head counterbore
  diameters and depths, insert-boss and captive-nut sizes — live there. **Link to that table; never
  restate a clearance number in this playbook.**
- [aesthetics-form](../references/aesthetics-form.md#decision-rules) — a bracket is usually
  **hidden/internal**, so spend effort on function, but still share **one radius family** on the
  visible breaks and keep the form intentional rather than a raw stack of boxes.

## Default recipe

Defaults, each traceable to a lens or the cookbook — adjust to the actual load and fastener, don't
invent past these:

- **Fastener pattern with the right clearance.** Bolt-through is the default: a clearance hole per
  the **normal-fit** column of the **cookbook §11 clearance table**
  ([cookbook §11 A](../../solidifai-modeling/references/build123d-cookbook.md#11-threads--fasteners)),
  recess a socket-head with the **counterbore** dimensions from
  [cookbook §11 B](../../solidifai-modeling/references/build123d-cookbook.md#11-threads--fasteners) if
  the head must sit flush. Need a *threaded* interface in the bracket itself (something bolts *into*
  it) → a **heat-set insert or captive nut**, not a modeled thread, per
  [manufacturability](../references/manufacturability.md#decision-rules) (cookbook §11 C/D). Pick a
  pattern that spreads the load — two bolts resist rotation, four resist a moment — and keep them
  clear of the gusset. **Pull the numbers from the cookbook table; do not copy them here.**
- **Gusseted, filleted load root.** The corner where the load levers the bracket is a stress riser —
  **fillet it** (radius ≥ ~0.5× the wall) and **brace it with a triangular gusset** tying the loaded
  flange back to the foot, per [structure](../references/structure.md#decision-rules). The gusset web
  is ~0.5–0.8× the wall; several modest gussets beat one massive one.
- **Wall / rib sized to the load.** Set the plate thickness from the force, not by reflex: thick
  enough to carry the bending moment but **stiffened with ribs/gussets rather than bulked solid**
  ([structure](../references/structure.md#data--defaults) — depth beats thickness). Never below
  **the active process's minimum wall on a load path**
  ([manufacturability](../references/manufacturability.md#data--defaults)).
- **A stand-off / clearance to the mating surface.** Give the mounted object real space off the
  surface it bolts to — a foot or boss that lifts it clear — so cables, fingers, or a connector
  aren't pinched against the wall and the part seats flat on its fastening face.

### Runnable starter

A parametric L-bracket: a foot flange bolted down with a 2×2 clearance-hole pattern (sizes from the
**cookbook §11** table — change `bolt_d` to the value there, don't re-derive it), an upstand flange
that carries the load, a **filleted internal load root**, and a **triangular gusset web** fused into
one solid bracing the corner. The foot itself is the stand-off that lifts the upstand clear of the
fastening face. Tweak with `set_params(...)`.

```python
from build123d import (
    Align,
    Axis,
    Box,
    BuildLine,
    BuildPart,
    BuildSketch,
    GridLocations,
    Hole,
    Locations,
    Plane,
    Polyline,
    extrude,
    fillet,
    make_face,
)
from solidifai import show

PARAMS = {
    "leg":      {"value": 55.0, "min": 25.0, "max": 120.0, "step": 1.0, "unit": "mm", "desc": "Leg length (each flange, X & Z)"},
    "width":    {"value": 40.0, "min": 20.0, "max": 100.0, "step": 1.0, "unit": "mm", "desc": "Bracket width (Y)"},
    "thick":    {"value": 5.0,  "min": 3.0,  "max": 12.0,  "step": 0.5, "unit": "mm", "desc": "Plate thickness (size to the load)"},
    "bolt_d":   {"value": 4.5,  "min": 3.2,  "max": 7.0,   "step": 0.1, "unit": "mm", "desc": "Bolt clearance Ø — set from cookbook §11 A"},
    "pitch_x":  {"value": 20.0, "min": 10.0, "max": 90.0,  "step": 1.0, "unit": "mm", "desc": "Hole spacing along X"},
    "pitch_y":  {"value": 24.0, "min": 12.0, "max": 70.0,  "step": 1.0, "unit": "mm", "desc": "Hole spacing along Y"},
    "gusset":   {"value": 28.0, "min": 8.0,  "max": 60.0,  "step": 1.0, "unit": "mm", "desc": "Gusset reach along each flange"},
    "root_fil": {"value": 4.0,  "min": 0.5,  "max": 10.0,  "step": 0.5, "unit": "mm", "desc": "Load-root fillet (≥ ~0.5× wall)"},
}


def build(leg, width, thick, bolt_d, pitch_x, pitch_y, gusset, root_fil):
    gus_t = max(0.6 * thick, 2.0)          # web ~0.6x wall (structure lens)
    hole_cx = (thick + gusset + leg) / 2   # holes in the clear foot beyond the gusset

    with BuildPart() as p:
        # Foot flange: lies on the bed, extends +X from the corner.
        Box(leg, width, thick, align=(Align.MIN, Align.CENTER, Align.MIN))
        # Upstand flange: rises +Z, against the corner at X = 0 -> the load arm.
        Box(thick, width, leg, align=(Align.MIN, Align.CENTER, Align.MIN))

        # Fillet the inside-corner load root (the Y-parallel edge at X=thick, Z=thick)
        # so stress flows around it instead of cracking a sharp notch.
        root = (
            p.edges()
            .filter_by(Axis.Y)
            .filter_by(lambda e: abs(e.center().X - thick) < 1e-3
                       and abs(e.center().Z - thick) < 1e-3)
        )
        fillet(root, radius=root_fil)

        # Triangular gusset web (XZ plane), right angle in the inner corner,
        # centred across the width and fused to both flanges -> stays one solid.
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Polyline(
                    (thick, thick),
                    (thick + gusset, thick),
                    (thick, thick + gusset),
                    close=True,
                )
            make_face()
        extrude(amount=gus_t / 2, both=True)

        # 2x2 bolt-hole pattern through the foot, clear of the gusset.
        # bolt_d is the clearance Ø from cookbook §11 A — not a number invented here.
        top = p.faces().filter_by(Axis.Z).sort_by(Axis.Z)[-1]
        with Locations(top):
            with Locations((hole_cx, 0)):
                with GridLocations(pitch_x, pitch_y, 2, 2):
                    Hole(radius=bolt_d / 2)

    show(p.part, name="Bracket", material="aluminum")


if __name__ == "__main__":
    build(**{k: v["value"] for k, v in PARAMS.items()})
```

To recess the heads, swap the `Hole(...)` for a `CounterBoreHole(...)` using the head Ø and depth
from [cookbook §11 B](../../solidifai-modeling/references/build123d-cookbook.md#11-threads--fasteners).
For a *threaded* boss (something bolts into the bracket) add a heat-set insert boss from
[cookbook §11 C](../../solidifai-modeling/references/build123d-cookbook.md#11-threads--fasteners)
instead of a clearance hole — gusset a tall boss to its base wall
([structure](../references/structure.md#decision-rules)).

## Questions that matter

Ask only these, and only if guessing wrong is expensive — otherwise default and state it:

- **What mounts to what?** Which surface does the foot bolt to (wall / frame / plate) and what does
  the upstand hold? Sets the geometry, the stand-off, and which flange carries the bolt pattern.
- **Load magnitude and direction?** Which way the force pushes/pulls and roughly how much
  (hand-press, a hanging shelf, a person's weight) sets the wall thickness, the gusset, and which
  internal corners to fillet ([structure](../references/structure.md#questions-that-matter)). An
  order-of-magnitude is enough; a real safety-critical load needs a proper stress check, not these
  rules of thumb — say so.
- **Fastener size and pattern?** Which bolt (M3 / M4 / M5 / M6) and how many — that picks the
  **clearance/counterbore row from the cookbook §11 table** and the hole pattern that resists the
  load's rotation or moment.

## Verify checklist

- **Assert (computed / referenced)** — confirm each bolt hole's diameter equals the **clearance value
  from the cookbook §11 table** for the chosen size/fit
  ([cookbook §11 A](../../solidifai-modeling/references/build123d-cookbook.md#11-threads--fasteners)),
  and any counterbore matches
  [§11 B](../../solidifai-modeling/references/build123d-cookbook.md#11-threads--fasteners). Reference
  the table value — don't assert against a number you re-typed here. `get_model_info()` `valid` and
  `manifold` are both true and the part is **one solid** (the gusset fused, not floating).
- **Assert (known-by-construction)** — the load-root fillet radius is **≥ ~0.5× the wall** and the
  gusset web is within ratio (~0.5–0.8× wall), per
  [structure — Verify](../references/structure.md#verify); every wall on the load path is **≥ the
  active process's minimum wall** ([manufacturability — Verify](../references/manufacturability.md#verify)). You
  set these, so you know them — true stress margin is **not** recoverable from `get_model_info()`.
- **Visual** — `capture_views(["right", "iso"])` (the right view looks down the gusset's XZ plane).
  Confirm the **internal load root is visibly filleted, not a sharp notch**, the **gusset braces the
  cantilevered corner**, the bolt pattern is clear of the gusset and lands fully inside the foot, and
  the upstand stands the mounted object **off the fastening face**
  ([structure — Verify](../references/structure.md#verify)).
- **Honesty** — report this as the load rules-of-thumb satisfied (filleted root, gusset, sized wall),
  **not** a verified stress margin. If the load is meaningful or safety-critical, say a proper
  structural check (FEA / hand calc) is still needed.
- **Mounted, not floating** — the bracket carries gravity through its fasteners, so confirm the load
  runs into them (no cantilever left holding itself up) and run `check_interferences()` so the part
  is one connected body with nothing `disjoint`/floating and no unintended `overlap`
  ([support-stability](../references/support-stability.md#verify)).

## Common failure modes

- **Unfilleted load root** — a sharp internal corner at the bend is a crack waiting to start,
  especially on brittle beams (FDM especially, pulled across the layers). Fillet it (≥ ~0.5× wall) and gusset the corner
  ([structure](../references/structure.md#decision-rules)).
- **Wrong or restated clearance** — a hole sized to the bolt's nominal Ø (no clearance) won't accept
  the bolt; a number copied into the playbook and gone stale is worse than a link. Take the clearance
  straight from the **cookbook §11 table**
  ([§11 A](../../solidifai-modeling/references/build123d-cookbook.md#11-threads--fasteners)), never
  re-type it.
- **Flimsy under the stated load** — a thin un-ribbed plate that flexes or snaps. Size the wall to
  the force and win stiffness with **depth, ribs, and gussets**, not by reflexively bulking the solid
  ([structure](../references/structure.md#data--defaults)); flag when the load needs a real stress
  check.
- **No stand-off** — the mounted object pinned flat against the fastening face pinches cables or a
  connector and can foul the bolt heads. Give it a foot/boss that lifts it clear, and let the part
  seat flat on its fastening face.
- **Floating gusset / fused-wrong geometry** — a gusset that doesn't actually touch both flanges (or
  a bracket that comes out non-manifold) carries no load and can't be made. Keep it **one solid**: the
  web must fuse to both flanges along the whole load path.
