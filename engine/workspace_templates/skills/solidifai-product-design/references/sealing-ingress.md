# sealing & ingress lens

Grounded judgment for a part that has to **keep water and dust out** — an enclosure or lid that
seals against the weather, a washdown, or a dusty shop. All values mm. These are **sealing-design
rules of thumb, not a tested ingress rating**: an IP figure is a **design intent** you aim the
geometry at, not a certification, so size the groove and the squeeze to give the seal a real chance,
and when the rating actually matters say it needs an IP test on a real sample rather than implying
the geometry earned the number.

This lens is about **keeping the inside dry and clean by design**. It is cross-cutting — any
enclosure or lid playbook can pull it. It does **not** own the mating clearance for a press/slip fit
between two un-sealed parts — that canonical gap is owned by
[solidifai-modeling](../../solidifai-modeling/SKILL.md#multi-part-models), linked here, not restated;
a *sealed* gasket or o-ring joint sets its **compression**, not a clearance, and that is owned here.
And sealing trades directly against letting heat out — the **airflow-vs-ingress** tension is shared
with [thermal-ventilation](thermal-ventilation.md#decision-rules): you cannot freely vent a sealed
box, so when the part runs hot that lens switches from cutting vents to conducting heat to the case.

## Principle

Keeping ingress out is about closing every path water and dust can take. Two moves do most of the
work: **squeeze a captive seal** — a gasket, o-ring, or a tongue pressed into a groove — so the
elastomer fills the joint and stays compressed, and **shed or drain water** rather than letting it
pool against a seam. A seal only works when it is **captured and compressed**: give it a groove that
holds it in place and a mating face that squeezes it the right amount (too little and it leaks, too
much and it takes a set or extrudes). Pick a **target IP rating** first — that says how hard the
water and dust are pushing — then choose the closure to match: a splash needs far less than a
hose-down, and immersion needs a continuous captive seal with no vents at all. And for outdoor parts
that are *not* sealed, the opposite move: don't trap water, **drain it** at the low point.

## Data & defaults

| Quantity | Value / rule | Notes |
|---|---|---|
| IP code (IEC 60529) | **two digits: first = solids 0–6, second = liquids 0–8(9)** | First digit is dust/solid-object protection (**5 = dust-protected**, dust limited but not fully excluded; **6 = dust-tight**). Second is water (**4 = splashing**, **5 = jets**, **6 = powerful jets**, **7 = temporary immersion**, **8 = continuous immersion**). An `X` means "not rated for that axis" (e.g. `IPX7`). |
| IP54 | **dust-protected + splashing water** | Dust ingress limited (not tight); water splashed from any direction does no harm. The "lives indoors-ish / light outdoor" bar — a continuous gasket and a snug lid, not necessarily immersion-grade. |
| IP65 | **dust-tight + water jets** | Fully dust-tight, and a **6.3 mm nozzle jet (~12.5 L/min)** from any direction does no harm. The common outdoor / washdown bar — a continuous captive gasket or tongue-and-groove all the way round. |
| IP67 | **dust-tight + temporary immersion (1 m, 30 min)** | Dust-tight and survives being submerged to ~**1 m for ~30 min**. Needs a continuous compressed o-ring or gasket and **no through-vents** — a sealed box. Note IPX7 does **not** imply IPX5/6: immersion-rated is not automatically jet-rated (the water ratings stop being cumulative above 6). |
| Gasket / o-ring compression (static seal) | **~25–30% squeeze** (broader static range ~**15–30%**) | The mating face must crush the seal cross-section by about a quarter to a third so it fills the joint and stays loaded. Too little leaks; much past ~30% takes a compression set or extrudes. Set the **groove depth** to leave the cord standing proud by that squeeze. |
| O-ring groove geometry | **groove depth ≈ 70–85% of the cord Ø** (leaves the squeeze); **groove width slightly > cord Ø** | Sized against the **cord (cross-section) diameter**, not the ring's bore. Depth shallower than the cord gives the ~25–30% squeeze; the groove is a touch wider than the cord so the elastomer has room to deform and roll, with the gland left **~75–85% filled** (room for thermal/swell). |
| Tongue-and-groove sealed lid | **tongue on one half, matching groove on the other; gasket captured in the groove, tongue compresses it** | The lid's tongue presses a captive gasket into the base's groove all the way around — a controlled, even squeeze and a labyrinth path, the standard sealed-enclosure joint. Continuous (no breaks at corners), and the tongue's penetration sets the compression to the ~25–30% target. |
| Drainage / weep (un-sealed outdoor) | **weep hole(s) at the lowest point**, sized to pass water + debris | The opposite of sealing: a part that **isn't** sealed must not **trap** water. Put a drain at the geometric low point so gravity empties it (and any internal condensation), oriented so the part actually drains in service. A trapped pool freezes, corrodes, and breeds the leak you were avoiding. |

**Sealing heuristics (rules of thumb):**

- **Capture and compress.** A seal that isn't held in a groove and squeezed ~25–30% will creep,
  unseat, or leak. Give every gasket/o-ring a groove and a mating face that loads it.
- **Continuous, no breaks.** A seal path is only as good as its worst gap — run the gasket or
  tongue-and-groove **all the way around** with no interruption at corners, screw bosses, or wire
  exits. One unsealed notch defeats the whole rating.
- **A vent and a high IP fight each other.** Every hole is an ingress path; a sealed box can't have
  open vents. If it also runs hot, that tension is owned by
  [thermal-ventilation](thermal-ventilation.md#decision-rules) — conduct the heat out, don't cut
  holes (a gasketed louver is the only compromise, and it costs you the rating).
- **Seal the fasteners too.** Screw holes through a sealed wall are leak paths — use blind bosses,
  sealing washers, or keep fasteners outside the gasket line. The gasket has to be *inboard* of
  every penetration.
- **Drain what you don't seal.** If the part is outdoor but open, the move is the inverse — a weep
  at the low point so water leaves, not a half-hearted seal that just holds the puddle.

## Decision rules

- **Must keep water/dust out → pick an IP target, then a captive seal.** Choose the IP rating from
  the exposure (splash → IP54, jets/washdown → IP65, immersion → IP67), then seal to it: a
  **continuous gasket or o-ring** (or a **tongue-and-groove**) compressed **~25–30%**, the groove
  depth set to leave that squeeze, the seal **inboard of every fastener and port**, and **no
  through-vents**.
- **Sealed + runs hot → you can't vent it.** A high-IP box and open vents are mutually exclusive;
  the airflow-vs-ingress call is owned by
  [thermal-ventilation](thermal-ventilation.md#decision-rules). Conduct the heat to the **case skin
  or an external heatsink** instead of cutting holes — and if the watts are real, say it needs a
  thermal check, not just a seal.
- **Outdoor but un-sealed → drain it, don't trap it.** Put a **weep hole at the lowest point** so
  rain and condensation run out under gravity; an open outdoor part that pools water is worse than
  one that drains. Confirm the low point is actually low **in the installed orientation**.
- **Real ingress requirement / safety-or-warranty-critical → flag it.** An IP figure is a **design
  intent**; if the product genuinely must hold a rating, say it needs an **IP test on a real
  sample** (and that a printed part is rarely watertight without a separate gasket), don't imply the
  geometry certified it.

## Questions that matter

- **Indoor, outdoor, or washdown?** A dry indoor shelf needs no seal; a splashed or rained-on part
  wants a gasket; a hosed-down or immersed part wants a continuous captive seal and no vents. This
  picks the whole approach before any number.
- **What IP target — splash, jets, or immersion?** Splash (IP54), jets/washdown (IP65), or
  temporary immersion (IP67) are very different bars. Knowing which one decides gasket vs.
  tongue-and-groove, how continuous the seal must be, and whether vents are allowed at all.
- **Does it also run hot?** A sealed box that dissipates real power can't vent — that forks to
  [thermal-ventilation](thermal-ventilation.md#decision-rules) and switches to conducting heat out.
  If it's cool, ignore the fork; if it's warm, the two lenses have to be resolved together.

## Verify

- **Assert (known-by-construction):** the **groove is sized for the chosen cord at the squeeze
  target** — depth ≈ 70–85% of the cord Ø so the seal stands proud by **~25–30%**, width a touch
  over the cord — and the seal path (gasket or tongue-and-groove) runs **continuous** with the
  gasket **inboard of every fastener and port**. You *set* the groove and the squeeze, so you
  **know** them — this is known-by-construction, not an ingress rating recovered from
  `get_model_info()` (which reports bounding box / volume / mass / `valid` / `manifold`, **not** a
  leak path or an IP figure). Confirm a **sealed part has no through-vents**.
- **Visual:** `capture_views(...)` and **look** — does the seal groove run unbroken all the way
  around (no gap at a corner or a boss), is the gasket line inboard of the screws and any port, and
  for an outdoor un-sealed part is there a **weep at the actual low point**? This catches an
  interrupted seal path or a missing drain the dimensions alone won't.
- **Honesty:** report this as **sealing geometry that targets the IP rating — a captive seal at the
  squeeze target with no vent paths — not a verified ingress rating.** An IP figure is **design
  intent, not a tested certification**; an FDM part is rarely watertight on its own. If the product
  must actually hold the rating, say it needs an **IP test on a real sample**.

## Sources

- **IEC 60529 — *Degrees of protection provided by enclosures (IP Code)*** — the authority for the
  two-digit code: first digit solids **0–6** (5 = dust-protected, 6 = dust-tight), second digit
  liquids **0–8(9)** (4 = splash, 5/6 = jets, 7 = 1 m / 30 min immersion, 8 = continuous), and that
  the water ratings stop being cumulative above 6 (IPX7 does not imply IPX5/6). Used for the rating
  meanings and the IP54 / IP65 / IP67 examples; the **test itself is the certification**, this lens
  only aims the geometry at the target.
- **Parker O-Ring Handbook** (Parker Hannifin, O-Ring Division) — static-seal gland design: the
  **~25–30% squeeze** for a static o-ring (broader static range ~15–30%), **groove depth shallower
  than the cord** so the ring stands proud by that squeeze, **groove width slightly over the cord**,
  and gland fill left at **~75–85%** for thermal expansion and swell. The basis for the compression
  and groove-vs-cord geometry here, used as the design rule of thumb.
- **Enclosure- and gasket-vendor sealing application notes** (e.g. Hammond / Bud and industrial
  gasket / tongue-and-groove flange guidance) — the **tongue-and-groove sealed lid** (captive
  gasket, tongue compresses it for controlled even squeeze), the **continuous-seal / seal-inboard-
  of-fasteners** rules, and **weep / drain at the low point** for un-sealed outdoor parts so water
  isn't trapped. Qualitative sealing-practice basis, not a substitute for an IP test.
- **Cross-links (single source of truth — linked, not restated):** the **mating clearance** for an
  un-sealed press/slip fit is owned by
  [solidifai-modeling](../../solidifai-modeling/SKILL.md#multi-part-models) (a sealed joint sets
  *compression*, not clearance — that part is owned here); the **airflow-vs-ingress** tradeoff and
  the "conduct instead of vent" path for a sealed-but-hot box are owned by
  [thermal-ventilation](thermal-ventilation.md#decision-rules).
