"""Trim a built engine site-packages for distribution.

Three passes, in order:
  1. prune_dev    - drop dev/REPL/unused tooling that the engine never imports.
  2. strip_caches - drop __pycache__ and in-package test trees.
  3. subset_vtk   - keep only the vtkmodules extension modules the offscreen
                    renderer actually loads at runtime, plus the transitive
                    native-library closure those extensions link against.

The VTK subset is computed empirically: we run the engine's `views.capture_smoke`
in the target interpreter and record which `vtkmodules.*` extension modules end
up loaded. That set (not a hand-curated guess) seeds a native-library dependency
closure (otool on macOS, ldd/patchelf on Linux). Everything outside the closure
is removed. The whole thing is gated by the build smoke test that re-runs
`capture_smoke` after pruning - if a view can no longer be captured, the build
fails rather than shipping a broken renderer.

Usage:
    python prune_engine.py <site-packages> <target-python>
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import struct
import subprocess
import sys
from pathlib import Path

# PEP 552 .pyc header bit field (the 4 bytes after the 4-byte magic).
#   bit 0 (0x1): hash-based invalidation (clear -> timestamp-based)
#   bit 1 (0x2): check_source -> the runtime re-hashes the source and may
#                regenerate the .pyc (only meaningful when hash-based)
# The engine ships inside an integrity-verified, incrementally-updated tree, so
# its bytecode must be IMMUTABLE at runtime: only unchecked-hash .pyc
# (flags == 0x1) are never rewritten by the interpreter. A timestamp .pyc
# (flags == 0x0) is regenerated whenever a source mtime drifts -- which happens
# when an incremental update copies an unchanged base file -- and the rewritten
# bytes then fail the signed manifest ("hash mismatch for Lib/__pycache__/*.pyc").
PYC_HASH_BASED = 0x1
PYC_CHECK_SOURCE = 0x2

# Packages the engine never imports at runtime, confirmed by exercising the full
# engine import chain (server + mcp + build123d + a view capture + a sweep of
# every solidifai_engine submodule) and recording sys.modules.
#
# IPython is load-bearing: build123d hard-imports IPython.lib.pretty, which pulls
# IPython.terminal.embed -> prompt_toolkit. So prompt_toolkit, pygments, IPython,
# and matplotlib_inline (an IPython dep) MUST ship. But jedi+parso are only the
# tab-completion engine, imported by IPython.core.completer behind a
# try/except ImportError - dropping them (~35 MB) leaves the engine fully
# functional (verified: both entrypoints, OCP/lib3mf/build123d, VTK capture, and
# all engine submodules import clean without them).
DEV_DENYLIST = (
    "matplotlib", "mpl_toolkits", "pytest", "_pytest", "pluggy",
    "jedi", "parso",
)

# Build/install tooling never used at runtime (the venv is frozen at ship time).
BUILD_TOOLING = ("pip", "setuptools", "pkg_resources", "_distutils_hack", "wheel")

# CPython stdlib subtrees a headless offscreen engine never touches.
STDLIB_TRIM = ("test", "idlelib", "tkinter", "turtledemo", "lib2to3", "ensurepip")


def _rm(p: Path) -> None:
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p, ignore_errors=True)
    else:
        p.unlink(missing_ok=True)


def _remove_top_level(site_packages: Path, names) -> list[str]:
    """Remove top-level packages by exact name. Returns the names removed.

    Matches the package dir, a single-file module, and the distribution's
    metadata only - NOT a broad ``{name}*`` prefix, so e.g. dropping
    ``matplotlib`` never catches ``matplotlib_inline`` (an IPython dependency).
    """
    removed: list[str] = []
    for name in names:
        targets = [site_packages / name, site_packages / f"{name}.py"]
        targets += list(site_packages.glob(f"{name}-*.dist-info"))
        targets += list(site_packages.glob(f"{name}-*.egg-info"))
        for target in targets:
            if target.exists() and target.parent == site_packages:
                _rm(target)
                removed.append(target.name)
    return removed


def prune_dev(site_packages: Path) -> list[str]:
    """Remove dev/unused top-level packages (matplotlib, pytest, jedi/parso)."""
    return _remove_top_level(site_packages, DEV_DENYLIST)


def prune_build_tooling(site_packages: Path) -> list[str]:
    """Remove pip/setuptools/etc - the frozen venv never installs at runtime."""
    return _remove_top_level(site_packages, BUILD_TOOLING)


def trim_stdlib(stdlib_dir: Path) -> list[str]:
    """Drop CPython stdlib subtrees a headless engine never uses."""
    removed: list[str] = []
    for name in STDLIB_TRIM:
        target = stdlib_dir / name
        if target.exists():
            _rm(target)
            removed.append(name)
    return removed


def strip_natives(dist_root: Path) -> dict:
    """Strip local/debug symbols from native libs (e.g. VTK ships unstripped).

    macOS REQUIRES an ad-hoc re-sign afterward: stripping invalidates the code
    signature and the Apple Silicon loader then refuses to load the dylib.
    Windows is skipped (PE/.pyd stripping is uncommon and risky). Linux is
    skipped too: auditwheel-vendored libs (hash-renamed, patchelf-processed)
    do not survive strip; the loader then rejects them ("ELF load command
    address/offset not page-aligned")."""
    system = platform.system()
    if system == "Windows":
        return {"skipped": "windows"}
    if system == "Linux":
        return {"skipped": "linux (strip corrupts auditwheel-patched libs)"}
    exts = {".dylib", ".so"}
    libs = [p for p in dist_root.rglob("*")
            if p.suffix in exts and p.is_file() and not p.is_symlink()]
    stripped = 0
    saved = 0
    for lib in libs:
        before = lib.stat().st_size
        if subprocess.run(["strip", "-x", str(lib)], capture_output=True).returncode != 0:
            continue
        # Re-sign ad-hoc; fatal on arm64 without this.
        subprocess.run(["codesign", "-f", "-s", "-", str(lib)], capture_output=True)
        stripped += 1
        saved += before - lib.stat().st_size
    return {"stripped": stripped, "bytes_saved": saved}


def strip_caches(site_packages: Path) -> None:
    """Drop __pycache__ everywhere and test trees inside installed packages."""
    for p in site_packages.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    for p in list(site_packages.rglob("tests")):
        # only inside a package (has a sibling __init__.py), never a top-level dir
        if p.is_dir() and p.parent != site_packages and (p.parent / "__init__.py").exists():
            shutil.rmtree(p, ignore_errors=True)


def recompile_bytecode(root: Path, target_python: Path) -> None:
    """Replace every .pyc under ``root`` with immutable, unchecked-hash bytecode.

    python-build-standalone ships the stdlib pre-compiled with timestamp-based
    .pyc. Those are regenerated by the running interpreter as soon as a source
    mtime drifts (an incremental update copies unchanged base files, which resets
    their mtime), and the rewritten bytes then no longer match the signed engine
    manifest. We wipe all __pycache__ and recompile the whole tree with PEP 552
    ``unchecked-hash`` invalidation, so the interpreter loads the shipped .pyc
    unconditionally and never rewrites them -- keeping the tree byte-stable across
    updates while preserving warm-start speed (bytecode still ships).

    Uses ``target_python`` (the bundled interpreter) so the .pyc magic number
    matches the interpreter that will load them.
    """
    for pc in root.rglob("__pycache__"):
        shutil.rmtree(pc, ignore_errors=True)
    # -j0 = all cores; -f = force; -q = quiet. Not checked for a zero exit: the
    # stdlib carries a few intentionally-unparseable fixtures, and a file we fail
    # to compile simply ships without a .pyc (compiled at runtime, never
    # manifested) rather than shipping a drift-prone one. assert_stable_bytecode
    # is the real gate.
    subprocess.run(
        [str(target_python), "-m", "compileall", "-q", "-f", "-j", "0",
         "--invalidation-mode", "unchecked-hash", str(root)],
        capture_output=True,
    )


def assert_stable_bytecode(root: Path) -> None:
    """Fail the build if any shipped .pyc under ``root`` is not unchecked-hash.

    Fail-closed guard: a timestamp .pyc (or a checked-hash one) would be rewritten
    at runtime and break the signed manifest on the next incremental update. If
    anything -- a dependency shipping its own .pyc, a compileall miss -- leaves a
    non-immutable .pyc in the tree, the build stops here rather than publishing a
    signed-but-unstable engine.
    """
    offenders: list[str] = []
    for pyc in root.rglob("*.pyc"):
        header = pyc.read_bytes()[:8]
        if len(header) < 8:
            offenders.append(f"  {pyc.relative_to(root)}: truncated/invalid .pyc header")
            continue
        flags = struct.unpack("<I", header[4:8])[0]
        if not (flags & PYC_HASH_BASED):
            offenders.append(f"  {pyc.relative_to(root)}: timestamp-based (flags={flags:#x})")
        elif flags & PYC_CHECK_SOURCE:
            offenders.append(f"  {pyc.relative_to(root)}: checked-hash (flags={flags:#x})")
    if offenders:
        raise RuntimeError(
            "non-immutable bytecode would ship in the engine tree; the runtime can "
            "regenerate these and break the signed manifest on incremental update:\n"
            + "\n".join(offenders)
        )


def native_closure(seeds: set[str], deps: dict[str, set[str]]) -> set[str]:
    """Transitive closure of `seeds` over a dependency graph.

    `deps` maps a library basename to the set of basenames it directly depends
    on. Pure function (no I/O) so the closure logic is unit-testable.
    """
    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(deps.get(cur, ()))
    return seen


# --- platform-specific native dependency extraction --------------------------

def _deps_macos(lib: Path) -> set[str]:
    out = subprocess.run(["otool", "-L", str(lib)], capture_output=True, text=True)
    names = set()
    for line in out.stdout.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        path = line.split(" (")[0]
        names.add(Path(path).name)
    return names


def _deps_linux(lib: Path) -> set[str]:
    # patchelf is available on the Tauri Linux runner; fall back to ldd.
    try:
        out = subprocess.run(["patchelf", "--print-needed", str(lib)],
                             capture_output=True, text=True, check=True)
        return {ln.strip() for ln in out.stdout.splitlines() if ln.strip()}
    except Exception:
        out = subprocess.run(["ldd", str(lib)], capture_output=True, text=True)
        names = set()
        for line in out.stdout.splitlines():
            parts = line.split("=>")
            head = parts[0].strip()
            if head:
                names.add(Path(head.split(" ")[0]).name)
        return names


def _libs_dir(site_packages: Path) -> Path | None:
    """Where VTK's bundled shared libs live - and only when pruning them is SAFE.

    macOS (delocate) names libs in ``vtkmodules/.dylibs`` exactly as they appear
    in the extensions' install names, so the otool-based closure is exact (and is
    the tested path).

    Linux is exact for the same reason: the wheel build (auditwheel/its
    equivalent) writes the vendored libs' FINAL basenames into the extensions'
    DT_NEEDED entries when it vendors them, and ``patchelf --print-needed``
    reports those strings verbatim - the loader resolves exactly what we match.
    Symlink chains (``libfoo.so.1`` -> ``libfoo.so.1.2.3``) are expanded after
    the closure so a kept link never loses its target. Only a directory that is
    unambiguously VTK's own vendored-lib dir is pruned; anything unexpected
    returns None, which keeps the ship-everything behavior.

    Windows ships DLLs whose PE import tables need a third-party parser, so
    Windows still ships the full lib set. Everywhere, a wrong subset fails the
    build smoke (re-runs capture_smoke + imports OCP/lib3mf/build123d), so this
    can break a release build but never a user.
    """
    system = platform.system()
    if system == "Darwin":
        dylibs = site_packages / "vtkmodules" / ".dylibs"
        return dylibs if dylibs.is_dir() else None
    if system == "Linux":
        candidates = [
            d
            for d in [site_packages / "vtkmodules" / ".libs",
                      *sorted(site_packages.glob("*vtk*.libs"))]
            if d.is_dir()
            and sum(1 for f in d.iterdir() if f.name.startswith("libvtk")) >= 5
        ]
        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            print(f"subset_vtk: ambiguous vtk lib dirs {candidates}, skipping libs")
        return None
    return None


def _expand_link_targets(kept: set[str], present: dict[str, Path]) -> set[str]:
    """Add the resolved targets of kept symlinks (SONAME chains) to the keep set.

    ``libvtkX.so.1`` is often a symlink to ``libvtkX.so.1.2.3``; keeping the
    link while deleting its target would ship a dangling symlink. Follows
    chains; targets outside `present` are ignored (nothing of ours to keep).
    """
    out = set(kept)
    stack = [name for name in kept if name in present]
    while stack:
        p = present.get(stack.pop())
        if p is None or not p.is_symlink():
            continue
        target = Path(os.readlink(p)).name
        if target in present and target not in out:
            out.add(target)
            stack.append(target)
    return out


def _loaded_vtk_extensions(target_python: Path) -> set[str]:
    """Run capture_smoke in the target interpreter; return the vtkmodules
    extension-module basenames that got loaded (the true runtime closure)."""
    probe = (
        "import tempfile, sys, json;"
        "from solidifai_engine import views;"
        "views.capture_smoke(tempfile.mkdtemp());"
        "mods=[m.rsplit('.',1)[1] for m in sys.modules "
        "if m.startswith('vtkmodules.') and m.count('.')==1];"
        "print('VTK_LOADED='+json.dumps(sorted(set(mods))))"
    )
    out = subprocess.run([str(target_python), "-c", probe],
                         capture_output=True, text=True)
    for line in out.stdout.splitlines():
        if line.startswith("VTK_LOADED="):
            return set(json.loads(line[len("VTK_LOADED="):]))
    raise RuntimeError(
        f"vtk probe failed (exit {out.returncode}); a headless builder needs a "
        f"software GL (xvfb / Mesa opengl32):\n{out.stdout}{out.stderr}"
    )


def _ext_suffixes() -> tuple[str, ...]:
    if platform.system() == "Windows":
        return (".pyd",)
    return (".so",)


def subset_vtk(site_packages: Path, target_python: Path) -> dict:
    """Keep only the loaded vtkmodules extensions + their native closure."""
    vm = site_packages / "vtkmodules"
    if not vm.is_dir():
        return {"skipped": "no vtkmodules"}

    keep_ext = _loaded_vtk_extensions(target_python)
    if not keep_ext:
        return {"skipped": "no extensions reported"}

    suffixes = _ext_suffixes()

    # Map every vtkmodules extension file -> its module stem (e.g.
    # "vtkRenderingCore.cpython-312-darwin.so" -> "vtkRenderingCore").
    def stem_of(p: Path) -> str:
        return p.name.split(".")[0]

    ext_files = [p for p in vm.iterdir()
                 if p.suffix in suffixes and stem_of(p).startswith("vtk")]
    keep_files = {p for p in ext_files if stem_of(p) in keep_ext}

    libs_dir = _libs_dir(site_packages)
    kept_libs: set[str] = set()
    if libs_dir:
        deps_fn = _deps_macos if platform.system() == "Darwin" else _deps_linux
        present_libs = {p.name: p for p in libs_dir.iterdir() if p.is_file()}

        # Seed the closure from EVERYTHING that links into the VTK lib dir, not
        # just the renderer's vtk extensions. OCP (OpenCASCADE) and lib3mf also
        # hard-link VTK dylibs, so we must scan every native module in
        # site-packages or we would delete libs OCP needs to import.
        native_suffixes = (".so", ".dylib", ".pyd")
        seed_sources = list(keep_files)
        for p in site_packages.rglob("*"):
            if (p.suffix in native_suffixes and p.is_file()
                    and vm not in p.parents):  # vtkmodules handled via keep_files
                seed_sources.append(p)

        seeds: set[str] = set()
        for src in seed_sources:
            for dep in deps_fn(src):
                if dep in present_libs:
                    seeds.add(dep)

        # graph edges between bundled libs (so the closure follows lib->lib deps)
        graph: dict[str, set[str]] = {
            name: {d for d in deps_fn(p) if d in present_libs}
            for name, p in present_libs.items()
        }
        kept_libs = _expand_link_targets(native_closure(seeds, graph), present_libs)

    # --- delete what is not kept ---
    removed_ext = removed_libs = 0
    for p in ext_files:
        if p not in keep_files:
            # drop the extension .so/.pyd and its thin .py wrapper
            _rm(p)
            wrapper = vm / f"{stem_of(p)}.py"
            if wrapper.exists():
                _rm(wrapper)
            removed_ext += 1
    if libs_dir:
        for name, p in present_libs.items():
            if name not in kept_libs:
                _rm(p)
                removed_libs += 1

    return {
        "kept_extensions": sorted(keep_ext),
        "removed_extensions": removed_ext,
        "kept_libs": len(kept_libs),
        "removed_libs": removed_libs,
        "native_closure_done": bool(libs_dir),
    }


def main() -> int:
    site_packages = Path(sys.argv[1])
    target_python = Path(sys.argv[2])
    # site-packages is <dist>/lib/pythonX.Y/site-packages
    stdlib_dir = site_packages.parent
    dist_root = site_packages.parents[2]

    removed = prune_dev(site_packages)
    print(f"prune_dev removed: {removed}")
    tooling = prune_build_tooling(site_packages)
    print(f"prune_build_tooling removed: {tooling}")
    std = trim_stdlib(stdlib_dir)
    print(f"trim_stdlib removed: {std}")
    strip_caches(site_packages)
    print("strip_caches done")
    report = subset_vtk(site_packages, target_python)
    print("subset_vtk:", json.dumps(report, indent=2))
    # Strip native symbols LAST, after VTK subsetting has deleted unused libs.
    strip = strip_natives(dist_root)
    print("strip_natives:", json.dumps(strip))
    # Bytecode step LAST: recompile the final pruned tree (stdlib + site-packages,
    # both under stdlib_dir) to immutable unchecked-hash .pyc, then fail closed if
    # any non-immutable .pyc survived. Must follow every deletion so we never
    # compile a file we then remove.
    recompile_bytecode(stdlib_dir, target_python)
    assert_stable_bytecode(stdlib_dir)
    print("recompile_bytecode: all .pyc are unchecked-hash (immutable)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
