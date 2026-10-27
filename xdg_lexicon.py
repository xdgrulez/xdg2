"""Compile generic base-lexicon records into XDG lexical entries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


LEXICON_DIR = Path(__file__).parent / "Lexicon"


def load_xdg_lexicon(language: str = "de") -> dict[str, dict[str, Any]]:
    base_path = LEXICON_DIR / f"base_{language}.json"
    overlay_name = "xdg_overlay.json" if language == "de" else f"xdg_overlay_{language}.json"
    overlay_path = LEXICON_DIR / overlay_name
    base = json.loads(base_path.read_text(encoding="utf-8"))
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    compiled: dict[str, dict[str, Any]] = {}
    for entry in base["entries"]:
        entry_id = entry["entry_id"]
        if entry_id not in overlay:
            raise ValueError(f"No XDG overlay for base lexicon entry {entry_id!r}")
        compiled[entry_id] = {
            **entry,
            "language": base["language"],
            "source": base["source"],
            "xdg": overlay[entry_id],
        }
    unused_overlays = set(overlay) - set(compiled)
    if unused_overlays:
        raise ValueError(f"XDG overlays have no base lexicon entry: {sorted(unused_overlays)}")
    return compiled


def xdg_entry(entry_id: str) -> dict[str, Any]:
    return load_xdg_lexicon()[entry_id]


def xdg_lexicon_datalog_facts() -> list[tuple[str, tuple[Any, ...]]]:
    """Flatten base lexical features into facts for hard Datalog filtering."""
    facts: list[tuple[str, tuple[Any, ...]]] = []
    for entry_id, entry in load_xdg_lexicon().items():
        features = entry.get("features", {})
        facts.append(
            (
                "base_lex_entry",
                (
                    entry_id,
                    entry["lemma"],
                    entry["pos"],
                    features.get("gender", "_"),
                    features.get("number", "_"),
                    entry["semantic_type"],
                ),
            )
        )
    return facts
