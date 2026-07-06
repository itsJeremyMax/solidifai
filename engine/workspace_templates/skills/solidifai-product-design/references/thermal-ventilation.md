# thermal & ventilation lens

Grounded judgment for a part that **runs warm** — a case or enclosure around electronics that
dissipate power and need that heat to get out. All values mm. These are **passive-cooling rules of
thumb, not a thermal or CFD simulation**: natural convection is buoyancy-driven and messy (it
depends on ambient temperature, component layout, surface area, and how hot the parts are actually
rated to run), so use the geometry rules to give the heat a sane way out and, when the rating is
tight or the dissipation is real, say it needs a proper thermal calc rather than implying these
heuristics sized it.

This lens is about **letting heat escape by design**. It is cross-cutting — any enclosure playbook
can pull it. It does **not** own the minimum width a vent slot can actually *print*: that is a
process constraint owned by [dfm-additive](dfm-additive.md#decision-rules) (the FDM
self-supporting / minimum-feature rule), linked here, not restated. And venting trades directly
against keeping water and dust out — that **airflow-vs-ingress** tension is owned by
[sealing-ingress](sealing-ingress.md#decision-rules); when the part has to be sealed, that lens
wins and this one switches to conducting heat to the case skin instead of cutting holes.

## Principle

Heat leaves a warm part three ways — conduction through the case, radiation off its surfaces, and
**convection** carrying it away in moving air — and inside a passive enclosure convection does most
of the work only if the air can actually circulate. Warm air is less dense, so it **rises**; design
the enclosure as a chimney. Put the **inlets low** so cool ambient air is drawn in at the bottom,
put the **outlets high** so the warmed air leaves at the top, and give the two a **vertical
separation** — the taller that inlet-to-outlet stack, the stronger the buoyancy-driven draft
(the **stack / chimney effect**) that pulls fresh air through. Then make the openings big enough:
size the open area to the heat being dumped, keep **inlet area roughly equal to outlet area** so
neither end chokes the flow, and never seal a heat source — a CPU, a regulator, a passive heatsink
— inside a dead cavity with no path out. When passive flow can't keep the parts under their rating,
add a **fan** to force the air and exhaust it high.

## Data & defaults

| Quantity | Value / rule | Notes |
|---|---|---|
| Convection direction | **inlets low, outlets high**, with vertical separation | Cool air in at the bottom, warm air out the top; the chimney/stack draft grows with the **inlet-to-outlet height**. Inlet and outlet on the *same low* level barely circulates. |
| Vent geometry | **slots > round holes** for open-area-per-strength; **louvers** add rain/splash shedding | A run of slots opens more free area for the same remaining wall than a field of round holes, and reads cleaner. Angled louvers let air out while shedding falling water — the outdoor move. |
| Open-area target (passive) | **size to the heat**, balance **inlet ≈ outlet**; aim for a **generous** free area on the vent panels (often framed as **tens of percent**, ~20–50% of the vented face) rather than a token few holes | The fuzziest number here — there is **no single universal %**; vendor and convection-cooling guidance frames it as *proportional to the dissipated power* and as a sizeable fraction of the panel, and says maximize free area within structural/EMI limits. Treat the % as a **target to hit by construction and sanity-check**, not a guarantee — a real thermal calc sizes it when the rating is tight. |
| Min **printable** vent slot | → [dfm-additive](dfm-additive.md#decision-rules) | The smallest slot that prints cleanly (self-supporting, vertical) follows the FDM minimum-feature / overhang rule owned there — link it, don't name a print min in this lens. |
| Axial fan sizes | common **25 / 30 / 40 mm** square (then 50 / 60 / 80…); body depth often ~10–25 mm | Pick the size that fits the panel; the **40 mm** fan mounts on a **32 mm** square screw pattern (25 / 30 mm fans use smaller patterns ~20 / 24 mm) — take the exact pattern, hole Ø and depth from the **chosen fan's datasheet**, don't assume. |
| Fan boss + clearance | screw-boss pattern to match the fan; **finger guard / grille** over the blades; leave the bore clear | Mount the fan to a boss matching its hole pattern (see [structure](structure.md#data--defaults) for boss/gusset *how*), put a guard or slotted grille over the blades for safety, and don't let the case wall block the intake/exhaust face. State which face is **intake** vs **exhaust** — pull cool air in low, push warm air out high. |
| Heatsink air gap | leave an **open air gap above the fins**; never enclose a passive heatsink in a dead box | A passive heatsink only works if convecting air can move *between and above* its fins; a few mm of clear gap to any wall, and a vent above it, or it just soaks the box. |
| Passive vs. active | **passive** for low/moderate dissipation indoors; **add a fan** when passive can't hold the rating | Passive is silent, cheap, nothing to fail; a fan moves far more heat but adds noise, power, dust intake and a failure point. Step up only when the parts won't stay under their rating passively. |

**Cooling heuristics (rules of thumb):**

- **Tall stack, not a flat one.** The buoyancy draft scales with the vertical drop from outlet to
  inlet — separate them top-to-bottom, don't cluster all the vents on one face at one height.
- **Balance the ends.** Inlet ≈ outlet free area; a big outlet fed by a pinhole inlet (or vice
  versa) is throttled by the smaller one. Match them.
- **Slots beat holes, louvers beat slots outdoors.** For the same residual wall, slots open more
  area than round holes; louvers trade a little area for shedding rain — use them only when water
  matters (and then mind [sealing-ingress](sealing-ingress.md#decision-rules)).
- **Don't trap the heat.** A heatsink, hot regulator, or CPU sealed in a closed cavity just cooks;
  give every heat source a low inlet and a high outlet, or conduct its heat to the case skin.
- **Derate awareness.** Electronics throttle or shorten their life when they run hot; "it boots"
  is not "it stays in spec." If the part genuinely runs warm, treat staying under the **rated**
  temperature as the goal, not just not-melting.

## Decision rules

- **Runs warm + indoor → passive.** Inlets low, outlets high with vertical separation, open area
  **≥ the target** (sized to the heat, inlet ≈ outlet), slots **vertical and self-supporting** so
  they print clean (→ [dfm-additive](dfm-additive.md#decision-rules)). This is the default for a
  Raspberry-Pi-class case that just needs airflow.
- **Passive can't hold the rating → add a fan.** Put in a **fan boss** matching the chosen fan's
  screw pattern with a **finger guard**, exhaust **high**, draw intake **low**, and keep the
  intake/exhaust face clear. Step up in fan size (25 → 30 → 40 mm…) before fighting a tiny fan.
- **Passive heatsink inside → never seal it in a dead box.** Leave an **open air gap above the
  fins** and a vent above it so air convects through, or the heatsink does nothing.
- **Sealed / high-IP (water, dust, outdoor) → no open vents.** Don't cut holes; **conduct** the
  heat to the case wall or an **external heatsink** instead, and let the airflow-vs-ingress
  tradeoff be owned by [sealing-ingress](sealing-ingress.md#decision-rules). A gasketed louver is
  the compromise only when some rain protection plus some airflow are both required.
- **Real dissipation / tight rating / safety-critical heat → flag it.** These are convection
  rules of thumb; if the watts are real or the parts are near their limit, say it needs a proper
  thermal calc (or a measured prototype), don't imply the heuristics verified the temperature.

## Questions that matter

- **How much power does it dissipate — does it actually run hot?** A few hundred milliwatts barely
  needs thinking about; several watts in a small sealed box will cook. An order-of-magnitude (a
  cool sensor vs. a warm SBC vs. a hot power stage) picks "a few vents" vs. "engineer the airflow"
  vs. "this needs a fan or a real calc."
- **Indoor, or sealed / outdoor?** Indoor and dry → open vents, passive. Wet, dusty, or
  ingress-rated → the holes fight the seal; that fork hands off to
  [sealing-ingress](sealing-ingress.md#decision-rules) and switches to conduction.
- **Is passive enough, or is a fan available / acceptable?** Noise, power, dust, and a moving part
  are real costs; some products must stay silent and fanless. Knowing whether a fan is on the table
  decides between sizing vents and designing a fan boss.

## Verify

- **Assert (known-by-construction):** **inlets are low and outlets are high** with real **vertical
  separation**, and the **total open area meets the target** with **inlet ≈ outlet**. You *cut* the
  vent pattern, so you **know** its open area — count the slots × their area and divide by the
  vented face: this is known-by-construction, not a temperature recovered from `get_model_info()`
  (which reports bounding box / volume / mass / `valid` / `manifold`, **not** temperature or
  airflow). Confirm every vent **slot ≥ the printable minimum** for the process
  (→ [dfm-additive](dfm-additive.md#decision-rules)).
- **Visual:** `capture_views(...)` and **look** — are the inlets genuinely near the bottom and the
  outlets near the top (a chimney, not all vents bunched on one face), is there a clear path over
  any heatsink's fins, and is no heat source sealed in a dead cavity? This catches a trapped
  heatsink or an all-on-one-level vent pattern the open-area number alone won't.
- **Honesty:** report these as **passive-cooling rules of thumb satisfied — geometry that gives the
  heat a way out — not a verified operating temperature.** Natural convection is not simulated here;
  if the dissipation is real or the parts run near their rating, say it needs a proper thermal calc
  or a measured prototype, and that adding a fan is the move when passive can't hold the rating.

## Sources

- **Ralph Remsburg, *Thermal Design of Electronic Equipment*** (CRC Press) — natural-convection
  cooling of enclosures, the buoyancy-driven inlet-low / outlet-high arrangement and the
  stack/chimney effect, and sizing vent area to the dissipated power; the engineering basis for the
  airflow-direction and open-area framing here, used as the qualitative rule of thumb, not a
  substitute for a thermal calc.
- **Frank P. Incropera et al., *Fundamentals of Heat and Mass Transfer*** (Wiley) — the underlying
  natural-convection physics (buoyancy from the density difference of warm vs. cool air, why warm
  air rises and the chimney draft grows with vertical separation). Used qualitatively for the
  direction-of-flow principle, not to compute a heat-transfer coefficient.
- **Enclosure-vendor venting application notes** (e.g. Hammond and Bud Industries ventilated-case
  and louvered-vent-plate guidance, plus perforated-/honeycomb-panel free-area data) — slots and
  louvers vs. round holes for open-area-per-strength, louvers for rain/splash shedding, inlets low
  / outlets high, and that vent **free area should be a sizeable fraction of the panel and
  proportional to the heat** (commonly tens of percent — there is no single universal figure, so
  it is captured here as a **target range to hit and sanity-check**, not false precision). Axial-fan
  sizes and the 40 mm → 32 mm screw pattern are standard fan datasheet values — take the exact
  pattern, hole size and depth from the chosen fan.
- **Cross-links (single source of truth — linked, not restated):** the **minimum printable vent
  slot** (FDM self-supporting / vertical) is owned by
  [dfm-additive](dfm-additive.md#decision-rules); the **airflow-vs-ingress** tradeoff and the
  sealed/high-IP "conduct instead of vent" path are owned by
  [sealing-ingress](sealing-ingress.md#decision-rules); the **fan-boss / heatsink-bracket boss and
  gusset** *how* is owned by [structure](structure.md#data--defaults).
