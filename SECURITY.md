# Security policy

## Supported versions

solidifai is an early MVP under active development. Security fixes land on the
latest release and on `main`; older versions are not maintained.

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue.

Use GitHub's private vulnerability reporting: go to the **Security** tab of this
repository and choose **Report a vulnerability**. That opens a private advisory
visible only to the maintainers.

When you report, include:

- what the issue is and the impact you can demonstrate,
- the steps or a minimal script to reproduce it,
- the version or commit you tested against, and your OS.

You can expect an acknowledgement within a few days. Once a fix is ready we will
coordinate a release and credit you in the advisory unless you prefer to stay
anonymous.

## Scope notes

solidifai runs a CLI coding agent you provide, in an embedded terminal, against a
local CAD engine. It does not host a model or hold API keys. The areas most worth
scrutiny are the Tauri IPC surface, the workspace provisioner (which writes files
into folders you choose), the local engine RPC socket, and the auto-updater's
signature verification.

## Dependency scanning and accepted advisories

CI runs dependency vuln scanning on every push and pull request (`pnpm audit`,
`pip-audit`, `cargo audit`) plus CodeQL. New advisories fail the build. The
following are tracked, accepted-risk exceptions:

- **VTK 9.3.1 (PYSEC-2025-224 / 225 / 226).** VTK is pinned transitively by
  `cadquery-ocp` (OCCT/VTK ABI coupling) and cannot be bumped independently; the
  fix (VTK 9.5.1) requires a coordinated OCP/OCCT/VTK stack upgrade, tracked as
  future work. VTK is used only for offscreen rendering of the user's own local
  models, not for parsing untrusted input, so exposure is low. Ignored in the
  `pip-audit` CI step.
- **Unmaintained-crate warnings (RUSTSEC) for the gtk3-rs Linux bindings and a
  few transitive macro crates.** These come from Tauri's Linux GTK stack, are
  warnings (not vulnerabilities), and `cargo audit` does not fail on them.
