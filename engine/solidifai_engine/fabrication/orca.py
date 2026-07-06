"""OrcaProvider — detect, profile discovery, headless slice quote, app handoff.

Shell-out is isolated behind ``_run_orca`` so tests inject a fake runner.
Detection uses injectable ``candidates`` so tests use fixture paths; real
default candidates cover macOS / Windows / Linux without needing Orca installed.

Profile discovery delegates to ``presets.list_profiles``; see that module for the
real config dir layout (system/<vendor>/<category>/ + user/<account>/<category>/).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from solidifai_engine import slicers
from solidifai_engine.fabrication import presets, slicedata
from solidifai_engine.fabrication.base import (
    Capabilities,
    Destination,
    InstallInfo,
)

# ---------------------------------------------------------------------------
# Config dir helper (injectable via monkeypatch in tests)
# ---------------------------------------------------------------------------


def _orca_config_dir() -> str:
    """Return the platform-appropriate OrcaSlicer user config directory.

    Returns the path string regardless of whether it exists.
    """
    sys = platform.system()
    if sys == "Darwin":
        return str(Path.home() / "Library" / "Application Support" / "OrcaSlicer")
    if sys == "Windows":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return str(Path(appdata) / "OrcaSlicer")
    # Linux / other
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return str(Path(xdg) / "OrcaSlicer")


# ---------------------------------------------------------------------------
# Default candidate paths (per OS)
# ---------------------------------------------------------------------------


def _default_candidates() -> list[str]:
    """Return ordered list of candidate executable paths for the current OS."""
    sys = platform.system()
    if sys == "Darwin":
        return ["/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer"]
    if sys == "Windows":
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        return [
            str(Path(pf) / "OrcaSlicer" / "orca-slicer.exe"),
            str(Path(pf86) / "OrcaSlicer" / "orca-slicer.exe"),
            str(Path(pf) / "Bambu Studio" / "orca-slicer.exe"),
        ]
    # Linux: check PATH first, then well-known install locations. The fixed
    # paths matter because a desktop-entry launch gets the minimal session PATH
    # (no shell-rc additions like ~/.local/bin), so which() alone misses
    # installs that resolve fine from the user's own terminal.
    found = shutil.which("orca-slicer")
    candidates = [found] if found else []
    candidates += [
        str(Path.home() / ".local" / "bin" / "orca-slicer"),
        str(Path.home() / "OrcaSlicer.AppImage"),
        str(Path.home() / "Applications" / "OrcaSlicer.AppImage"),
        "/usr/bin/orca-slicer",
        "/usr/local/bin/orca-slicer",
        "/opt/OrcaSlicer/orca-slicer",
    ]
    return candidates


# ---------------------------------------------------------------------------
# OrcaProvider
# ---------------------------------------------------------------------------


class OrcaProvider:
    """Fabrication provider that wraps a locally installed OrcaSlicer.

    Shell-out for quote/detect goes through ``_run_orca`` (injectable ``runner``).
    App handoff uses a separate ``_launcher`` seam (injectable, defaults to
    ``subprocess.Popen``) so tests verify non-blocking launch without spawning a
    real process.
    """

    def __init__(
        self,
        candidates: list[str] | None = None,
        version_runner: Callable[[str], str] | None = None,
        runner: Callable[..., Any] | None = None,
        launcher: Callable[..., Any] | None = None,
        config_dir: str | None = None,
    ) -> None:
        # None → use OS defaults at detect() time (lazy, so tests work without real Orca)
        self._candidates = candidates
        self._version_runner = version_runner
        # Shell-out for detect/quote; tests inject a fake here
        self._runner = runner if runner is not None else subprocess.run
        # Non-blocking launcher for app handoff; tests inject a fake here
        self._launcher = launcher if launcher is not None else subprocess.Popen
        self._config_dir = config_dir  # None -> resolve OS default lazily
        self._cached_info: InstallInfo | None = None

    # ------------------------------------------------------------------
    # Shell-out boundary
    # ------------------------------------------------------------------

    def _run_orca(self, args: list[str], **kwargs: Any) -> Any:
        """Single point of subprocess execution — injectable for tests."""
        return self._runner(args, **kwargs)

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect(self) -> InstallInfo:
        """Probe candidate paths and return the first usable executable.

        Result is cached on the instance; repeated calls are free.
        """
        if self._cached_info is not None:
            return self._cached_info

        if self._candidates is not None:
            candidates = self._candidates
        else:
            # The host-configured override (Settings -> Slicers) wins over OS defaults.
            override = slicers.override_executable("orca")
            candidates = ([override] if override else []) + _default_candidates()

        for path in candidates:
            if not path:
                continue
            p = Path(path)
            if p.is_file() and os.access(path, os.X_OK):
                version = self._get_version(path)
                info = InstallInfo(found=True, version=version, executable=path)
                self._cached_info = info
                return info

        info = InstallInfo(found=False)
        self._cached_info = info
        return info

    def _get_version(self, executable: str) -> str | None:
        """Run the version probe; fall back to None if anything goes wrong."""
        if self._version_runner is not None:
            try:
                return self._version_runner(executable)
            except Exception:
                return None
        # Real probe: OrcaSlicer --version
        try:
            result = self._run_orca(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # Strip "OrcaSlicer" prefix if present; take first token of output
                return result.stdout.strip().split()[-1]
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Profile discovery
    # ------------------------------------------------------------------

    def _resolve_config_dir(self) -> str:
        return self._config_dir if self._config_dir is not None else _orca_config_dir()

    def profiles(self) -> dict[str, list[str]]:
        """Printer/filament/process preset names from the Orca config. Never raises."""
        try:
            return presets.list_profiles(self._resolve_config_dir())
        except Exception:  # defensive — discovery never raises
            return {"printers": [], "filaments": [], "processes": []}

    # ------------------------------------------------------------------
    # Slice quote
    # ------------------------------------------------------------------

    def quote(
        self,
        model_path: str,
        profile: dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Slice ``model_path`` with the selected presets; return a slice Estimate.

        Flattens each selected preset (machine/process/filament) into a temp config
        because bare user presets are rejected by the Orca CLI. Output goes to a temp
        .3mf parsed by slicedata. On failure returns {"ok": False, "reason": ...}.
        """
        info = self.detect()
        exe: str = info.executable if info.executable is not None else "orca-slicer"
        config_dir = self._resolve_config_dir()
        price_fallback = (options or {}).get("price_per_kg", 25.0)

        with tempfile.TemporaryDirectory(prefix="sf_orca_") as work:
            # Flatten whichever slots resolve; skip the rest.
            flats: dict[str, str] = {}
            for slot, category in (
                ("printer", "machine"),
                ("process", "process"),
                ("filament", "filament"),
            ):
                name = profile.get(slot)
                if not name:
                    continue
                dest = os.path.join(work, f"{category}.json")
                if presets.write_flattened(config_dir, name, category, dest):
                    flats[category] = dest

            out_3mf = os.path.join(work, "out.3mf")
            args = [exe, "--datadir", config_dir]

            # --load-settings: machine first, then process (Orca requires that order).
            settings = [flats[c] for c in ("machine", "process") if c in flats]
            if settings:
                args += ["--load-settings", ";".join(settings)]
            if "filament" in flats:
                args += ["--load-filaments", flats["filament"]]

            # Absolute --export-3mf; never combine with --outputdir (paths concatenate).
            args += ["--slice", "1", "--export-3mf", out_3mf, model_path]

            try:
                result = self._run_orca(args, capture_output=True, text=True, timeout=120)
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "reason": str(exc)}

            # Headless slicing logs GL thumbnail-shader errors to stderr but still
            # exports; key off exit status and the output file, not stderr content.
            if result.returncode != 0 or not os.path.isfile(out_3mf):
                return {"ok": False, "reason": (result.stdout or "slicer failed")[:500]}

            xml, gcode = slicedata.read_3mf(out_3mf)
            est = slicedata.build_estimate(
                slicedata.parse_slice_info(xml),
                slicedata.parse_gcode_footer(gcode),
                price_fallback=price_fallback,
            )
            return {"ok": True, "estimate": est}

    # ------------------------------------------------------------------
    # App handoff
    # ------------------------------------------------------------------

    def open_in_app(
        self, model_path: str, destination: Destination | None = None
    ) -> dict[str, Any]:
        """Spawn OrcaSlicer with ``model_path`` and return immediately.

        Uses ``_launcher`` (injectable, defaults to ``subprocess.Popen``) so
        the GUI process is detached — we never block on it.
        """
        info = self.detect()
        exe: str = info.executable if info.executable is not None else "orca-slicer"

        try:
            self._launcher(
                [exe, model_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    def capabilities(self) -> Capabilities:
        return Capabilities(
            processes=["FDM"],
            materials=["PLA", "PETG", "ABS", "ASA", "TPU", "PA", "PC"],
            # Conservative default matching common bed-slinger range (mm)
            maxBuildSize=(256.0, 256.0, 256.0),
        )

    # ------------------------------------------------------------------
    # Submit (v1 stub)
    # ------------------------------------------------------------------

    def submit(
        self,
        model_path: str,
        destination: Destination,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        """Print submission is not enabled in v1."""
        return {"ok": False, "reason": "not enabled in v1"}
