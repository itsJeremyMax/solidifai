# solidifai model-quality judge rubric
version: 1

Score the rendered model on five axes, each an integer 1-5. Judge ONLY what is
visible in the labeled multi-view render grid plus fidelity to the quoted
brief. Be strict: 4s and 5s must be earned. "It would print and work" is a 3,
not a 5. Give exactly one short sentence of rationale per axis.

## proportion
How intentional the massing and ratios look.
- 1: malformed or degenerate massing; elements at obviously wrong relative scale.
- 2: recognizable but awkward; arbitrary-looking ratios; key elements mis-sized.
- 3: correct, believable massing; nothing offensive, nothing considered.
- 4: deliberate ratios; sizes relate to each other (consistent margins, aligned datums).
- 5: confident, named-ratio proportions; the silhouette reads designed from every view.

## detail_density
Real products carry ribs, bosses, lips, chamfers, recesses. Slabs do not.
- 1: bare primitive(s); a box or cylinder with at most a boolean cut.
- 2: one or two token features; large unbroken slab faces dominate.
- 3: the functional features exist (bosses, lips, recesses) but surfaces stay plain.
- 4: purposeful secondary detail: ribs instead of solid slabs, recessed panels, grips, vents where they belong.
- 5: production-level detail density; every region shows evidence of design intent.

## surface_finish
Edge and surface treatment.
- 1: every edge razor sharp; visible faceting or self-intersection artifacts.
- 2: a few fillets or chamfers, applied inconsistently.
- 3: correct massing but unbroken edges and slab faces remain on visible surfaces.
- 4: visible edges broken consistently; transitions blended; faces clean.
- 5: a coherent edge language everywhere (consistent radii, lead-ins, no stray sharp edge).

## realism
Would a stranger read this as a render of a real product?
- 1: reads as a programming exercise, not an object.
- 2: reads as a rough prototype; major giveaways.
- 3: plausible 3D print; would pass on a hobby-printing site.
- 4: reads as a designed product; minor giveaways only.
- 5: indistinguishable from a commercial product's CAD render.

## brief_fidelity
Does the model do what the brief asked?
- 1: misses the point of the brief.
- 2: addresses the theme but violates a stated constraint.
- 3: meets the letter of the brief; ignores implied needs.
- 4: meets stated and implied needs (access, clearance, usability).
- 5: meets everything and resolves unstated conflicts sensibly.

## Output contract
Respond with ONLY this JSON object (no prose before or after, no code fence):

{"proportion": {"score": <1-5>, "why": "<one line>"},
 "detail_density": {"score": <1-5>, "why": "<one line>"},
 "surface_finish": {"score": <1-5>, "why": "<one line>"},
 "realism": {"score": <1-5>, "why": "<one line>"},
 "brief_fidelity": {"score": <1-5>, "why": "<one line>"}}
