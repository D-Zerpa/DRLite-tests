from __future__ import annotations
from typing import List, Dict, Any
import json, os

from drlite.models import Demon, Alignment, Question, Personality
from drlite.utils import canonical_slug, coerce_int


def load_demons(path: str) -> List[Demon]:
    """
    Load demons from JSON:
    [
      {
        "name": "Pixie",
        "alignment": {"law_chaos": 1, "light_dark": 2},
        "personality": "PLAYFUL",
        "patience": 5, "tolerance": 4, "rapport_needed": 2
      }, ...
    ]
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Demons file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    demons: List[Demon] = []
    if not isinstance(raw, list):
        raise ValueError("demons.json must contain a list of demons.")

    for i, item in enumerate(raw, start=1):
        try:
            name = str(item["name"])
            did = str(item.get("id") or _canonical_demon_id(name))
            al = item.get("alignment", {})
            lc = _coerce_int(al.get("law_chaos", 0))
            ld = _coerce_int(al.get("light_dark", 0))
            align = Alignment(law_chaos=lc, light_dark=ld)

            personality = _parse_personality(item.get("personality", "PLAYFUL"))
            patience = _coerce_int(item.get("patience", 4), 4)
            tolerance = _coerce_int(item.get("tolerance", 3), 3)
            rapport_needed = _coerce_int(item.get("rapport_needed", 2), 2)

            demons.append(
                Demon(
                    id=did,
                    name=name,
                    alignment=align,
                    personality=personality,
                    patience=patience,
                    tolerance=tolerance,
                    rapport_needed=rapport_needed,
                )
            )
        except Exception as e:
            raise ValueError(f"Invalid demon at index {i}: {e}") from e

    return demons

def load_questions(path: str) -> List[Question]:
    """
    Load questions from JSON:
    [
      {
        "id": "...",
        "text": "...",
        "tags": ["..."],
        "choices": {
           "Option label": {"dLC":0,"dLD":1,"dRapport":1,"tags":["..."]},
           ...
        }
      }, ...
    ]
    """
    # Allow singular/plural fallback if you wish
    if not os.path.exists(path):
        alt = path.replace("question.json", "questions.json")
        if os.path.exists(alt):
            path = alt
        else:
            raise FileNotFoundError(f"Questions file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        raise ValueError("questions.json must contain a list of questions.")

    questions: List[Question] = []
    for i, q in enumerate(raw, start=1):
        try:
            qid = str(q["id"])
            text = str(q["text"])
            tags = _ensure_list_of_str(q.get("tags", []))

            choices_raw = q.get("choices", {})
            if not isinstance(choices_raw, dict) or not choices_raw:
                raise ValueError("choices must be a non-empty object.")

            # Normalize effects
            norm_choices: Dict[str, Effect] = {}
            for label, eff in choices_raw.items():
                if not isinstance(eff, dict):
                    raise ValueError(f"choice '{label}' must be an object with dLC/dLD/dRapport.")
                norm_choices[str(label)] = Effect(
                    dLC=_coerce_int(eff.get("dLC", 0)),
                    dLD=_coerce_int(eff.get("dLD", 0)),
                    dRapport=_coerce_int(eff.get("dRapport", 0)),
                    tags=_ensure_list_of_str(eff.get("tags", [])),
                )

            questions.append(Question(id=qid, text=text, tags=tags, choices=norm_choices))

        except Exception as e:
            raise ValueError(f"Invalid question at index {i}: {e}") from e

    return questions

def load_personality_weights(path: str = "data/personality_weights.json") -> None:
    """
    Load personality tag weights from JSON into PERSONALITY_TAG_WEIGHTS.
    JSON schema:
      { "PLAYFUL": {"humor": 2, "order": -1, ...}, "CUNNING": {...}, ... }

    - Keys must be Personality names (case-insensitive).
    - Inner keys are tag strings (we normalize to lowercase).
    - Values are ints; clamped to [-2, 2].
    If file is missing or empty, we fall back to neutral (no bonuses).
    """
    global PERSONALITY_TAG_WEIGHTS

    if not os.path.exists(path):
        print(f"[weights] {path} not found. Using neutral weights (no personality bonuses).")
        PERSONALITY_TAG_WEIGHTS = {}
        return

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError("personality_weights.json must be a JSON object mapping personality -> tag map.")

    weights: dict[Personality, dict[str, int]] = {}
    for p_name, tagmap in raw.items():
        if not isinstance(tagmap, dict):
            raise ValueError(f"Invalid tag map for personality {p_name!r}: must be an object.")

        # Map string to Personality enum (case-insensitive)
        try:
            p = Personality[p_name.strip().upper()]
        except KeyError as e:
            raise ValueError(f"Unknown personality name: {p_name!r}") from e

        inner: dict[str, int] = {}
        for tag, val in tagmap.items():
            try:
                v = int(val)
            except (TypeError, ValueError):
                raise ValueError(f"Weight for tag {tag!r} under {p_name!r} must be an integer.")
            # Clamp to [-2, 2]
            if v < -2: v = -2
            if v >  2: v =  2
            inner[str(tag).lower()] = v  # normalize tag key to lowercase

        weights[p] = inner

    PERSONALITY_TAG_WEIGHTS = weights
    total = sum(len(m) for m in weights.values())
    print(f"[weights] Loaded {total} tag weights across {len(weights)} personalities.")

def load_item_catalog(path: str = "data/items.json") -> None:
    """
    Load item catalog from JSON into ITEM_CATALOG.
    JSON schema (recommended): a single object mapping item_id -> ItemDef.
    All keys are normalized to lowercase.
    Defaults:
      rarity="common", value=0, stackable=True, description=""
      display_name = Title Case of the key if missing.
    """
    global ITEM_CATALOG

    if not os.path.exists(path):
        print(f"[items] {path} not found. Loaded empty catalog.")
        ITEM_CATALOG = {}
        return

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError("items.json must be a JSON object mapping item_id -> item metadata.")

    catalog: Dict[str, ItemDef] = {}
    for raw_key, meta in raw.items():
        key = canonical_item_id(raw_key)
        if not isinstance(meta, dict):
            raise ValueError(f"Item '{raw_key}' must have an object as value.")
        display = str(meta.get("display_name") or raw_key.title())
        rarity = str(meta.get("rarity") or "common").lower()
        if rarity not in {"common", "uncommon", "rare", "epic", "legendary"}:
            raise ValueError(f"Item '{raw_key}' has invalid rarity: {rarity}")
        try:
            value = int(meta.get("value", 0))
        except (TypeError, ValueError):
            value = 0
        stackable = bool(meta.get("stackable", True))
        desc = str(meta.get("description", ""))

        catalog[key] = ItemDef(
            display_name=display,
            rarity=rarity,      # type: ignore[assignment]
            value=value,
            stackable=stackable,
            description=desc,
        )

    ITEM_CATALOG = catalog
    print(f"[items] Loaded {len(ITEM_CATALOG)} items.")

def load_events(path: str = "data/events.json") -> None:
    """Load event templates by id into EVENTS_REGISTRY."""
    global EVENTS_REGISTRY
    if not os.path.exists(path):
        print(f"[events] {path} not found. Loaded empty registry.")
        EVENTS_REGISTRY = {}
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("events.json must be an object mapping id -> event payload.")
    # normalize a bit (clamp ranges later if needed)
    EVENTS_REGISTRY = {str(k): v for k, v in data.items()}
    print(f"[events] Loaded {len(EVENTS_REGISTRY)} events.")


def load_whims(path: str = "data/whims.json") -> None:
    """Load whim config and templates."""
    global WHIMS_CONFIG, WHIM_TEMPLATES
    if not os.path.exists(path):
        print(f"[whims] {path} not found. Whims disabled.")
        WHIMS_CONFIG, WHIM_TEMPLATES = {}, []
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("whims.json must be an object with base_chance, personality_mod, entries[].")
    WHIMS_CONFIG = {
        "base_chance": float(data.get("base_chance", 0.0)),
        "personality_mod": {str(k).upper(): float(v) for k, v in data.get("personality_mod", {}).items()},
    }
    entries = data.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("whims.json 'entries' must be a list.")
    # normalize ids and ensure required fields
    norm_entries: List[EventPayload] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        e = dict(e)
        e["type"] = str(e.get("type", "")).lower()  # ask_gold/ask_item
        e["id"] = str(e.get("id", ""))
        e["weight"] = int(e.get("weight", 1))
        norm_entries.append(e)  # we keep validation light for now
    WHIM_TEMPLATES = norm_entries
    print(f"[whims] Loaded {len(WHIM_TEMPLATES)} whim templates.")

def load_personality_cues(path: str = "data/personality_cues.json") -> None:
    """
    Load textual cues per Personality from JSON into PERSONALITY_CUES_BY_NAME.
    JSON schema: { "PLAYFUL": {"Delighted":"...", "Pleased":"...", ...}, ... }
    Keys are personality names (case-insensitive). Tone keys are used as-is.
    Missing file → empty table (fallback to default emoji at usage).
    """
    global PERSONALITY_CUES_BY_NAME

    if not os.path.exists(path):
        print(f"[cues] {path} not found. Using default emoji-only cues.")
        PERSONALITY_CUES_BY_NAME = {}
        return

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError("personality_cues.json must be an object mapping personality -> {tone: cue}.")

    # Normalize personality keys to upper-case names
    table: Dict[str, Dict[str, str]] = {}
    for pname, tones in raw.items():
        if not isinstance(tones, dict):
            raise ValueError(f"Cues for '{pname}' must be an object.")
        table[str(pname).strip().upper()] = {str(k): str(v) for k, v in tones.items()}

    PERSONALITY_CUES_BY_NAME = table
    total = sum(len(v) for v in table.values())
    print(f"[cues] Loaded {total} cues across {len(table)} personalities.")

def _parse_personality(val: Any) -> Personality:
    """Normalize personality from JSON (string or enum-like) to Personality enum."""
    if isinstance(val, Personality):
        return val
    if isinstance(val, str):
        key = val.strip().upper()
        try:
            return Personality[key]
        except KeyError:
            # Accept values already equal to enum.value
            for p in Personality:
                if p.value.upper() == key:
                    return p
    raise ValueError(f"Invalid personality value: {val!r}")