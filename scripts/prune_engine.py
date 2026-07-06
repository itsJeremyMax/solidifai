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
import platform
import shutil
import subprocess
import sys
from pathlib import Path

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
        return {l.strip() for l in out.stdout.splitlines() if l.strip()}
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
    the tested path). Linux auditwheel renames libs with a content hash
    (``libvtkCommonCore-<hash>.so.1``) while ``ldd``/``patchelf`` report the
    unmangled SONAME, so a basename match would wrongly delete a needed lib;
    Windows ships DLLs alongside the extensions. Until that mapping is validated
    on those runners we do NOT prune native libs there - those platforms still
    drop unused vtk *extension modules* + dev deps, only the shared libs stay.
    See docs/RELEASING.md (VTK subsetting is macOS-only for now).
    """
    if platform.system() != "Darwin":
        return None
    dylibs = site_packages / "vtkmodules" / ".dylibs"
    return dylibs if dylibs.is_dir() else None


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
        kept_libs = native_closure(seeds, graph)

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
