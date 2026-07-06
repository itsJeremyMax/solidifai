# Changelog

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
