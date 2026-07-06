# solidifai-delegation acceptance scenarios

Scenarios an operator (or the agent itself, in the live app) walks to confirm the skill works and
stays safe. Each is written to pass identically whether the harness has workers or not, except
where noted.

## 1. Parity: multi-part assembly, with and without workers

Brief: "a hinged box: base, lid, and a pin."

- With workers: Sol freezes a skeleton, fans out one part worker per part under a round, composes
  once.
- Without workers: Sol authors the three parts in sequence under the same round, composes once.

Pass: both runs produce the same parts, the same composed assembly, and the same
`check_interferences` verdict. Workers changed wall-clock, not the model.

## 2. Parity: image reproduction

Brief: a photo of a spring-loaded clip.

- With workers: one or more grounding scouts research how the clip works and return a structure
  and parts list; Sol builds from it.
- Without workers: Sol grounds inline, then builds.

Pass: the same understood structure and the same first build either way.

## 3. Gate: a specified single part stays inline

Brief: "a 20 x 20 x 20 mm cube with a 5 mm through hole."

Pass: no workers are stood up; Sol builds it directly. Delegation that adds no value is not used.

## 4. Safety: no scout writes the engine

Pass: in any run, only Sol (or a part worker under a round) calls a writing tool
(`execute_script`, `set_part`, `set_params`, `set_skeleton`). Grounding, design, and verify scouts
call only read-only tools.

## 5. Safety: one writer at a time

Pass: no run has two agents writing the live model at once. Part workers write different parts
under one round; verify scouts run only after the model is stable.

## 6. Safety: verify runs on a stable model

Pass: verify scouts run their read-only checks only when no build is in flight; their reported
flags reflect the settled model that Sol then repairs.
