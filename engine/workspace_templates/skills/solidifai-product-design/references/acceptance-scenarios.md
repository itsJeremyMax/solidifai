# Acceptance scenarios — solidifai-product-design

Six scenarios an operator (or the agent itself, in the live app) walks to confirm the skill
behaves correctly. Each scenario states the expected **classify → default → ask → build →
self-verify** behavior and a **pass condition**. Work through the checklist in order; a failing
step is a regression.

---

## Scenario 1 — "a case for a [handheld device]"

**Target class:** `handheld-enclosure`

### Expected behavior

- [ ] **Classify.** Maps to `handheld-enclosure` playbook; loads that playbook and its four lenses
  (`ergonomics`, `affordance-usability`, `manufacturability`, `aesthetics-form`). Does not load
  `structure` or any other unrelated lens.
- [ ] **Infer & default.** Fills every unspecified dimension from the playbook's default recipe
  without asking:
  - Walls 2–2.5 mm (from `manufacturability` — at or above the printable minimum).
  - Outer edges filleted in one shared radius family (~6 mm soft corner); no sharp grip surface.
  - Internal cavity = assumed device dimensions + canonical FDM mating clearance per side
    (`manufacturability`); shell outer size = device + 2 × (clearance + wall).
  - Lid strategy (snap-fit or screw boss) chosen and stated.
  - Button cutouts at or above the finger-pad minimum; port openings = connector + ~0.5 mm.
  - States all assumptions briefly (e.g. "I'm assuming an 80 × 45 × 18 mm device, 2.4 mm walls,
    0.3 mm clearance per side, snap-fit lid, 12 mm button cutout on the +X face").
- [ ] **Ask only ≤ 3 questions** — only the decision-changing ones the playbook flags:
  1. Device outer dimensions (sets the entire cavity; wrong guess wastes a print).
  2. Which faces carry ports and buttons (drives layout before filleting).
  3. Carry mode: pocket-carry vs. mounted (affects thickness/boss strategy).

  Does **not** ask about wall thickness, fillet radius, clearance, lid strategy, or anything
  derivable from the defaults.
- [ ] **Build.** Calls `execute_script` with a parametric hollow filleted shell: outer box,
  filleted vertical edges, hollowed to wall thickness (top open for lid), button cutout on the
  named face, port opening(s) on the named face. `show()`s the case (and lid separately if
  modeled). Lid is its own solid with the canonical lip clearance, not fused.
- [ ] **Self-verify — both channels.**
  - **Measurable asserts:** `get_model_info()` bounding box matches device + 2 × (clearance +
    wall); `valid` and `manifold` both true. States which checks are known-by-construction (wall
    thickness, cavity clearance — set by the agent, not back-measured from the bbox) vs. computed
    (overall bbox).
  - **Visual review:** calls `capture_views(["front", "<control-face>"])`. Looks at the images and
    confirms: button cutout(s) are reachable and unobstructed by the grip hand; primary control is
    under the natural thumb; outer edges share one radius family with no stray sharp grip edge.

**Pass condition:** agent states assumptions, asks ≤ 3 questions (only the three above), builds a
valid + manifold solid, and both self-verify channels run and pass with findings reported.

---

## Scenario 2 — "a knob for a stove"

**Target class:** `knob-control`

### Expected behavior

- [ ] **Classify.** Maps to `knob-control` playbook; loads `ergonomics`, `affordance-usability`,
  and `aesthetics-form`. Does not load `structure` or `manufacturability` unless there is a
  specific load or wall concern.
- [ ] **Infer & default.** Applies the precision-grip defaults without asking:
  - Knob Ø falls within the precision-grip band from `ergonomics` (fingertip-turned control, not
    a fist-wrapped handle).
  - Flutes or knurl applied for finger purchase (polar pattern of subtracted grooves around the
    rim; no smooth, slippery disc).
  - Indicator rib or pointer present — a stove knob sets a value (burner level), so a visible
    indicator is mandatory per `affordance-usability`.
  - Top rim edge broken in one radius family (no sharp edge a finger rides).
  - Blind shaft bore sized for a typical stove shaft; states the assumed Ø and fit.
  - States assumptions briefly (e.g. "Ø 14 mm precision-grip knob, 14 flutes, indicator rib on
    top, 6.2 mm blind shaft bore").
- [ ] **Ask only ≤ 3 questions** — only the decision-changing ones:
  1. Shaft / interface dimensions (round press-fit, D-shaft, or splined pot shaft — sets bore
     profile; wrong guess means the knob won't go on).
  2. Turned or pressed? (Confirms the precision-grip/rotation recipe vs. a button recipe.)
  3. Setting (multi-position value) or on/off? (Confirms the indicator is mandatory vs. optional.)

  Does **not** ask about flute count, Ø, top radius, or anything derivable from the defaults.
- [ ] **Build.** Calls `execute_script` with a parametric fluted knob: precision-grip cylinder,
  polar flutes subtracted from the rim, top rim fillet, indicator rib, blind shaft bore. One
  valid manifold solid.
- [ ] **Self-verify — both channels.**
  - **Measurable asserts:** knob Ø is within the precision-grip band (known-by-construction — the
    agent set the diameter; the bounding box also reflects the nominal Ø since flutes only notch
    the rim). Shaft bore is blind (doesn't break the top). `valid` and `manifold` both true from
    `get_model_info()`. Wall around the bore is reported known-by-construction (not recoverable
    from `get_model_info()` on curved geometry).
  - **Visual review:** calls `capture_views(["iso", "top"])`. Looks at the images and confirms:
    flutes/knurl read as a grip the fingers could turn (not a smooth disc); a clear indicator/
    pointer is visible; Ø:height proportion looks like a deliberate knob, not an accidental stub
    or tower.

**Pass condition:** knob Ø is within the precision-grip band, indicator is present, both
self-verify channels run and pass, and findings are reported.

---

## Scenario 3 — "a wall bracket for a router"

**Target class:** `bracket-mount`

### Expected behavior

- [ ] **Classify.** Maps to `bracket-mount` playbook; loads `structure`, `manufacturability`
  (fastener strategy), and `aesthetics-form`. Does not load `ergonomics` or
  `affordance-usability` (nothing is gripped or pressed on a hidden wall bracket).
- [ ] **Infer & default.** Applies the structural and fastener defaults without asking:
  - Fastener pattern chosen; clearance-hole diameters taken from the **cookbook §11 clearance
    table** (normal-fit column) for the assumed bolt size. Does **not** copy the number into the
    response — references the table and states which row/column it used.
  - Counterbore dimensions (if heads must sit flush) taken from cookbook §11 B, same reference
    discipline.
  - Load root filleted: radius ≥ ~0.5× the adjoining wall (from `structure`).
  - Triangular gusset web bracing the cantilevered corner; gusset web ~0.5–0.8× wall.
  - Wall/rib sized to the load; wins stiffness with depth and ribs, not by bulking solid.
  - Stand-off/boss lifting the router off the wall surface (cable clearance, connector access).
  - States assumptions briefly (e.g. "M4 bolts, normal-fit clearance from cookbook §11 A, 2×2
    hole pattern, 5 mm wall, 4 mm load-root fillet, triangular gusset, aluminum material").
- [ ] **Ask only ≤ 3 questions** — only the decision-changing ones:
  1. What mounts to what? (Foot bolts to the wall; upstand holds the router — confirms geometry
     and which flange gets the bolt pattern.)
  2. Load magnitude and direction? (Order-of-magnitude: hand-press vs. hanging device vs.
     heavier load — sets wall thickness and gusset sizing; flags when a real stress check is
     needed.)
  3. Fastener size and pattern? (M3/M4/M5/M6, how many — picks the cookbook §11 clearance row
     and the hole pattern that resists rotation or moment.)
- [ ] **Build.** Calls `execute_script` with a parametric L-bracket: foot flange + upstand flange,
  filleted internal load root, triangular gusset fused to both flanges (one solid), bolt-hole
  pattern through the foot using clearance Ø from cookbook §11. One valid manifold solid.
- [ ] **Self-verify — both channels.**
  - **Measurable asserts:** each bolt-hole diameter equals the clearance value from the cookbook
    §11 table for the chosen size/fit (references the table, does not assert against a re-typed
    literal). Load-root fillet radius ≥ ~0.5× wall (known-by-construction). Gusset web within
    ratio (known-by-construction). `valid` and `manifold` both true from `get_model_info()`;
    part is one solid (gusset fused, not floating). Every wall on the load path ≥ printable
    minimum (known-by-construction). Reports that true stress margin is **not** recoverable from
    `get_model_info()` — these are structural rules-of-thumb, not a verified stress analysis.
  - **Visual review:** calls `capture_views(["right", "iso"])` (right view looks down the gusset's
    XZ plane). Looks at the images and confirms: internal load root is visibly filleted, not a
    sharp notch; gusset braces the cantilevered corner; bolt pattern lands fully inside the foot
    and is clear of the gusset; upstand stands the router off the fastening face.
  - **Honesty statement:** agent explicitly states this satisfies structural rules-of-thumb
    (filleted root, gusset, sized wall), **not** a verified stress margin; recommends a proper
    structural check (FEA or hand calc) if the load is meaningful or safety-critical.

**Pass condition:** fastener clearances reference the cookbook §11 table (not a re-typed number),
load root is filleted, gusset is present and fused, both self-verify channels run and pass, and
the honesty statement is included.

---

## Scenario 4 — Short-circuit: "a 20 mm calibration cube"

**Target class:** none — skill does NOT engage

### Expected behavior

- [ ] **Classify.** Recognizes this as pure geometry / utility: a calibration cube is fully
  specified (20 mm, no design decisions left open) and no human operates or holds it in any
  way that design judgment could improve.
- [ ] **Short-circuit.** Does NOT load any playbook or lens. Does NOT apply ergonomic defaults,
  ask design questions, impose a fillet family, choose a wall strategy, or make any
  aesthetic/usability judgment. Hands the request straight to `solidifai-modeling`.
- [ ] **No design opinions imposed.** The output is a plain 20 mm cube — no rounded corners
  added "for feel", no wall strategy applied, no ergonomic sizing question asked.
- [ ] **No design questions asked.** Zero questions about how it will be held, what controls go
  on it, what carry mode, or any other design-judgment topic.

**Pass condition:** no ergonomic or aesthetic defaults are imposed, no design questions are asked,
and the request is forwarded to `solidifai-modeling` without modification.

---

## Scenario 5 — "a case for a Raspberry Pi that runs warm"

**Target class:** `electronics-enclosure` (NOT `handheld-enclosure`)

### Expected behavior

- [ ] **Classify.** Maps to `electronics-enclosure` — a board-in-a-box, not a held device. Loads
  that playbook and the lenses it pulls: `thermal-ventilation` (it runs warm), `dfm-additive`
  (active family lens), `structure` (standoffs/bosses), `manufacturability` (process + fastening),
  `affordance-usability` (port/connector layout), and `support-stability` (it sits on a desk). Pulls
  `sealing-ingress` **only** if the user says outdoor/sealed. Does **not** load `ergonomics` (nothing
  is gripped or thumb-operated). The key check: a "Pi case" does **not** misroute to
  `handheld-enclosure`.
- [ ] **Infer & default.** Fills the recipe without asking:
  - **Standoffs at the board's mounting-hole pattern** (e.g. a Pi 4 is ~85 × 56 mm, M2.5 holes on a
    58 × 49 mm rectangle) that lift the board off the floor so its bottom pins don't short.
  - Cavity = board + component-stack height + clearance; outer = cavity + walls.
  - **Port cutouts derived from the connector layout** on the board's actual faces (USB/Ethernet on
    one long side, HDMI/USB-C/audio on the other, microSD on the end), each = connector + clearance.
  - **Low-inlet / high-outlet vents** to a thermal open-area target (`thermal-ventilation`), slots
    vertical and self-supporting (`dfm-additive`).
  - Snap or screw lid with the canonical mating clearance (linked, not re-picked); captive lid
    hardware and a single assembly direction (`serviceability-assembly`).
  - States assumptions briefly (e.g. "Pi 4 footprint, 58 × 49 mm M2.5 standoffs 5 mm tall, ports on
    the two long faces, low+high vent bands, 2.4 mm walls, screw-boss lid, indoor/passive").
- [ ] **Ask only ≤ 3 questions** — only the decision-changing ones:
  1. The board's outline and mounting-hole pattern (sets the standoffs and cavity).
  2. Which faces carry which connectors (drives the port cutouts and the orientation).
  3. Does it run hot / need a fan, and indoor vs. sealed/outdoor (forks `thermal-ventilation` vs.
     `sealing-ingress` — you can't freely vent a sealed box).

  Does **not** ask about wall thickness, vent slot width, fillet radius, or anything derivable.
- [ ] **Build.** Calls `execute_script` with a parametric shell: standoffs on the hole pitch, a
  **low inlet vent band and a high outlet vent band** through the side walls, a port cutout on the
  connector face. `show()`s the enclosure (lid modeled as a separate part; exploded view is the
  built-in viewport control — **no `explode` parameter**).
- [ ] **Self-verify — both channels.**
  - **Measurable asserts:** `get_model_info()` bbox = cavity + 2 × wall; `valid` and `manifold`
    true; center of mass projects inside the footprint. Standoffs match the hole pattern and clear
    the floor; vent open area ≥ the target and every slot ≥ the printable minimum and self-supports
    (known-by-construction). `check_interferences()` reads board-to-standoff `adjacent`, nothing
    `disjoint`/floating.
  - **Visual review:** `capture_views(["iso", "<port-face>", "front"])`. Confirms vents read
    **low-in / high-out**, every port clears its connector and nothing is blocked, and the box sits
    stably.
  - **Honesty statement:** states the cooling satisfies passive ventilation **rules of thumb**, not
    a verified thermal result; flags that a real thermal/airflow check is needed if dissipation is
    high or the rating is tight.

**Pass condition:** routes to `electronics-enclosure` (not `handheld-enclosure`), standoffs land on
the board's hole pattern, **low-inlet / high-outlet vents** are present to an open-area target, both
self-verify channels run and pass, and the thermal honesty statement is included.

---

## Scenario 6 — "a sheet-metal bracket"

**Target class:** `bracket-mount` · **method route:** `dfm-sheet` (NOT the default FDM/`dfm-additive`)

This scenario exercises the **method router**: the part class is a bracket, but the user named a
manufacturing method (sheet metal) that is not the material's auto-detected process, so the active
DFM family lens must switch to `dfm-sheet`.

### Expected behavior

- [ ] **Classify — both axes.** Part class → `bracket-mount` (loads `structure`, the
  `manufacturability` hub, `aesthetics-form`). **Method → `dfm-sheet`**: the user said "sheet
  metal", so the method is **stated**, overriding the material's auto-detected `fdm`/`cnc`. Loads
  `dfm-sheet` as the active family lens instead of `dfm-additive`. (Confirms the **Routing →
  Method router** honesty rule: sheet is reached by stated/inferred intent, not auto-detection.)
- [ ] **Infer & default — to the sheet rules, not the FDM rules.** Applies `dfm-sheet` defaults
  without asking:
  - **One uniform stock thickness** `t` throughout (a sheet part is a single gauge, not a solid
    massed where it likes).
  - **Inside bend radius ≥ ~`t`** (looser on stainless, which work-hardens).
  - **Bend relief** slots at each bend end so the fold doesn't tear.
  - **Holes kept ≥ ~2.5`t` + radius from any bend** so they don't deform.
  - **Min flange ≥ ~4`t` + radius** so the brake can form it.
  - **Self-clinch / PEM** for a threaded fastening — **not** a heat-set insert (that's the FDM
    strategy; the sheet-native fastening is a pressed-in nut/stud).
  - States assumptions briefly (e.g. "1.5 mm aluminum, two 90° bends, ~1.5 mm inside radius,
    relief at each bend, holes 4 mm from the bends, PEM nuts").
- [ ] **Ask only ≤ 3 questions** — only the decision-changing ones:
  1. Gauge and material (sets `t`, the bend radius, and how much the metal work-hardens).
  2. How many bends and in which directions (sets the flat pattern and whether it unfolds).
  3. What fastens to what (sets the hole pattern and the PEM vs. through-bolt call).
- [ ] **Build.** Calls `execute_script` for a bracket designed **to the sheet rules** — uniform
  wall, generous bend radii, relief at the bends, holes clear of the bend zones — even though the
  engine models it as a solid. (Does **not** apply FDM-only moves like a heat-set boss or a
  3D-printed thick gusset web.)
- [ ] **Self-verify — both channels.**
  - **Measurable asserts:** wall is **one uniform `t`** throughout, inside bend radii **≥ ~`t`**,
    and every hole sits **≥ ~2.5`t` + radius** from a bend (all known-by-construction). `valid` and
    `manifold` true from `get_model_info()`.
  - **Visual review:** `capture_views(["iso", "front"])` — confirms the bends carry relief, no hole
    rides a bend, and the part reads as a folded sheet, not a printed solid.
  - **Honesty statement:** states the true **flat pattern / bend allowance** depends on the actual
    brake, die, and K-factor — these are sheet-design rules of thumb, not a verified flat blank.

**Pass condition:** the **method router engages** (`dfm-sheet`, not the default additive lens),
sheet rules are applied (uniform `t`, bend radius ≥ `t`, bend relief, hole-to-bend clearance, PEM
rather than heat-set), and the flat-pattern honesty statement is included.

---

## Running the scenarios

These are human-walkable checklists, not automated tests. To run them:

1. Open the live solidifai app (or a dev workspace with the MCP server running).
2. Type each prompt verbatim (or a close paraphrase).
3. Walk each checkbox in order, marking pass/fail.
4. A scenario **passes** only when every checkbox is ticked. Any unchecked item is a regression
   to investigate and fix in the relevant playbook or the skill's behavior loop.
