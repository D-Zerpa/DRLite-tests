from __future__ import annotations
from typing import Dict, Any, Optional, List
import os, json

ASSETS_MANIFEST: Dict[str, Any] = {}


def load_assets_manifest(path: str = "assets_manifest.json") -> None:
    """
    Load the portraits-only manifest into ASSETS_MANIFEST.
    Schema:
      {
        "sources": { "sjr": { "root": "assets/sjr/portraits/", "ext": "png" } },
        "map": { "pixie": { "portrait": "pixie.png" } }
      }
    """
    global ASSETS_MANIFEST
    if not os.path.exists(path):
        print(f"[assets] {path} not found. Portraits will be unavailable.")
        ASSETS_MANIFEST = {"sources": {}, "map": {}}
        return
    with open(path, "r", encoding="utf-8") as f:
        ASSETS_MANIFEST = json.load(f)
    if "sources" not in ASSETS_MANIFEST or "map" not in ASSETS_MANIFEST:
        raise ValueError("assets_manifest.json must contain 'sources' and 'map' keys.")
    print(f"[assets] Manifest loaded with {len(ASSETS_MANIFEST.get('map', {}))} entries.")


def get_portrait_path(demon: "Demon", variant: str = "neutral") -> Optional[str]:
    """
    Return the absolute path to the demon's portrait file, or None if not found.
    Supports two forms:
      "portrait": "file.png"
      "portrait": { "neutral": "file.png", "angry": "file2.png", ... }
    """
    sources = ASSETS_MANIFEST.get("sources", {})
    amap = ASSETS_MANIFEST.get("map", {})
    src_key = getattr(demon, "sprite_source", None) or "sjr"
    key = getattr(demon, "sprite_key", None) or demon.id

    entry = amap.get(key)
    if not entry:
        return None

    p = entry.get("portrait")
    if p is None:
        return None

    # string or dict
    if isinstance(p, str):
        filename = p
    elif isinstance(p, dict):
        filename = p.get(variant) or p.get("neutral")
        if not filename:
            # pick any available variant as fallback
            filename = next(iter(p.values()), None)
    else:
        return None

    if not filename:
        return None

    root = _resolve_source_root(src_key)
    return os.path.join(root, filename)

def validate_portraits(demons: list["Demon"], strict: bool = True) -> None:
    """
    Validate that every demon has a portrait entry and the file exists.
    If strict=False, only warn for missing files; otherwise raise.
    """
    problems = []
    for d in demons:
        path = get_portrait_path(d)
        if path is None:
            problems.append(f"[{d.id}] portrait not mapped (source={getattr(d, 'sprite_source', 'sjr')}, key={getattr(d, 'sprite_key', d.id)})")
        else:
            if not os.path.exists(path):
                problems.append(f"[{d.id}] portrait file missing: {path}")

    if problems:
        msg = "\n".join(problems[:12])
        if strict:
            raise RuntimeError(f"[assets] Portrait validation failed ({len(problems)} issues):\n{msg}")
        else:
            print(f"[assets] Portrait validation warnings ({len(problems)}):\n{msg}")
    else:
        print(f"[assets] Portraits validated for {len(demons)} demons.")