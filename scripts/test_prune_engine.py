"""Unit tests for the pure logic in prune_engine (dev prune, cache strip, closure).

The VTK native subset is validated end-to-end by the build smoke test, not here.
"""
import struct
import sys
from pathlib import Path

import prune_engine

# PEP 552 .pyc header: 4-byte magic, then a 4-byte little-endian bit field.
#   bit 0 (0x1) set  -> hash-based invalidation (vs timestamp-based when clear)
#   bit 1 (0x2) set  -> "check_source" (Python re-hashes the source and may
#                       regenerate the .pyc); clear -> "unchecked", never checked
# A shipped, integrity-verified engine tree must contain ONLY unchecked-hash
# .pyc (flags == 0x1): those are the only ones the running interpreter never
# rewrites, so their bytes stay identical to the signed manifest across
# incremental updates. A timestamp .pyc (flags == 0x0) gets regenerated when the
# source mtime drifts (e.g. a base file copied during an incremental assemble),
# which is exactly the "hash mismatch for Lib/__pycache__/*.pyc" install failure.
PYC_HASH_BASED = 0x1
PYC_CHECK_SOURCE = 0x2


def _pyc_flags(pyc: Path) -> int:
    return struct.unpack("<I", pyc.read_bytes()[4:8])[0]


def _all_pyc(root: Path) -> list[Path]:
    return list(root.rglob("*.pyc"))


def _touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x")


def test_prune_dev_removes_dev_keeps_runtime(tmp_path):
    sp = tmp_path / "site-packages"
    for pkg in ["matplotlib", "mpl_toolkits", "pytest", "_pytest", "pluggy",
                "matplotlib_inline", "IPython", "jedi", "parso", "prompt_toolkit",
                "build123d", "numpy"]:
        _touch(sp / pkg / "__init__.py")
    _touch(sp / "matplotlib-3.9.dist-info" / "RECORD")
    _touch(sp / "pytest-8.0.dist-info" / "RECORD")
    removed = prune_engine.prune_dev(sp)
    # dev/unused removed
    assert not (sp / "matplotlib").exists()
    assert not (sp / "matplotlib-3.9.dist-info").exists()
    assert not (sp / "pytest").exists()
    assert not (sp / "pytest-8.0.dist-info").exists()
    assert not (sp / "_pytest").exists()
    assert not (sp / "pluggy").exists()
    # jedi+parso are only the tab-completion engine; now removed
    assert not (sp / "jedi").exists()
    assert not (sp / "parso").exists()
    # runtime deps the engine needs are kept (IPython.lib.pretty -> prompt_toolkit)
    assert (sp / "IPython").exists()
    assert (sp / "prompt_toolkit").exists()
    assert (sp / "build123d").exists()
    assert (sp / "numpy").exists()
    # precision: matplotlib_inline (an IPython dep) must NOT be caught by "matplotlib"
    assert (sp / "matplotlib_inline").exists()
    assert "matplotlib" in removed


def test_prune_build_tooling_removes_pip_setuptools(tmp_path):
    sp = tmp_path / "site-packages"
    for pkg in ["pip", "setuptools", "pkg_resources", "_distutils_hack", "numpy"]:
        _touch(sp / pkg / "__init__.py")
    _touch(sp / "pip-24.3.1.dist-info" / "RECORD")
    removed = prune_engine.prune_build_tooling(sp)
    assert not (sp / "pip").exists()
    assert not (sp / "pip-24.3.1.dist-info").exists()
    assert not (sp / "setuptools").exists()
    assert not (sp / "pkg_resources").exists()
    assert (sp / "numpy").exists()  # never touch real deps
    assert "pip" in removed


def test_trim_stdlib_removes_only_listed(tmp_path):
    for d in ("test", "idlelib", "tkinter", "asyncio", "json"):
        (tmp_path / d).mkdir(parents=True)
    removed = prune_engine.trim_stdlib(tmp_path)
    assert not (tmp_path / "test").exists()
    assert not (tmp_path / "idlelib").exists()
    assert not (tmp_path / "tkinter").exists()
    assert (tmp_path / "asyncio").exists(), "must not touch needed stdlib"
    assert (tmp_path / "json").exists()
    assert set(removed) >= {"test", "idlelib", "tkinter"}


def test_strip_caches_drops_pycache_and_package_tests(tmp_path):
    sp = tmp_path / "site-packages"
    _touch(sp / "pkg" / "__init__.py")
    _touch(sp / "pkg" / "__pycache__" / "x.pyc")
    _touch(sp / "pkg" / "tests" / "test_x.py")
    _touch(sp / "tests" / "keep_me.py")  # top-level, not inside a package
    prune_engine.strip_caches(sp)
    assert not (sp / "pkg" / "__pycache__").exists()
    assert not (sp / "pkg" / "tests").exists()
    assert (sp / "tests").exists()  # top-level tests dir untouched


def test_recompile_bytecode_ships_only_unchecked_hash(tmp_path):
    # Regression: stdlib .pyc shipped as timestamp-based bytecode, which the
    # running engine rewrites when a source mtime drifts, breaking the signed
    # manifest on the next incremental update ("hash mismatch for
    # Lib/__pycache__/tarfile.cpython-312.pyc"). After recompile, EVERY shipped
    # .pyc must be unchecked-hash so the interpreter never regenerates it.
    root = tmp_path / "Lib"
    _touch(root / "amod.py")
    _touch(root / "pkg" / "__init__.py")
    _touch(root / "pkg" / "sub.py")
    # a pre-existing timestamp-mode .pyc (what python-build-standalone ships) that
    # the recompile must replace, not leave behind
    stale = root / "__pycache__" / "amod.cpython-stale.pyc"
    _touch(stale)

    prune_engine.recompile_bytecode(root, Path(sys.executable))

    pyc = _all_pyc(root)
    assert pyc, "recompile must produce .pyc for the tree"
    assert not stale.exists(), "stale timestamp .pyc must be cleared, not kept"
    for p in pyc:
        flags = _pyc_flags(p)
        assert flags & prune_engine.PYC_HASH_BASED, f"{p} is not hash-based (flags={flags:#x})"
        assert not (flags & prune_engine.PYC_CHECK_SOURCE), (
            f"{p} is checked-hash; it must be unchecked so the runtime never "
            f"regenerates it (flags={flags:#x})"
        )


def test_assert_stable_bytecode_rejects_timestamp_pyc(tmp_path):
    # The build-time fail-closed guard: if ANYTHING leaves a timestamp .pyc in the
    # tree (a dependency that shipped one, a compileall miss), the build must fail
    # loudly rather than publish a drift-prone, signed-but-unstable engine.
    root = tmp_path / "Lib"
    _touch(root / "mod.py")
    prune_engine.recompile_bytecode(root, Path(sys.executable))
    prune_engine.assert_stable_bytecode(root)  # clean tree: no raise

    # Inject a timestamp-mode .pyc (flags = 0x0) and expect a hard failure.
    bad = root / "__pycache__" / "injected.cpython-tmp.pyc"
    bad.parent.mkdir(parents=True, exist_ok=True)
    good = _all_pyc(root)[0].read_bytes()
    bad.write_bytes(good[:4] + struct.pack("<I", 0) + good[8:])
    try:
        prune_engine.assert_stable_bytecode(root)
        raise AssertionError("expected assert_stable_bytecode to reject a timestamp .pyc")
    except RuntimeError as e:
        assert "injected" in str(e) and "timestamp" in str(e).lower()


def test_native_closure_is_transitive():
    deps = {
        "a.so": {"b.dylib", "c.dylib"},
        "b.dylib": {"d.dylib"},
        "c.dylib": set(),
        "d.dylib": set(),
        "unused.dylib": {"a.so"},
    }
    got = prune_engine.native_closure({"a.so"}, deps)
    assert got == {"a.so", "b.dylib", "c.dylib", "d.dylib"}
    assert "unused.dylib" not in got


def test_native_closure_handles_cycles():
    deps = {"x": {"y"}, "y": {"x"}}
    assert prune_engine.native_closure({"x"}, deps) == {"x", "y"}


def test_libs_dir_linux_requires_unambiguous_vtk_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(prune_engine.platform, "system", lambda: "Linux")
    sp = tmp_path / "site-packages"

    # nothing present -> skip
    sp.mkdir(parents=True)
    assert prune_engine._libs_dir(sp) is None

    # a real vtk vendored dir -> found
    libs = sp / "vtkmodules" / ".libs"
    for i in range(6):
        _touch(libs / f"libvtkCommonCore-{i}.so.1")
    assert prune_engine._libs_dir(sp) == libs

    # too few libvtk files -> not confidently vtk's dir -> skip
    thin = tmp_path / "thin" / "site-packages"
    _touch(thin / "vtkmodules" / ".libs" / "libvtkOne.so")
    assert prune_engine._libs_dir(thin) is None

    # two plausible dirs -> ambiguous -> skip (ship everything)
    for i in range(6):
        _touch(sp / "vtk.libs" / f"libvtkRendering-{i}.so.1")
    assert prune_engine._libs_dir(sp) is None


def test_libs_dir_windows_always_skips(tmp_path, monkeypatch):
    monkeypatch.setattr(prune_engine.platform, "system", lambda: "Windows")
    libs = tmp_path / "vtkmodules" / ".libs"
    for i in range(6):
        _touch(libs / f"libvtk-{i}.dll")
    assert prune_engine._libs_dir(tmp_path) is None


def test_expand_link_targets_keeps_soname_chains(tmp_path):
    real = tmp_path / "libvtkX.so.1.2.3"
    real.write_text("elf")
    (tmp_path / "libvtkX.so.1").symlink_to(real.name)
    (tmp_path / "libvtkX.so").symlink_to("libvtkX.so.1")
    unrelated = tmp_path / "libvtkY.so.1"
    unrelated.write_text("elf")
    present = {p.name: p for p in tmp_path.iterdir()}

    kept = prune_engine._expand_link_targets({"libvtkX.so"}, present)
    assert kept == {"libvtkX.so", "libvtkX.so.1", "libvtkX.so.1.2.3"}
    assert "libvtkY.so.1" not in kept


def test_strip_natives_skips_linux_and_windows(tmp_path, monkeypatch):
    # auditwheel-patched libs are corrupted by strip; PE stripping is risky.
    for system in ("Linux", "Windows"):
        monkeypatch.setattr(prune_engine.platform, "system", lambda s=system: s)
        result = prune_engine.strip_natives(tmp_path)
        assert "skipped" in result, f"{system} must not be stripped"
