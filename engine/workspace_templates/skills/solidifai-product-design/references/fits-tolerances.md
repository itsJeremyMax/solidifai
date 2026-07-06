# fits & tolerances lens

Grounded judgment for **how two parts share a dimension** — whether a shaft should spin in a bore, sit
in it without play, or never come back out. All values mm. These are **fit-selection rules of thumb,
not a verified tolerance stack**: they tell you *which class of fit* to aim for and roughly how big the
gap should be relative to the feature, but the actual gap that lands depends on the **process
capability** of whatever makes the part — so size the fit to the process and, when the fit really
matters, say it needs a stack-up against the real machine, not a number this lens implies.

This lens owns the **fit-class system** — clearance vs. transition vs. interference, and the
running/sliding/locational/press families inside them — plus tolerance-stack-up basics. It does **not**
own the **baseline mating-clearance number** (the per-process slip/press gap between two parts): that
canonical value is owned by [solidifai-modeling](../../solidifai-modeling/SKILL.md#multi-part-models),
linked here, not restated. This lens adds *which class* to pick on top of that number. Nor does it own
**fastener clearance/counterbore fits** — those tables live in
[cookbook §11](../../solidifai-modeling/references/build123d-cookbook.md#11-threads--fasteners). And it
does not own **achievable tolerance per process** — that is owned by the family lenses
([dfm-additive](dfm-additive.md), [dfm-subtractive](dfm-subtractive.md),
[dfm-formative](dfm-formative.md)), linked, not restated.

## First: is the shared thing a number, or a profile?

Before choosing a fit class, decide how the two parts stay consistent at all.

- If they share a **number** (a bore diameter, a width, a bolt-circle radius), engineer the fit as a scalar: publish the dimension once on the assembly skeleton and derive each part from it (e.g. `bush_od = nominal + interference`). A round press-fit is exactly this. Do not over-build it.
- If they share a **profile** (a sealing rim, a gasket groove, a cam path, an irregular mating face that both parts must follow), do not reconstruct that shape in each part from a bag of numbers; they will drift. Publish it once with `s.profile(...)` on the skeleton and have the mating part `offset()` it by the clearance. See **solidifai-assemblies**. This keeps the interface a single source of truth and is the right tool whenever copy-pasting a profile into two parts is the alternative.

The fit class below still applies on top of either approach (it sets how much clearance or interference).

## Principle

A fit is the **relationship between two mating dimensions**, not a single size — a hole and the shaft
that goes in it, a lid lip and the bore it drops into. There are only three outcomes, and you pick the
one the function needs: a **clearance** fit always leaves a gap (the part moves or assembles freely), an
**interference** fit always overlaps (the part is forced in and stays), and a **transition** fit
straddles zero (it locates precisely and *might* be slightly snug or slightly loose). Decide the outcome
from what the joint must do — move, locate, or stay put — then size the gap to the **process that can
actually hold it**: a tight transition is meaningless on a loose FDM bore, and an interference press has
to be sized against the real shrink/over-extrusion of the process, not a textbook micron. Build the gap
in **one direction on purpose** (clearance opens the hole / shrinks the shaft; interference does the
reverse), and on a chain of stacked features, remember the gaps **add up**.

## Data & defaults

| Fit class | Family | What it does | Representative *relative* gap | Notes |
|---|---|---|---|---|
| **Clearance** | free-running | spins/slides freely, tolerates dirt + thermal growth | **largest** clearance — order of *several thousandths of the diameter* | bearings, loose pivots; the gap is deliberately generous so it never binds |
| **Clearance** | close-running / sliding | turns or slides with little play, lubricated | **small but always positive** — order of *a thousandth or two of the diameter* | precision spindles, sliding pins; smallest gap that still always moves |
| **Transition** | locational | locates precisely, hand- or light-press to assemble, still comes apart | **straddles zero** — a hair of clearance or a hair of interference | dowels, gear bores, register features where *position* matters more than free motion |
| **Interference** | press / force / shrink | permanent, no fastener; assembled by force or thermal expansion | **always negative (overlap)** — shaft slightly *larger* than the bore | press-fit bushings, heat-set boss; sized to the process's achievable tolerance, not a generic micron |

The **representative gaps above are relative and qualitative on purpose** — the full ISO 286 / ANSI B4.1
grade tables are not transcribed here. The *absolute* baseline gap for a printed/CNC slip or press fit
between two parts is the **mating clearance owned by
[solidifai-modeling](../../solidifai-modeling/SKILL.md#multi-part-models)** — link it and apply the
class *on top* of that number; do not restate it. For **fastener** clearance holes and counterbores use
the tables in [cookbook §11](../../solidifai-modeling/references/build123d-cookbook.md#11-threads--fasteners),
not numbers here.

**Tolerance stack-up (rule of thumb):** when a fit depends on a **chain of dimensions** (several parts
or features end-to-end), the worst case is the **sum of the individual tolerances** along the chain —
`T_total = T₁ + T₂ + … + Tₙ`. Every dimension lands somewhere in its band; the worst case assumes they
all conspire. A fit that looks fine on one feature can vanish once three loose features stack, so check
the **whole chain**, not just the mating pair. (Worst-case sum is the conservative bound; a statistical
RSS sum is looser but needs real process data — beyond a rule of thumb.)

**Achievable tolerance is set by the process — linked, not restated.** Whether a given class is even
holdable depends on the process band: **FDM / SLA run loose** (owned by [dfm-additive](dfm-additive.md)),
**CNC holds tight** (owned by [dfm-subtractive](dfm-subtractive.md)), **molding sits in the middle**
(owned by [dfm-formative](dfm-formative.md)). Read the achievable number from the family lens for the
active process and pick a class the process can actually hit — don't promise a transition fit a loose
process can't hold.

## Decision rules

- **Free-moving (spins, slides, must never bind) → running / sliding clearance.** Open the hole or
  shrink the shaft so the gap is **always positive**; go *free-running* (larger gap) if there's dirt or
  thermal growth, *close-running / sliding* (smaller gap) where play hurts. Apply the class on top of the
  [mating-clearance baseline](../../solidifai-modeling/SKILL.md#multi-part-models).
- **Must locate precisely but still assemble / disassemble → transition (locational).** Aim the gap at
  **zero** so it registers position with almost no play and goes together by hand or a light press —
  dowels, gear bores, alignment features. Only worth specifying if the process can hold near-zero;
  otherwise fall back to a tight clearance plus a locating feature.
- **Permanent / no fastener → interference (press / force / shrink).** Make the shaft slightly **larger**
  than the bore so it's forced in and stays, **sized to the process's achievable tolerance**
  ([family lens](dfm-subtractive.md) for the real band) — too little and it falls out, too much and it
  splits the boss or won't go. For a printed press, lean on the
  [mating-clearance baseline](../../solidifai-modeling/SKILL.md#multi-part-models) and the part's wall
  strength ([structure](structure.md)).
- **Long chain of stacked dimensions → check the worst-case stack.** Sum the tolerances along the chain
  (`T₁ + … + Tₙ`); if the worst case eats the fit, tighten the few dimensions that dominate or redesign
  the chain shorter — don't just tighten everything (that's expensive and often unmakeable).
- **Real, load- or safety-critical fit → flag it.** These pick a class; a real fit needs a stack-up
  against the **actual process capability**. Say so rather than implying this lens sized the joint.

## Questions that matter

- **Does it move, locate, or stay put?** Moving → clearance (running/sliding); locate-but-assemble →
  transition; permanent-no-fastener → interference. This one answer picks the fit family before any
  number.
- **What process makes each part?** The process sets the **achievable tolerance** (FDM/SLA loose, CNC
  tight, molding mid — owned by the [family lenses](dfm-additive.md)), which decides whether the class
  you want is even holdable. A tight transition on a loose process is a fantasy.
- **How many stacked dimensions feed the fit?** One mating pair, or a chain of several features/parts
  end-to-end? More links → check the **worst-case stack**, because the tolerances add and a fit that
  looks fine per-feature can disappear across the chain.

## Verify

- **Assert (known-by-construction):** the **chosen fit class is stated** (clearance running/sliding,
  transition locational, or interference press) and the **gap direction and size are consistent with the
  process tolerance** — clearance always positive, interference always negative, transition near zero,
  each sized within the achievable band of the active process. You *chose* the class and *set* the gap,
  so you **know** them — this is known-by-construction, not a fit recovered from `get_model_info()`
  (which reports bounding box / volume / mass / `valid` / `manifold`, **not** a clearance or an
  interference). `check_interferences()` can confirm a clearance pair reads **adjacent/clear** and a
  press pair reads **overlap** as intended — advisory, judge the flag.
- **Visual:** `capture_views(...)` the mating pair and **look** — is there a visible gap where there
  should be one (clearance), are the faces flush where they register (transition), is the press feature
  the bigger of the two (interference)? This catches a gap built the wrong direction the numbers alone
  won't.
- **Honesty:** report this as a **fit class chosen and a gap sized to the process rule of thumb — not a
  verified tolerance stack.** A real stack-up needs the **actual process capability** (the achievable
  band, owned by the family lenses) summed along the whole dimension chain; these are **fit-selection
  rules of thumb**. If the fit is load- or safety-critical, say it needs a proper stack-up, don't imply
  this lens sized it.

## Sources

- **Machinery's Handbook** (Industrial Press) — the *Limits and Fits* tables (ANSI B4.1 inch classes
  **RC** running/sliding, **LC** locational clearance, **LT** locational transition, **LN** locational
  interference, **FN** force/shrink; and the ISO 286 hole/shaft system). Used here for the **three fit
  families and the class names only** — the full grade tables are **not** transcribed; this lens keeps
  representative *relative* gaps, and the absolute baseline is the linked
  [mating clearance](../../solidifai-modeling/SKILL.md#multi-part-models).
- **ISO 286 — *Geometrical product specifications (GPS) — ISO code system for tolerances on linear sizes***
  — the hole-basis / shaft-basis fit system and the clearance / transition / interference distinction.
  Source of the qualitative class definitions (clearance always positive, interference always negative,
  transition straddles zero), used as the framework, not as a transcribed grade table.
- **J.E. Shigley & C.R. Mischke, *Mechanical Engineering Design*** (McGraw-Hill) — fits and tolerances,
  the clearance/transition/interference framing, and the **worst-case tolerance stack** as the **sum of
  the tolerances along a dimension chain** (`T_total = ΣTᵢ`), with statistical (RSS) summing as the
  looser alternative that needs real process data. The basis for the stack-up rule of thumb here.
- **Cross-links (single source of truth — linked, not restated):** the **baseline mating-clearance
  number** for a printed/CNC slip or press fit is owned by
  [solidifai-modeling](../../solidifai-modeling/SKILL.md#multi-part-models); **fastener clearance /
  counterbore fits** are owned by
  [cookbook §11](../../solidifai-modeling/references/build123d-cookbook.md#11-threads--fasteners); and
  the **achievable tolerance per process** (FDM/SLA loose, CNC tight, molding mid) is owned by
  [dfm-additive](dfm-additive.md), [dfm-subtractive](dfm-subtractive.md), and
  [dfm-formative](dfm-formative.md). This lens owns only the **fit-class system** layered on top.
