#!/usr/bin/env python3
"""Build solidifai-engine-index.json from the manifests + sha256 sidecars on the `engine`
release. The app reads it to resolve which assets to fetch for its pinned rev.

Usage: build-engine-index.py <repo> <assets_dir> <out.json> [latest_rev]
Asset naming: solidifai-engine-<platform>-<rev>.{manifest.json,full.tar.zst,...}
              solidifai-engine-<platform>-<prev>.<rev>.pack.tar.zst
(single dot between revs: GitHub rewrites ".." in uploaded asset names to ".")
"""
import json
import sys
from pathlib import Path


def main() -> int:
    repo, assets_dir, out = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    # Caller-supplied (from release-asset upload times); the mtime fallback is
    # only meaningful when the assets were produced locally, not downloaded.
    latest_override = sys.argv[4] if len(sys.argv) > 4 else ""
    base = f"https://github.com/{repo}/releases/download/engine"

    def sha(name: str) -> str:
        f = assets_dir / f"{name}.sha256"
        return f.read_text().strip() if f.is_file() else ""

    revs: dict[str, dict] = {}
    latest_rev, latest_mtime = "", -1.0

    for man in sorted(assets_dir.glob("solidifai-engine-*.manifest.json")):
        meta = json.loads(man.read_text())
        rev, plat, mhash = meta["engineRev"], meta["platform"], meta["manifestHash"]
        stem = f"solidifai-engine-{plat}-{rev}"

        # incremental pack into this rev, if a sidecar is present
        pack = None
        prev = None
        for sidecar in assets_dir.glob(f"solidifai-engine-{plat}-*.{rev}.pack.tar.zst.sha256"):
            packname = sidecar.name[: -len(".sha256")]
            prev = packname[len(f"solidifai-engine-{plat}-") :].split(".")[0]
            pack = {"from": prev, "url": f"{base}/{packname}", "sha256": sidecar.read_text().strip()}
            break

        entry = revs.setdefault(rev, {"prev": prev, "platforms": {}})
        if prev:
            entry["prev"] = prev
        entry["platforms"][plat] = {
            "manifest": f"{base}/{stem}.manifest.json",
            "manifestSig": f"{base}/{stem}.manifest.json.sig",
            "manifestHash": mhash,
            "full": f"{base}/{stem}.full.tar.zst",
            "fullSha256": sha(f"{stem}.full.tar.zst"),
            **({"pack": pack} if pack else {}),
        }

        m = man.stat().st_mtime
        if m > latest_mtime:
            latest_mtime, latest_rev = m, rev

    latest = latest_override if latest_override in revs else latest_rev
    Path(out).write_text(json.dumps({"latestRev": latest, "revs": revs}, indent=2))
    print(f"wrote {out}: {len(revs)} rev(s), latest={latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
