"""
General-purpose helpers for the project.
IMPORTANT: This module must NOT import from other drlite.* modules
to avoid circular imports. Keep it self-contained.

Conventions:
- Pure utilities only (string/ID normalization, RNG helpers, collections).
- No game-specific classes imported here.
"""

from __future__ import annotations
from typing import Any, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Sequence, Tuple, TypeVar
import random
import re

T = TypeVar("T")

# ----------------------------
# Numeric coercion & clamping
# ----------------------------

def coerce_int(x: Any, default: int = 0) -> int:
    """Best-effort int conversion with default fallback."""
    try:
        return int(x)
    except Exception:
        return int(default)

def coerce_float(x: Any, default: float = 0.0) -> float:
    """Best-effort float conversion with default fallback."""
    try:
        return float(x)
    except Exception:
        return float(default)

def clamp(value: int, lo: int, hi: int) -> int:
    """Clamp integer 'value' to [lo, hi]."""
    return max(lo, min(hi, value))

# ----------------------------
# Random helpers
# ----------------------------

def get_rng(seed: Optional[int] = None) -> random.Random:
    """Return a dedicated RNG; use 'random' module if you prefer global state."""
    return random.Random(seed) if seed is not None else random.Random()

def weighted_choice(options: List[dict], weight_key: str = "weight") -> Optional[dict]:
    """
    Pick a single item from (item, weight) pairs.
    Negative weights are treated as 0. If all weights <= 0, returns the first item.
    """

    if not options:
        return None
    
    total = sum(float(x.get(weight_key, 0)) for x in options)
    if total <= 0:
        return random.choice(options)
        
    r = random.uniform(0, total)
    upto = 0.0
    for opt in options:
        w = float(opt.get(weight_key, 0))
        if upto + w >= r:
            return opt
        upto += w
    return options[-1]

def choice(seq: Sequence[T], rng: Optional[random.Random] = None) -> T:
    """Random choice that accepts an optional RNG."""
    if not seq:
        raise ValueError("choice() received an empty sequence.")
    r = rng or random
    return r.choice(seq)  # type: ignore[arg-type]

def randint_range(lo: int, hi: int, rng: Optional[random.Random] = None) -> int:
    """Random integer in [lo, hi], inclusive, with optional RNG."""
    r = rng or random
    return r.randint(lo, hi)

# ----------------------------
# Strings, slugs, tags
# ----------------------------

_slug_re = re.compile(r"[^a-z0-9]+", re.IGNORECASE)

def canonical_slug(s: str) -> str:
    """
    Lowercase ASCII-like slug: spaces/punctuation -> '_', collapse repeats, trim.
    NOTE: Does not strip accents; pre-normalize upstream if needed.
    """
    s = s.strip().lower()
    s = _slug_re.sub("_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")

def canonical_item_id(raw_name: str) -> str:
    """
    Converts 'Life Stone' -> 'life_stone'.
    """
    if not raw_name:
        return ""
    return str(raw_name).strip().lower().replace(" ", "_")

def canonical_demon_id(name: str) -> str:
    """Canonical demon ID (slug)."""
    return canonical_slug(name)

def normalize_tag(tag: str) -> str:
    """Normalize tags to a consistent lower snake-like form."""
    return canonical_slug(tag)

# ----------------------------
# Collections & dict helpers
# ----------------------------

def ensure_list_of_str(val: Any) -> List[str]:
    """
    Ensure value is a list[str]. Scalars -> [str(value)].
    None -> [].
    """
    if val is None:
        return []
    if isinstance(val, str):
        return [val]
    if isinstance(val, list):
        return [str(v) for v in val]
    return []

def unique_preserve_order(seq: Iterable[T]) -> List[T]:
    """De-duplicate preserving first-seen order."""
    seen: set = set()
    out: List[T] = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def nested_get(d: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    """
    Safe nested dictionary get: nested_get(obj, ["a","b","c"], default).
    Returns default if any key is missing or 'd' isn't a mapping at some level.
    """
    cur: Any = d
    for k in keys:
        if not isinstance(cur, Mapping) or k not in cur:
            return default
        cur = cur[k]
    return cur

def require_keys(d: Mapping[str, Any], keys: Sequence[str], ctx: str = "") -> None:
    """
    Validate required keys exist. Raises KeyError with context if missing.
    """
    missing = [k for k in keys if k not in d]
    if missing:
        prefix = f"[{ctx}] " if ctx else ""
        raise KeyError(prefix + "Missing keys: " + ", ".join(missing))

# ----------------------------
# Feedback helpers (tone & cues)
# ----------------------------

def tone_from_delta(delta: int) -> str:
    """
    Map rapport delta -> coarse tone label.
    Keep it free of game classes to avoid imports.
    """
    if delta > 0: return "contento"    
    if delta < 0: return "molesto"    
    return "pensativo"                 


def flavor_cue(personality_enum: Any, tone: str, cues_data: Dict[str, Any], default: str = "...") -> str:
    """
    Resolve a short textual cue from personality + tone against a mapping:
      cues_by_name = { "PLAYFUL": {"Delighted": "✨ hee-ho!", ...}, ... }
    'personality' can be an Enum or a string; we use its .name or str().
    """
    # Convert Enum to string key (e.g., Personality.GLOOMY -> "GLOOMY")
    p_name = getattr(personality_enum, "name", str(personality_enum))
    
    # Look up in the dictionary
    p_data = cues_data.get(p_name, {})
    
    # Tone mapping (English keys in JSON -> Spanish tone internal logic)
    # Assuming JSON uses keys like "happy", "annoyed", "neutral"
    tone_map = {
        "contento": "happy",
        "molesto": "annoyed",
        "pensativo": "neutral"
    }
    json_key = tone_map.get(tone, "neutral")
    
    candidates = p_data.get(json_key, [])
    if not candidates:
        return default
        
    return random.choice(candidates)

def resolve_event_ref(effect: Dict[str, Any], registry: Dict[str, Any]) -> Dict[str, Any]:
    """
    If the effect has an 'event_ref' key, look it up in the registry
    and inject the full event definition under the 'event' key.
    """
    ref = effect.get("event_ref")
    if ref:
        # Buscamos en el registro inyectado
        ev_data = registry.get(ref)
        if ev_data:
            effect["event"] = ev_data
    return effect

# ----------------------------
# Backward-compat aliases
# ----------------------------

_coerce_int = coerce_int
_coerce_float = coerce_float
_weighted_choice = weighted_choice
_canonical_demon_id = canonical_demon_id
_canonical_item_id = canonical_item_id
_tone_from_delta = tone_from_delta

__all__ = [
    "coerce_int", "coerce_float", "clamp",
    "get_rng", "weighted_choice", "choice", "randint_range",
    "canonical_slug", "canonical_item_id", "canonical_demon_id", "normalize_tag",
    "ensure_list_of_str", "unique_preserve_order", "nested_get", "require_keys",
    "tone_from_delta", "flavor_cue", "resolve_event_ref"
]