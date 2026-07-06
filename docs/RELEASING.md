# Releasing solidifai

This is the operator's guide to the release pipeline: how versions get cut, how
cross-platform installers are built and signed, how the in-app auto-updater
works, and the one-time setup the pipeline needs before the first release.

## The pipeline at a glance

```
Conventional Commits on main
        │  (commitlint enforces the format, locally + in CI)
        ▼
release-please  ──opens──▶  a "Release PR" (bumps package.json, writes CHANGELOG.md)
        │  merge the Release PR
        ▼
release-please creates a DRAFT GitHub Release and calls release-build
        │
        ▼
full CI gate, then a 4-job matrix builds the engine + signs Tauri bundles
and uploads every asset to the draft
        │
        ▼
the publish job verifies the updater manifest covers all four platforms and
every expected asset exists, adds SHA256SUMS.txt, and only then flips the
draft to published and mirrors the manifest (latest.json / beta.json)
        │
        ▼
Running apps check the manifest, show "Update available", apply the update,
and show the "What's new" screen on first launch after updating.
```

A release is all-or-nothing: until every platform's assets are built, uploaded,
and verified, the release stays an invisible draft and the updater feed is
untouched. There is no state in which users can see a release with assets
missing for their platform.

## Commit convention

Every commit must follow [Conventional Commits](https://www.conventionalcommits.org/):
`type(scope): summary`, e.g. `feat(updater): add channel toggle`. This drives both
the changelog and the version bump:

- `fix:` → patch (0.1.0 → 0.1.1)
- `feat:` → minor (0.1.0 → 0.2.0)
- `feat!:` / `BREAKING CHANGE:` → major (pre-1.0, a `feat!` bumps the minor)

Enforcement:

- **Local**: a `commit-msg` hook (in `.githooks/`, wired by the `prepare` npm
  script on `pnpm install`) runs commitlint on every commit.
- **CI**: `.github/workflows/commitlint.yml` lints every commit in a pull request.

## How a release is cut

1. Land Conventional Commits on `main` as normal.
2. `release-please` keeps a **Release PR** open that accumulates the pending
   changes, the next version, and the generated `CHANGELOG.md` entry.
3. When you're ready to release, **merge the Release PR**. release-please
   creates a **draft** GitHub Release for `vX.Y.Z` and the same workflow run
   calls `release-build.yml` with the tag.
4. release-build re-runs the full CI gate on the release commit, builds and
   signs every platform, uploads all assets to the draft, verifies the set is
   complete, and publishes the release (which is when the `vX.Y.Z` git tag is
   created, pinned to the built commit).

If a platform build fails, the release stays a draft and nothing is visible.
Two recovery paths:

- **Environmental failure** (runner hiccup, registry outage): re-run the failed
  jobs on the same workflow run. The publish gate runs again once they pass.
- **A fix is needed**: land it on `main`, then run **release-build** manually
  (Actions → release-build → Run workflow, with the tag, e.g. `v0.2.0`). It
  builds the current branch head and re-targets the tag to that commit on
  publish. It refuses to run against an already-published release.

You never bump versions or write changelog entries by hand. The Rust crate
version in `src-tauri/Cargo.toml` is intentionally decoupled and stays put; the
app version is single-sourced from `package.json` (Tauri reads it via
`tauri.conf.json` `"version": "../package.json"`).

## Channels: stable and beta

- **Stable** releases come from `main` (`release-please.yml`) and publish
  `latest.json`.
- **Beta** releases come from the `beta` branch (`release-please-beta.yml`,
  using `release-please-config.beta.json`) and produce `vX.Y.Z-beta.N`
  pre-release tags + `beta.json`.

Whenever you create (or re-cut) the `beta` branch from `main`, first sync
`.release-please-manifest.beta.json` to the current stable version (the value
in `.release-please-manifest.json`). release-please computes the next beta from
that baseline; a stale baseline yields a beta that is semver-older than the
published stable, and publishing it would clobber `beta.json` and pin
beta-channel users behind stable.

Both channel manifests are mirrored to a single permanent, non-prerelease GitHub
Release tagged **`updater`** (created automatically on the first build). The app
checks `…/releases/download/updater/latest.json` or `…/beta.json`. This matters:
GitHub's `/releases/latest/` redirect resolves only to the latest *non-prerelease*,
so a beta manifest published on a pre-release could never be fetched from there.
The fixed `updater` release gives both channels a stable URL and the `publish`
job (which runs once, after the whole matrix, and only after the release is
verified complete and public) avoids any per-job race. Do not delete the
`updater` release.

Users opt into beta in **Settings → Updates → Channel**.

## The build matrix

`release-build.yml` runs four jobs (no universal2: the embedded interpreter and
the OpenCASCADE/VTK wheels are architecture-specific):

| Job | Runner | Target |
|---|---|---|
| macOS Apple Silicon | `macos-14` | `aarch64-apple-darwin` |
| macOS Intel | `macos-15-intel` | `x86_64-apple-darwin` |
| Windows | `windows-latest` | `x86_64-pc-windows-msvc` |
| Linux | `ubuntu-22.04` | `x86_64-unknown-linux-gnu` |

Each job builds the engine bundle (`scripts/build-engine-dist.*`) into
`src-tauri/engine-dist`, then `tauri-action` builds + signs the app and uploads
to the draft Release. The engine's offscreen view-capture smoke test needs a
virtual display on the headless Linux runner, so that job runs under
`xvfb-run`. After all four jobs finish, the `publish` job verifies the
matrix-merged manifest lists all four platforms and that every expected asset
is on the release, publishes a `SHA256SUMS.txt` covering every asset (with a
`SHA256SUMS.txt.sig` minisign signature made with the same release key), flips
the draft to published, and mirrors the manifest to the `updater` release.

### Release assets

Updater payloads stay **engine-less** (a few MB) and are never replaced after
signing; installed apps fetch their pinned engine from the permanent `engine`
release, so an engine-less install or update self-heals on first launch.
Engine-full offline installers use formats or names disjoint from the updater
payloads:

| Asset | What it is |
|---|---|
| `solidifai_X.Y.Z_aarch64.dmg` / `_x64.dmg` | macOS installers (Apple Silicon / Intel), engine included |
| `solidifai_X.Y.Z_x64-setup.exe` | Windows installer, downloads the engine on first launch |
| `solidifai_X.Y.Z_x64-offline-setup.exe` | Windows installer, engine included (no network needed) |
| `solidifai_X.Y.Z_amd64.deb` | Debian/Ubuntu package, engine included |
| `solidifai_X.Y.Z_amd64.AppImage` | Portable Linux binary, downloads the engine on first launch |
| `*.app.tar.gz`, `*.sig`, `latest.json` | Auto-updater plumbing, not for manual download |
| `SHA256SUMS.txt` (+ `.sig`) | Checksums for verifying manual downloads |

The publish job also appends a short "Which file do I download?" guide to every
release's notes, so the release page explains this to first-time downloaders.

Engine assets on the permanent `engine` release are content-addressed:
`solidifai-engine-<platform>-<rev>.{manifest.json,full.tar.zst}` plus
incremental `solidifai-engine-<platform>-<prev>.<rev>.pack.tar.zst` packs and
a `solidifai-engine-index.json` the app reads to resolve its pinned rev. The
rev is a hash of the resolved dependencies + engine source, not an app
version: one engine rev serves every app version that pins it.

The checksums file exists for people (and package managers) verifying a manual
download:

```sh
sha256sum -c SHA256SUMS.txt --ignore-missing
# The updater pubkey in tauri.conf.json is a base64-encoded minisign key file.
echo '<pubkey from tauri.conf.json>' | base64 -d > minisign.pub
minisign -Vm SHA256SUMS.txt -p minisign.pub
```

The in-app updater does not read it; it already verifies the minisign
signature on every update payload, and engine assets carry per-file hashes
inside a signed manifest.

## The engine bundle

A downloaded app cannot rely on the dev `engine/.venv`, so the build ships a
self-contained engine:

- `scripts/build-engine-dist.sh` (and `.ps1` on Windows) installs a relocatable
  standalone CPython (via `uv`), installs the engine's production dependencies
  into it, and runs `scripts/prune_engine.py`.
- `prune_engine.py` removes dev/unused packages (matplotlib, pytest) on every
  platform, and on **macOS** also subsets VTK to the native dependency closure the
  offscreen renderer plus OpenCASCADE actually link (computed empirically with
  `otool`, seeded from every native module so OCP/lib3mf deps are kept). This
  trims the macOS bundle from ~918 MB of site-packages to roughly **700 MB
  installed** (about a 400 MB compressed download). Native-lib subsetting is
  macOS-only for now: Linux's auditwheel hash-renames libs while `ldd` reports
  unmangled SONAMEs, so a basename-matched closure could delete a needed lib;
  validating that mapping on a Linux runner (so Linux/Windows also shrink) is a
  tracked follow-up. Until then those platforms ship the full VTK shared libs
  (the build smoke imports OCP + lib3mf + build123d, so a broken bundle fails CI
  rather than shipping).
- The result is shipped as a Tauri resource (`bundle.resources: ["engine-dist"]`).
  At runtime `engine.rs` resolves the bundled interpreter from the resource dir
  in release builds and falls back to the dev tree under `tauri dev`. The bundled
  interpreter also serves `python -m solidifai_mcp` for external agent tools.

To build and validate the bundle locally (macOS/Linux):

```sh
scripts/build-engine-dist.sh 3.12   # writes src-tauri/engine-dist, runs a smoke test
```

## In-app updates and "What's new"

- **Behavior** (Settings → Updates): `notify` (default, a quiet "Update available"
  indicator the user clicks to install), `autoDownload` (downloads in the
  background, then offers restart), or `silent` (installs without prompting).
- **What's new**: on the first launch after an update, a fullscreen modal renders
  the `CHANGELOG.md` sections added since the version the user last launched.
  The bundled `CHANGELOG.md` is the single source of truth.
- **All four targets update.** Every matrix job publishes its engine assets
  (the Windows publish runs the same bash script under Git Bash) and lands in
  the updater manifest, so macOS, Windows, and Linux all follow the same
  tiny-update-plus-engine-fetch path. If a platform's manifest entry were ever
  missing, the app reports "up to date" rather than erroring.

## One-time setup (required before the first release)

These steps need the GitHub repo and credentials and cannot be done from a local
worktree.

1. **Create the public repo** `github.com/itsJeremyMax/solidifai`, add it as the
   `origin` remote, and push `main` (and `beta` if you want a beta channel).

2. **Generate the updater signing keypair** and wire it up:
   ```sh
   pnpm tauri signer generate -w ~/.solidifai-updater.key
   ```
   - Paste the printed **public key** into `src-tauri/tauri.conf.json` at
     `plugins.updater.pubkey` (replacing the `REPLACE_WITH_OUTPUT_OF_...`
     placeholder), and commit it (the public key is safe to commit).
   - Add the **private key** and its password as GitHub Actions repository
     secrets: `TAURI_SIGNING_PRIVATE_KEY` and
     `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`. The public key in the config and the
     private key in secrets MUST be from the same `signer generate` run, or the
     updater will reject every download.

3. **Allow release-please to open PRs**: in repo Settings → Actions → General,
   enable "Allow GitHub Actions to create and approve pull requests".

4. **Create the `RELEASE_PLEASE_TOKEN` secret** (required, not optional): a
   fine-grained PAT or GitHub App token with `contents: write` +
   `pull-requests: write`. release-please uses it instead of the default
   `GITHUB_TOKEN` because **PRs created with the default token do not trigger
   other workflows**, so the Release PR would never get its CI or commitlint
   checks. Add it as the repo secret `RELEASE_PLEASE_TOKEN`.

5. **Cut the first release**: merge the Release PR that release-please opens,
   then watch the chained `release-build` run produce installers and the
   `publish` job flip the draft public and create the `updater` release with
   `latest.json`.

6. **Verify end-to-end on each OS**: install the build, confirm the app launches
   and the engine runs, then publish a second release and confirm the
   "Update available" flow and the "What's new" modal both work.

## Later: OS-level signing (not required for v1)

The pipeline ships with updater (minisign) signing only. Until OS signing is
added, macOS/Windows users see a one-time Gatekeeper/SmartScreen prompt on first
launch. To remove it later, add the secrets and `tauri-action` inputs for:

- **macOS**: Apple Developer ID Application certificate + notarization
  (`APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_ID`,
  `APPLE_PASSWORD`, `APPLE_TEAM_ID`).
- **Windows**: an Authenticode code-signing certificate.
