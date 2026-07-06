"""Unit tests for the pure logic in prune_engine (dev prune, cache strip, closure).

The VTK native subset is validated end-to-end by the build smoke test, not here.
"""
from pathlib import Path

import prune_engine


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


def test_strip_natives_skips_linux_and_windows(tmp_path, monkeypatch):
    # auditwheel-patched libs are corrupted by strip; PE stripping is risky.
    for system in ("Linux", "Windows"):
        monkeypatch.setattr(prune_engine.platform, "system", lambda s=system: s)
        result = prune_engine.strip_natives(tmp_path)
        assert "skipped" in result, f"{system} must not be stripped"
