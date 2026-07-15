"""Versioned manufacturing knowledge loaded from the shipped JSON catalog."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache
def load() -> dict:
    path = Path(__file__).with_name("manufacturing_catalog.json")
    return json.loads(path.read_text(encoding="utf-8"))


def base_process(base: str) -> str | None:
    return (load()["bases"].get(base) or {}).get("defaultProcess")


def process(process_id: str) -> dict | None:
    return load()["processes"].get(process_id)


def profile_settings(process_id: str) -> set[str]:
    entry = process(process_id)
    return set(entry.get("profileSettings", [])) if entry else set()


def rule_pack(process_id: str) -> str | None:
    entry = process(process_id)
    return entry.get("rulePack") if entry else None
