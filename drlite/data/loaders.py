from __future__ import annotations
from typing import List, Dict, Any
import json, os

from drlite.models import Demon, Alignment, Question, Personality
from drlite.utils import canonical_slug, coerce_int, canonical_item_id, ensure_list_of_str
from drlite.data.types import ItemDef, Effect, Rarity


# ==============================================================================
#  HELPERS
# ==============================================================================

def _parse_alignment(raw_val: Any) -> Alignment:
    if isinstance(raw_val, dict):
        return Alignment(int(raw_val.get("law_chaos", 0)), int(raw_val.get("light_dark", 0)))
    if isinstance(raw_val, (list, tuple)) and len(raw_val) >= 2:
        return Alignment(int(raw_val[0]), int(raw_val[1]))
    return Alignment(0, 0)

# ==============================================================================
#  LOADERS
# ==============================================================================

def load_demons(path: str) -> List[Demon]:
    """
    Load demons from JSON:
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
            lc = coerce_int(al.get("law_chaos", 0))
            ld = coerce_int(al.get("light_dark", 0))
            align = Alignment(law_chaos=lc, light_dark=ld)
            r_str = str(item.get("rarity", "COMMON")).upper()
            r_enum = getattr(Rarity, r_str, Rarity.COMMON)

            personality = _parse_personality(item.get("personality", "PLAYFUL"))
            patience = coerce_int(item.get("patience", 4), 4)
            tolerance = coerce_int(item.get("tolerance", 3), 3)
            rapport_needed = coerce_int(item.get("rapport_needed", 2), 2)

            demons.append(
                Demon(
                    id=did,
                    name=name,
                    alignment=align,
                    personality=personality,
                    rarity=r_enum,
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
            tags = ensure_list_of_str(q.get("tags", []))

            choices_raw = q.get("choices", {})
            if not isinstance(choices_raw, dict) or not choices_raw:
                raise ValueError("choices must be a non-empty object.")

            # Normalize effects
            norm_choices: Dict[str, Effect] = {}
            for label, eff in choices_raw.items():
                if not isinstance(eff, dict):
                    raise ValueError(f"choice '{label}' must be an object with dLC/dLD/dRapport.")
                norm_choices[str(label)] = Effect(
                    dLC=coerce_int(eff.get("dLC", 0)),
                    dLD=coerce_int(eff.get("dLD", 0)),
                    dRapport=coerce_int(eff.get("dRapport", 0)),
                    tags=ensure_list_of_str(eff.get("tags", [])),
                )

            questions.append(Question(id=qid, text=text, tags=tags, choices=norm_choices))

        except Exception as e:
            raise ValueError(f"Invalid question at index {i}: {e}") from e

    return questions

def load_personality_weights(path: str = "data/personality_weights.json") -> None:
    """
    Load personality tag weights and RETURN them.
    """

    if not os.path.exists(path):
        print(f"[weights] {path} not found. Returning empty weights.")
        return {}

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError("personality_weights.json must be a JSON object mapping personality -> tag map.")

    weights: Dict[str, Dict[str, int]] = {}
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

        p_key = p_name.strip().upper() 
        weights[p_key] = {str(k).lower(): int(v) for k, v in tagmap.items()}

    print(f"[weights] Loaded weights for {len(weights)} personalities.")
    return weights

def load_item_catalog(path: str = "data/items.json") -> Dict[str, ItemDef]:
    if not os.path.exists(path):
        print(f"[items] Items not found on {path}")
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        catalog = {}
        for raw_key, meta in raw.items():
            key = raw_key.lower() 
            
            r_str = str(meta.get("rarity", "COMMON")).upper()
            r_enum = getattr(Rarity, r_str, Rarity.COMMON)

            catalog[key] = ItemDef(
                display_name=str(meta.get("display_name") or raw_key.title()),
                rarity=r_enum,
                value=int(meta.get("value", 0)),
                stackable=bool(meta.get("stackable", True)),
                description=str(meta.get("description", "")),
            )
        
        print(f"[Items] Loaded {len(catalog)} items.")
        return catalog
    except Exception as e:
        print(f"[Items] Error: {e}")
        return {}

    
    

def load_events(path: str = "data/events.json"):
    """Load and RETURN event catalog."""
    if not os.path.exists(path):
        print(f"[events] {path} not found. Loaded empty registry.")
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("events.json must be an object mapping id -> event payload.")

    # normalize a bit (clamp ranges later if needed)
    events = {str(k): v for k, v in data.items()}

    return events
    print(f"[events] Loaded {len(events)} events.")


def load_whims(path: str = "data/whims.json"):
    """Load whim config and templates."""
    if not os.path.exists(path):
        print(f"[whims] {path} not found. Whims disabled.")
        return {}, []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("whims.json must be an object with base_chance, personality_mod, entries[].")

    whim_config = {
        "base_chance": float(data.get("base_chance", 0.0)),
        "personality_mod": {str(k).upper(): float(v) for k, v in data.get("personality_mod", {}).items()},
    }
    entries = data.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("whims.json 'entries' must be a list.")

    norm_entries: List[EventPayload] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        e = dict(e)
        e["type"] = str(e.get("type", "")).lower()  # ask_gold/ask_item
        e["id"] = str(e.get("id", ""))
        e["weight"] = int(e.get("weight", 1))
        norm_entries.append(e)  # we keep validation light for now

    whim_templates = norm_entries

    print(f"[whims] Loaded {len(whim_templates)} whim templates.")
    return whim_config, whim_templates

def load_personality_cues(path: str = "data/personality_cues.json") -> None:
    """Load and RETURN personality cues catalog."""

    if not os.path.exists(path):
        print(f"[cues] {path} not found. Using default emoji-only cues.")
        return {}

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

    total = sum(len(v) for v in table.values())
    print(f"[cues] Loaded {total} cues across {len(table)} personalities.")
    return table

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