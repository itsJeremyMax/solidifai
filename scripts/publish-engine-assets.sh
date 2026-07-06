#!/usr/bin/env bash
# Publish this platform's engine assets to the permanent `engine` GitHub release:
# sign the manifest, emit an incremental pack vs the previous published rev, and
# upload everything with sha256 sidecars. Run by release-build.yml after
# build-engine-dist has produced engine-out/. Outputs this platform's manifestHash
# (for the publish-engine-index job) to $GITHUB_OUTPUT when set.
#
# Env: GH_TOKEN, TAURI_SIGNING_PRIVATE_KEY[_PASSWORD], REPO (owner/name).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${ENGINE_OUT_DIR:-$ROOT/engine-out}"
EP="$ROOT/src-tauri/target/release/engine-pack"
[ -x "$EP" ] || EP="$EP.exe" # Windows (run under Git Bash)
DIST="$ROOT/src-tauri/engine-dist"

# macOS ships shasum but not sha256sum; Git Bash on Windows the reverse.
sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi
}

MAN="$(ls "$OUT"/solidifai-engine-*.manifest.json | head -1)"
[ -n "$MAN" ] || { echo "no manifest in $OUT"; exit 1; }
base="$(basename "$MAN" .manifest.json)"          # solidifai-engine-<plat>-<rev>
plat_rev="${base#solidifai-engine-}"               # <plat>-<rev>
plat="${plat_rev%-*}"                              # <plat>  (rev has no dashes)
rev="${plat_rev##*-}"
manifest_hash="$(jq -r .manifestHash "$MAN")"

# Ensure the permanent, non-prerelease engine release exists. Four matrix legs
# race here on the very first release; tolerate losing the create.
if ! gh release view engine -R "$REPO" >/dev/null 2>&1; then
  gh release create engine -R "$REPO" --title "Engine bundles" --latest=false \
    --notes "Content-addressed engine manifests, full archives, and packs. Do not delete." || true
  gh release view engine -R "$REPO" >/dev/null
fi

# Incremental pack vs the NEWEST previously published rev for this platform, if
# any (upload time, newest first: packing against the oldest rev would make
# clients on the actual previous rev fall back to the full download).
prev="$(gh release view engine -R "$REPO" --json assets \
  --jq "[.assets[] | select(.name | startswith(\"solidifai-engine-$plat-\")) | select(.name | endswith(\".manifest.json\"))] | sort_by(.createdAt) | reverse | .[].name" \
  2>/dev/null | grep -v "$rev" | head -1 || true)"
if [ -n "$prev" ]; then
  gh release download engine -R "$REPO" -p "$prev" -D /tmp/prev --clobber
  prev_rev="$(basename "$prev" .manifest.json)"; prev_rev="${prev_rev##*-}"
  # Single dot between revs: GitHub rewrites ".." in uploaded asset names to
  # ".", which made the published pack invisible to build-engine-index.py.
  # Revs are fixed-length hex with no dots, so the name stays unambiguous.
  PACK="$OUT/solidifai-engine-$plat-$prev_rev.$rev.pack.tar.zst"
  "$EP" pack "$DIST" "$MAN" "/tmp/prev/$prev" "$PACK"
  sha256 "$PACK" | awk '{print $1}' > "$PACK.sha256"
fi

# Sign the manifest with the updater key (the app trusts the same pubkey).
pnpm tauri signer sign -k "$TAURI_SIGNING_PRIVATE_KEY" -p "${TAURI_SIGNING_PRIVATE_KEY_PASSWORD:-}" "$MAN"

gh release upload engine -R "$REPO" "$OUT"/solidifai-engine-"$plat"-* --clobber

# The notices also ride inside every bundle archive; a standalone copy on the
# release makes them reachable without downloading a 100+ MB archive.
cp "$ROOT/scripts/ENGINE-THIRD-PARTY-NOTICES.txt" "$OUT/THIRD-PARTY-NOTICES.txt"
gh release upload engine -R "$REPO" "$OUT/THIRD-PARTY-NOTICES.txt" --clobber

# Hand this platform's hash to the index job.
[ -n "${GITHUB_OUTPUT:-}" ] && {
  echo "platform=$plat" >> "$GITHUB_OUTPUT"
  echo "rev=$rev" >> "$GITHUB_OUTPUT"
  echo "manifest_hash=$manifest_hash" >> "$GITHUB_OUTPUT"
}
echo "published engine $plat rev=$rev hash=$manifest_hash"
