#!/usr/bin/env bash
# Build a self-contained, trimmed engine into src-tauri/engine-dist.
#
# Ships a relocatable standalone CPython (python-build-standalone, via uv) with
# the engine's production dependencies installed, then prunes dev tooling and
# subsets VTK to the native closure the offscreen renderer actually needs.
# The result runs `python -m solidifai_engine` AND `python -m solidifai_mcp`
# (the latter is launched by external agent tools), so we ship a real
# interpreter rather than a frozen single-file binary.
#
# Usage: scripts/build-engine-dist.sh [python-version]
set -euo pipefail
PYVER="${1:-3.12}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/src-tauri/engine-dist"

# Platform label for engine assets; must match the Rust runtime's current_platform().
engine_platform() {
  local os arch
  case "$(uname -s)" in Darwin) os=darwin;; Linux) os=linux;; *) os=unknown;; esac
  case "$(uname -m)" in arm64|aarch64) arch=aarch64;; x86_64|amd64) arch=x86_64;; *) arch="$(uname -m)";; esac
  echo "$os-$arch"
}

echo "==> Cleaning previous bundle"
rm -rf "$DIST"

echo "==> Installing standalone CPython $PYVER via uv"
uv python install "$PYVER"
PYBIN="$(UV_PYTHON_PREFERENCE=only-managed uv python find "$PYVER")"
# pwd -P: newer uv answers `python find` with a minor-version alias directory
# (cpython-3.12-... -> cpython-3.12.13-...). Copying that symlink instead of the
# real tree makes engine-dist an alias into uv's managed install, which is
# externally managed (PEP 668) and must not be modified.
PYHOME="$(cd "$(dirname "$PYBIN")/.." && pwd -P)"
echo "    managed interpreter: $PYHOME"

echo "==> Copying interpreter into engine-dist"
cp -R "$PYHOME" "$DIST"
[ -d "$DIST" ] && [ ! -L "$DIST" ] || { echo "ERROR: engine-dist is not a real directory (symlinked interpreter copied?)"; exit 1; }
DIST_PY="$DIST/bin/python3"
[ -x "$DIST_PY" ] || { echo "ERROR: $DIST_PY missing after copy"; ls -la "$DIST/bin" || true; exit 1; }

# This is now our private copy, not uv's managed interpreter: drop the PEP 668
# marker so we can install the engine into it.
find "$DIST" -name EXTERNALLY-MANAGED -delete

echo "==> Installing the engine (locked production deps) into the bundle"
# Install the LOCKED closure from engine/uv.lock, not a fresh resolution: the
# bundle must ship exactly the dependency set CI tests against. A fresh resolve
# once silently dropped vtk when cadquery-ocp's metadata changed upstream.
REQ="$(mktemp)"
uv export --project "$ROOT/engine" --frozen --no-dev --no-emit-project -o "$REQ"
uv pip install --python "$DIST_PY" -r "$REQ"
uv pip install --python "$DIST_PY" --no-deps "$ROOT/engine"
rm -f "$REQ"

echo "==> Pruning dev deps + subsetting VTK (native closure)"
SP="$(echo "$DIST"/lib/python*/site-packages)"
"$DIST_PY" "$ROOT/scripts/prune_engine.py" "$SP" "$DIST_PY"

# The bundle ships LGPL and attribution-required native libraries (OCCT,
# FreeImage, FreeType, libjpeg, ...); their license texts must accompany
# every binary distribution, so the notices ride in the bundle root.
echo "==> Copying third-party license notices into the bundle"
cp "$ROOT/scripts/ENGINE-THIRD-PARTY-NOTICES.txt" "$DIST/THIRD-PARTY-NOTICES.txt"

echo "==> Smoke test (both entrypoints + a build123d op + a VTK view capture)"
"$DIST_PY" -m solidifai_engine --help >/dev/null
"$DIST_PY" -c "from solidifai_mcp.server import main; print('mcp entrypoint OK')"
"$DIST_PY" - <<'PY'
import tempfile, pathlib
import OCP          # OpenCASCADE bindings (links several VTK dylibs)
import lib3mf       # 3MF native lib
import build123d as bd
from solidifai_engine import views, exports, dfm  # full engine import graph
assert bd.Box(1, 1, 1).volume > 0.0, "build123d/OCP broken"
out = views.capture_smoke(tempfile.mkdtemp())
assert out and all(pathlib.Path(p).exists() for p in out), "VTK view capture broken"
print("engine smoke OK")
PY

# --- Content-addressed engine assets (manifest + full archive) + app pin --------
# The manifest and full archive are published to the permanent `engine` GitHub
# release by release-build.yml, which also emits the incremental pack vs the
# previous rev, signs the manifest, and uploads. Here we produce the locally
# reproducible parts and stamp the pin the shipped app resolves against.
echo "==> Emitting engine assets + stamping pin"
PLAT="$(engine_platform)"
OUT="${ENGINE_OUT_DIR:-$ROOT/engine-out}"
mkdir -p "$OUT"
# engineRev: hash of resolved deps + first-party source. Per-platform in practice
# (sh and ps1 hash slightly differently); the app embeds + resolves its own rev.
# `uv pip freeze` rather than `python -m pip`: the prune step strips pip from the
# bundle, which made the dep half of the rev silently hash an empty string.
DEPS="$(uv pip freeze --python "$DIST_PY")"
[ -n "$DEPS" ] || { echo "ERROR: dependency freeze is empty; engineRev would ignore deps"; exit 1; }
DEPREV="$(printf '%s\n' "$DEPS" | sort | shasum -a 256 | cut -c1-12)"
SRCREV="$(find "$ROOT/engine" -name '*.py' -not -path '*/.venv/*' -print0 | sort -z | xargs -0 shasum -a 256 2>/dev/null | shasum -a 256 | cut -c1-12)"
ENGINE_REV="${DEPREV}${SRCREV}"
EP="$ROOT/src-tauri/target/release/engine-pack"
[ -x "$EP" ] || cargo build --release --manifest-path "$ROOT/src-tauri/Cargo.toml" -p engine-pack
MAN="$OUT/solidifai-engine-$PLAT-$ENGINE_REV.manifest.json"
MANIFEST_HASH="$("$EP" manifest "$DIST" "$ENGINE_REV" "$PLAT" "$MAN")"
"$EP" full "$DIST" "$MAN" "$OUT/solidifai-engine-$PLAT-$ENGINE_REV.full.tar.zst"
for f in "$OUT"/solidifai-engine-"$PLAT"-*; do
  case "$f" in *.sha256) continue;; esac  # don't hash sidecars on a re-run
  shasum -a 256 "$f" | awk '{print $1}' > "$f.sha256"
done
printf '{ "engineRev": "%s", "manifestHash": "%s" }\n' "$ENGINE_REV" "$MANIFEST_HASH" \
  > "$ROOT/src-tauri/engine-pin.json"
echo "    engineRev=$ENGINE_REV manifestHash=$MANIFEST_HASH plat=$PLAT"

echo "==> Bundle size:"
du -sh "$DIST"
echo "==> Engine assets in $OUT:"
ls -lh "$OUT"
echo "==> engine-dist built at $DIST"
