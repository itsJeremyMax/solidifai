# Changelog

## [0.6.0](https://github.com/itsJeremyMax/solidifai/compare/v0.5.0...v0.6.0) (2026-07-09)


### Features

* **app:** show assembly occurrences and joints in the tree panel ([f20129e](https://github.com/itsJeremyMax/solidifai/commit/f20129e248129527b6fa1c0fd03185e9e338be48))
* **engine:** occurrence-based instancing (mirrored occurrences) + joints/mates ([b9a9250](https://github.com/itsJeremyMax/solidifai/commit/b9a9250adea79f6ae047289f85761f03732c17cb))
* **engine:** real modeled ISO threads via helix sweep ([f101e3e](https://github.com/itsJeremyMax/solidifai/commit/f101e3eef0137d8a95fdb82d4a984696db15a280))
* **engine:** spatial measure/query tools (measure_between, query_faces, thickness_at) ([033b471](https://github.com/itsJeremyMax/solidifai/commit/033b47110f4619097a41de7a3b9062948fbe954a))


### Bug Fixes

* **engine,app:** exact occurrence identity in model.json + instanced subassembly handling ([9f186c6](https://github.com/itsJeremyMax/solidifai/commit/9f186c6c5ec125e71d330adeab9ba2dbd0bb223a))
* **engine:** assembly cache/serialize/flatten correctness + instancing dedup ([f314fb8](https://github.com/itsJeremyMax/solidifai/commit/f314fb89fb5294d787ba5f06e7c1f6a15ac3ac0e))
* **engine:** harden worker crash-isolation, history transactionality, and split-brain/param guards ([3944ba8](https://github.com/itsJeremyMax/solidifai/commit/3944ba8b0601a6581a7550fe872c09320e162d8e))
* **engine:** make part_signature chirality-sensitive so mirrored parts don't merge ([01b7865](https://github.com/itsJeremyMax/solidifai/commit/01b78653df6226310113fb1f26cc811cf990efa9))
* **engine:** make the feature system work in assembly mode + fix inference/targeting bugs ([df612f4](https://github.com/itsJeremyMax/solidifai/commit/df612f41d7513acb89e17c7f252f008a3341b550))
* **engine:** pass structured failure fields through the RPC envelope + harden the MCP bridge ([383f890](https://github.com/itsJeremyMax/solidifai/commit/383f890048f401a633eab25a3115194689056c7c))
* **engine:** safe-bevel empty/mixed-parent guards + profile-aware counterbore bore ([b6242a2](https://github.com/itsJeremyMax/solidifai/commit/b6242a27af162d41ce6861a889aa84d36df1da25))
* **engine:** satisfy mypy on the new spatial/error-envelope code ([6c46c21](https://github.com/itsJeremyMax/solidifai/commit/6c46c2133b6b0cf15682deea07aca38b90fcc88d))
* **engine:** serve engine connections concurrently so an idle client can't starve others ([13fae41](https://github.com/itsJeremyMax/solidifai/commit/13fae41ed34c1c490a529ad521f24a3bedc3276e))
* **engine:** ship raised-error tracebacks over the worker pipe so scriptLine surfaces ([1a9c753](https://github.com/itsJeremyMax/solidifai/commit/1a9c75324358525ef913e82cd1e7161591057268))
* **engine:** stop Compound child-theft corrupting the model + export from snapshot ([38c354f](https://github.com/itsJeremyMax/solidifai/commit/38c354fd32499ed23787042926dae43aab1849d1))
* **engine:** validate assembly-mode set_params against the skeleton PARAMS schema ([4f3ebff](https://github.com/itsJeremyMax/solidifai/commit/4f3ebff8f98c81f8cbac2e34ed1036adc7f731b7))

## [0.5.0](https://github.com/itsJeremyMax/solidifai/compare/v0.4.0...v0.5.0) (2026-07-08)


### Features

* **engine:** isolate builds in a crash-proof worker process ([dc64fbb](https://github.com/itsJeremyMax/solidifai/commit/dc64fbbac649e4ac4fc54b6830da494692421925))
* **engine:** phase-aware update progress + ring-gauge status pill ([133eea1](https://github.com/itsJeremyMax/solidifai/commit/133eea1472dec306aa20c452ff160e11648df829))
* **engine:** self-clamping safe_chamfer/safe_fillet ([9f4d820](https://github.com/itsJeremyMax/solidifai/commit/9f4d820aa8c19f772857c781f89e232b7b42dd27))
* **macos:** explain Documents-folder access in the permission prompt ([ce9ace3](https://github.com/itsJeremyMax/solidifai/commit/ce9ace3f2db425e7bedf12e8d215e94f8e085de1))


### Bug Fixes

* **about:** source "What's new" from the changelog, not a stale hardcoded list ([34e5f43](https://github.com/itsJeremyMax/solidifai/commit/34e5f43bd115f506ec89459c3b40ea5c068110f1))
* **about:** stop copying a workspace path the diagnostics table never shows ([1257188](https://github.com/itsJeremyMax/solidifai/commit/1257188ad2e6b7a3703c1c52bde3d7befb109e5a))
* **engine:** annotate ctx in safe bevel target resolution for mypy ([582c0b7](https://github.com/itsJeremyMax/solidifai/commit/582c0b7a081dd3f5c75891b8846c8cac7d4a800a))
* **engine:** audit batch 1 - screw-size parse, counterbore pocket, worker resolver ([c946ace](https://github.com/itsJeremyMax/solidifai/commit/c946ace54b8f6728329093e5d1a0a191e8227ea4))
* **engine:** audit fixes for DFM checks and motion range ([7c2c86f](https://github.com/itsJeremyMax/solidifai/commit/7c2c86f025092def2283c9aea06d75675674205a))
* **engine:** audit fixes for export, standards, reverse, drawing ([b44cec8](https://github.com/itsJeremyMax/solidifai/commit/b44cec8aea1360ebb47aa959dd1f0a74a0cba684))
* **engine:** audit fixes for metrology and spec correctness ([6610cd3](https://github.com/itsJeremyMax/solidifai/commit/6610cd3f3fa64303724338b821e7a31586c4bcc2))
* **engine:** audit fixes for session state integrity ([67721d7](https://github.com/itsJeremyMax/solidifai/commit/67721d74588c6c3ce068229f06942d0e9113d06a))
* **engine:** carry the asset fingerprint through cache promotion ([e4e4993](https://github.com/itsJeremyMax/solidifai/commit/e4e499379df592cd6997de6210147edb1d57ba41))
* **engine:** re-audit fixes for requirements, fabrication, standards, drawing, motion ([2e75c48](https://github.com/itsJeremyMax/solidifai/commit/2e75c4840c9159f3044f57c640f4860b4e09e81d))
* **engine:** repair three worker/bevel regressions from the crash-isolation refactor ([7363f3a](https://github.com/itsJeremyMax/solidifai/commit/7363f3a56241357e7533474f1943524a26aebedc))
* **engine:** repair two regressions from the audit fix pass ([ce4f46d](https://github.com/itsJeremyMax/solidifai/commit/ce4f46d01ca5ffb37882a1d1e573db3bc2195678))
* **engine:** restore clean error type across the worker boundary ([de7f321](https://github.com/itsJeremyMax/solidifai/commit/de7f3212ff9f56d2c1b3ae17b07f195234716f3b))
* **engine:** revalidate imported-asset fingerprint in the node cache ([f29dbc4](https://github.com/itsJeremyMax/solidifai/commit/f29dbc4be77874728abfb4236960fb53ba70633f))
* **engine:** snapshot last-good params + reflect module-level build args ([8734b8d](https://github.com/itsJeremyMax/solidifai/commit/8734b8df35033508b82079b339f04b1fdab7ba2c))
* **hooks:** honor ruff excludes for staged files (--force-exclude) ([653f869](https://github.com/itsJeremyMax/solidifai/commit/653f8696e9591311b3cec0af8629c0c34ad2bf15))
* **render:** correct build material + reject unmeshable geometry ([cf8479d](https://github.com/itsJeremyMax/solidifai/commit/cf8479d522ef2e12c2f8f0e4b93543efedfe085c))
* **ui:** swap import/export button icons ([fec65dc](https://github.com/itsJeremyMax/solidifai/commit/fec65dcc98688f02dce5d5a3baa717619126bb5f))
* **updater:** add vertical spacing between What's new groupings ([2878c7d](https://github.com/itsJeremyMax/solidifai/commit/2878c7df2c2650c1e250d66886ad6c803eff12f1))

## [0.4.0](https://github.com/itsJeremyMax/solidifai/compare/v0.3.0...v0.4.0) (2026-07-07)


### Features

* **engine:** weave custom instructions into provisioned AGENTS.md ([fe6d3e6](https://github.com/itsJeremyMax/solidifai/commit/fe6d3e6b75e10b8dc82e25d8189496d1f3a65c11))
* **settings:** split into App and Workspace settings, add Custom instructions ([a1486a5](https://github.com/itsJeremyMax/solidifai/commit/a1486a5a538cf4f70f362a6d3014e82af4d13e92))
* **ui:** group header nav into libraries + utilities, add a Help page ([13f39f2](https://github.com/itsJeremyMax/solidifai/commit/13f39f20f9e05a143966db6037e8f6a44b7e91e0))
* **updater:** show real release notes in the update UI ([9626395](https://github.com/itsJeremyMax/solidifai/commit/9626395fbb352b436ba143463eaccdb84ec50bd5))


### Bug Fixes

* **engine:** exclude region markers from the AGENTS.md word ceiling ([bdde65a](https://github.com/itsJeremyMax/solidifai/commit/bdde65ae4a40d6c9b4105b2e7d834bfcf1dc0e18))
* **home:** open from the whole card and hero image, de-dup the hero ([2fe5b65](https://github.com/itsJeremyMax/solidifai/commit/2fe5b6563d7ffdf2ce6de0dc4c1af22c1bcd4b09))
* **inspector:** don't nest the section action button in the header toggle ([8d90ed8](https://github.com/itsJeremyMax/solidifai/commit/8d90ed865c0620ff1be87675bd0842740ee42894))
* **ui:** stop nesting tag-chip buttons inside the card open button ([50baff8](https://github.com/itsJeremyMax/solidifai/commit/50baff879374612a5a41c93d3320b4172f5061d6))
* **updater:** keep What's new visible while installing, tidy mock notes/version ([1419e39](https://github.com/itsJeremyMax/solidifai/commit/1419e39c05a2638ed62560721bb5a7b758600f7f))
* **updater:** show a single update CTA at a time, never stacked ([28ce93a](https://github.com/itsJeremyMax/solidifai/commit/28ce93a01cfd44ffe3230bac03105bb5186e11b7))
* **updater:** show the mock update from Check now in dev builds ([4192df5](https://github.com/itsJeremyMax/solidifai/commit/4192df57c789ba6c8b4040f6459a171c0f2f6247))

## [0.3.0](https://github.com/itsJeremyMax/solidifai/compare/v0.2.0...v0.3.0) (2026-07-07)


### Features

* **updater:** context-aware update UX, periodic checks, and reliability fixes ([0823b24](https://github.com/itsJeremyMax/solidifai/commit/0823b243ac603c42de4d4959f0c543eb351e4974))


### Bug Fixes

* **engine:** satisfy clippy::unnecessary_unwrap in ensure() self-heal ([#10](https://github.com/itsJeremyMax/solidifai/issues/10)) ([60f4c7b](https://github.com/itsJeremyMax/solidifai/commit/60f4c7bb926f166bfa45b9ca6123d55d0c628aae))
* **engine:** stop shipping mutable bytecode that breaks incremental update integrity ([193b55d](https://github.com/itsJeremyMax/solidifai/commit/193b55d49156b5e97d4ee550479b631e8b0453b7))

## [0.2.0](https://github.com/itsJeremyMax/solidifai/compare/v0.1.2...v0.2.0) (2026-07-06)


### Features

* **release:** subset VTK native libs on Linux too (exact DT_NEEDED closure) ([35d376e](https://github.com/itsJeremyMax/solidifai/commit/35d376ee4bfe8d94d70c99209845e442b36aac64))
* **shell:** enforce a single app instance; a second launch focuses the first ([e104900](https://github.com/itsJeremyMax/solidifai/commit/e104900a44cb5d65401c9f7cdc58fcace69d340e))


### Bug Fixes

* **engine-py:** handle-wait parent watchdog on nt; utf-8 materials; wider orca probes ([b7ab074](https://github.com/itsJeremyMax/solidifai/commit/b7ab074cd29aa570bba23858fa54e58d8b9644d8))
* **engine:** bound the control-channel roundtrip so a wedged host fails the tool call ([286e0b4](https://github.com/itsJeremyMax/solidifai/commit/286e0b46344523f73840328981ba5d0ec1638b79))
* **engine:** make fetch/seed single-flight and race-free, stream downloads, retry errored workspaces ([5adc48d](https://github.com/itsJeremyMax/solidifai/commit/5adc48d1f01ccaece4ed954b7949f3a65fa59398))
* **ipc:** engine endpoints live in the per-user config dir, not the workspace root ([0df69b1](https://github.com/itsJeremyMax/solidifai/commit/0df69b12a1466a7c4bfdd02200a6852a33885c9b))
* **pty:** pick the terminal shell per OS so Windows gets cmd.exe, not /bin/zsh ([9b13ca7](https://github.com/itsJeremyMax/solidifai/commit/9b13ca7b3b3368d083ab64ddc813b92a05bb0cba))
* **release:** publish job is the single writer of latest.json (kills the per-leg merge race) ([5678d34](https://github.com/itsJeremyMax/solidifai/commit/5678d34dca3f6950bf01f43d83b4be72391df8e1))
* **ui:** windows-aware path display, quiet offline update check, one-step settings back ([b51ac4a](https://github.com/itsJeremyMax/solidifai/commit/b51ac4abbdfb78b85acc9019cc16594086a1f75e))
* **updater:** shut engines down before the Windows install handoff, relaunch if it fails ([60caa05](https://github.com/itsJeremyMax/solidifai/commit/60caa057bb92bf6110d8e8d42e87190fa44ebac7))
* **viewport:** flip WebGL readback rows, track DPR changes, surface GPU device loss ([7b9a970](https://github.com/itsJeremyMax/solidifai/commit/7b9a97050a30462bf5ac29abb1bdd7b46b2e6e93))

## [0.1.2](https://github.com/itsJeremyMax/solidifai/compare/v0.1.1...v0.1.2) (2026-07-06)


### Bug Fixes

* **shell:** login shell and TERM default so the terminal works from a Finder launch ([2905969](https://github.com/itsJeremyMax/solidifai/commit/29059694f8f1d64d9b4cfb3acd65102ff5096e2f))
* **ui:** always launch at home; restoring the last route left Back dead ([548d692](https://github.com/itsJeremyMax/solidifai/commit/548d692f7b3f37e818769464bece25deb5f51278))
* **ui:** show the update indicator on every surface, not just the editor ([d942042](https://github.com/itsJeremyMax/solidifai/commit/d942042bd48c924366cce26e49dc6f4737fdc0b3))
* **viewport:** attach IBL only after renderer init; PMREM crashed the WebGL fallback ([15af7b5](https://github.com/itsJeremyMax/solidifai/commit/15af7b587da5269ab6803d699901b7420dabbe66))

## [0.1.1](https://github.com/itsJeremyMax/solidifai/compare/v0.1.0...v0.1.1) (2026-07-06)


### Bug Fixes

* **macos:** ad-hoc sign bundles so Gatekeeper offers Open Anyway instead of "damaged" ([fe2bc69](https://github.com/itsJeremyMax/solidifai/commit/fe2bc69f403590fdc0ccbf9248abfb8fb1d7f135))

## 0.1.0 (2026-07-06)


### Features

* initial release ([7d98847](https://github.com/itsJeremyMax/solidifai/commit/7d98847779eec80ed003a17561c999ce52bad80d))
