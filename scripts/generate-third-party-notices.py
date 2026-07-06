#!/usr/bin/env python3
"""Generate THIRD-PARTY-NOTICES.txt for the solidifai desktop app.

The installers minify the frontend's production npm closure and statically
compile the Rust crate graph, which strips the copyright/license texts that
MIT/BSD/ISC condition redistribution on. This aggregates both closures
(pnpm licenses list + cargo metadata) into one notices file: an inventory of
every package with its license expression and source URL, followed by each
package's license text, deduplicated.

Run from the repo root after `pnpm install`; cargo metadata fetches any crate
sources it is missing. release-build.yml runs this once per release and
uploads the result as a release asset.

Usage: generate-third-party-notices.py <out.txt>
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

LICENSE_GLOBS = ("LICENSE*", "LICENCE*", "COPYING*", "NOTICE*")


def read_license_texts(pkg_dir: Path) -> list[str]:
    """All license-ish file texts in a package root, deduplicated."""
    texts, seen = [], set()
    for pattern in LICENSE_GLOBS:
        # Also match lowercase names on case-sensitive filesystems.
        for f in sorted(list(pkg_dir.glob(pattern)) + list(pkg_dir.glob(pattern.lower()))):
            real = f.resolve()
            if real in seen or not f.is_file():
                continue
            seen.add(real)
            try:
                texts.append(f.read_text(encoding="utf-8", errors="replace").strip())
            except OSError:
                continue
    return texts


def npm_store_dir(root: Path, path: str) -> Path:
    """pnpm reports store paths without the node_modules/.pnpm/ segment
    (e.g. <root>/react@19.2.7/node_modules/react); put it back."""
    p = Path(path)
    if p.is_dir():
        return p
    try:
        fixed = root / "node_modules" / ".pnpm" / p.relative_to(root)
    except ValueError:
        return p
    return fixed if fixed.is_dir() else p


def npm_packages(root: Path) -> list[dict]:
    raw = subprocess.run(
        ["pnpm", "licenses", "list", "--prod", "--json"],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout
    pkgs = []
    for entries in json.loads(raw).values():
        for e in entries:
            texts = []
            for p in e.get("paths") or []:
                texts += read_license_texts(npm_store_dir(root, p))
            pkgs.append({
                "name": e["name"],
                "version": ", ".join(e.get("versions", [])),
                "license": e.get("license", "unknown"),
                "url": e.get("homepage") or "",
                "texts": texts,
            })
    return pkgs


def cargo_packages(root: Path) -> list[dict]:
    raw = subprocess.run(
        ["cargo", "metadata", "--format-version", "1",
         "--manifest-path", str(root / "src-tauri" / "Cargo.toml")],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout
    meta = json.loads(raw)
    members = set(meta["workspace_members"])
    pkgs = []
    for p in meta["packages"]:
        if p["id"] in members:
            continue  # our own crates, not third-party
        pkgs.append({
            "name": p["name"],
            "version": p["version"],
            "license": p.get("license") or p.get("license_file") or "unknown",
            "url": p.get("repository") or "",
            "texts": read_license_texts(Path(p["manifest_path"]).parent),
        })
    return pkgs


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(__doc__.strip())
    out = Path(sys.argv[1])
    root = Path(__file__).resolve().parent.parent

    sections = [
        ("npm packages (production frontend bundle)", npm_packages(root)),
        ("Rust crates (compiled into the application binary)", cargo_packages(root)),
    ]

    # Dedupe identical license texts across packages; the inventory lines
    # reference them by number.
    unique: list[str] = []
    index: dict[str, int] = {}

    def ref(text: str) -> int:
        h = hashlib.sha256(text.encode()).hexdigest()
        if h not in index:
            unique.append(text)
            index[h] = len(unique)
        return index[h]

    rule = "=" * 78
    lines = [
        rule,
        "THIRD-PARTY NOTICES for the solidifai desktop application",
        rule,
        "",
        "solidifai is licensed under the Apache License 2.0",
        "(https://github.com/itsJeremyMax/solidifai). The application also",
        "distributes the third-party packages listed below, in minified or",
        "compiled form. Each entry names its license and refers to the license",
        "text(s), including copyright notices, reproduced in full after the",
        "inventory. For packages under MPL-2.0, the corresponding source is",
        "available unmodified from the listed repository. The engine bundle",
        "fetched or installed alongside the app carries its own",
        "THIRD-PARTY-NOTICES.txt.",
        "",
    ]
    for title, pkgs in sections:
        lines += [rule, title, rule, ""]
        for p in sorted(pkgs, key=lambda p: (p["name"].lower(), p["version"])):
            refs = sorted({ref(t) for t in p["texts"]})
            refs_s = "texts " + ", ".join(f"#{r}" for r in refs) if refs else "no text shipped"
            lines.append(f"{p['name']} {p['version']} | {p['license']} | {refs_s}"
                         + (f" | {p['url']}" if p["url"] else ""))
        lines.append("")

    lines += [rule, "License texts", rule, ""]
    for i, text in enumerate(unique, 1):
        lines += [f"---------- text #{i} ----------", "", text, ""]

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    total = sum(len(p) for _, p in sections)
    print(f"wrote {out}: {total} packages, {len(unique)} unique license texts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
