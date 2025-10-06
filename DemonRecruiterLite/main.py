"""
SMT-lite: Demon Recruitment.
Description: 
    - Light mini game to simulate the Demon Recruitment system on SMT. 
    - Made to be implemented in Cognitas Discord Bot.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, TypedDict, Set, Final, Any, Literal, NotRequired
import textwrap
from shutil import get_terminal_size
from enum import Enum
from datetime import datetime
import os, json, tempfile
import random
import time

# ====== Global registry and Defaults ======
RAPPORT_MIN, RAPPORT_MAX = -3, 3
AXIS_MIN, AXIS_MAX       = -5, 5
TOL_MIN, TOL_MAX         = 1, 5
RNG_SEED                 = None
ROUND_DELAY_SEC          = 0
PERSONALITY_TAG_WEIGHTS: dict[Personality, dict[str, int]] = {}
ITEM_CATALOG: Dict[str, ItemDef] = {}
EVENTS_REGISTRY: Dict[str, EventPayload] = {}
WHIMS_CONFIG: Dict[str, Any] = {}
WHIM_TEMPLATES: List[EventPayload] = []
PERSONALITY_CUES_BY_NAME: Dict[str, Dict[str, str]] = {}
SAVE_PATH = "saves/slot1.json"
ASSETS_MANIFEST: Dict[str, Any] = {}

# =========================
# OOP Models
# =========================



class EventPayload(TypedDict, total=False):
    type: Literal["ask_gold", "ask_item", "trap", "whim"]
    # Common:
    message: NotRequired[str]

    # ask_gold:
    amount: NotRequired[int]
    pay_rapport: NotRequired[int]
    refuse_rapport: NotRequired[int]
    flee_on_refuse: NotRequired[bool]
    join_on_pay: NotRequired[bool]

    # ask_item:
    item: NotRequired[str]
    amount: NotRequired[int]
    consume: NotRequired[bool]
    give_rapport: NotRequired[int]
    decline_rapport: NotRequired[int]
    amount_range: NotRequired[List[int]]
    join_on_give: NotRequired[int]

    # trap:
    penalty_rapport: NotRequired[int]
    flee_chance: NotRequired[float]

    # whims:
    kind: NotRequired[str]
    only_if_has_item: NotRequired[bool]
    weight: NotRequired[int]

class Effect(TypedDict, total=False):
    dLC: int
    dLD: int
    dRapport: int
    tags: List[str]
    event: EventPayload
    event_ref: str

class ItemDef(TypedDict, total=False):
    display_name: str
    rarity: Literal["common", "uncommon", "rare", "epic", "legendary"]
    value: int
    stackable: bool
    description: str




# =========================
# OOP Models (Save state)
# =========================


# =========================
# Helpers
# =========================



def _parse_personality(val: Any) -> Personality:
    if isinstance(val, Personality):
        return val
    if isinstance(val, str):
        key = val.strip().upper()
        try:
            return Personality[key]
        except KeyError:
            # Accept values already like "PLAYFUL" or with proper casing
            for p in Personality:
                if p.value.upper() == key:
                    return p
    raise ValueError(f"Invalid personality value: {val!r}")

def clamp(x: int, lo: int, hi: int) -> int:
    return lo if x < lo else hi if x > hi else x



def resolve_event_ref(effect: Effect) -> Effect:
    """Return a copy of effect with an embedded 'event' if it had 'event_ref'."""
    if not isinstance(effect, dict):
        return effect
    ref = effect.get("event_ref")
    if not ref:
        return effect
    payload = EVENTS_REGISTRY.get(str(ref))
    if not payload:
        print(f"[warn] Unknown event_ref '{ref}'. Ignoring.")
        return effect
    eff = dict(effect)
    eff["event"] = payload  # do NOT delete event_ref; harmless to keep or remove
    return eff

def _split_tag_sentiment(personality: Personality, tags: List[str]) -> tuple[List[str], List[str]]:
    """Classify which tags were liked/disliked based on loaded weights (JSON)."""
    weights = PERSONALITY_TAG_WEIGHTS.get(personality, {})
    liked, disliked = [], []
    for t in tags:
        w = int(weights.get(t, 0))
        if w > 0:  liked.append(t)
        elif w < 0: disliked.append(t)
    return liked, disliked

def rapport_gauge(val: int, lo: int = RAPPORT_MIN, hi: int = RAPPORT_MAX) -> str:
    """
    Text gauge for rapport. Example (min=-3..max=3):
    [··|·#··]  → '|' marks 0; '#' marks current value.
    """
    width = hi - lo + 1
    width = max(3, width)  # safety
    cells = ["·"] * width

    # current index and zero-index (clamped)
    idx = max(0, min(width - 1, val - lo))
    zero = max(0, min(width - 1, 0 - lo))

    cells[zero] = "|"     # zero marker
    cells[idx] = "#"      # current value
    return "[" + "".join(cells) + "]"


def distance_trend(delta: int) -> str:
    """
    Arrow showing how distance changed this turn:
      < 0 → closer; > 0 → farther; 0 → unchanged.
    """
    if delta < 0:
        return "↘ closer"
    if delta > 0:
        return "↗ farther"
    return "→ unchanged"







def _resolve_source_root(source_key: str) -> str:
    src = ASSETS_MANIFEST.get("sources", {}).get(source_key)
    if not src:
        raise KeyError(f"Unknown sprite_source '{source_key}' in assets manifest.")
    return src.get("root", "")



# Simple ANSI style helper
def _style(text: str, code: str, enable: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if enable else text

def _rarity_label(rarity_obj, color: bool) -> str:
    # Works whether rarity is an Enum or a plain string
    if isinstance(rarity_obj, Enum):
        key = rarity_obj.value
        raw = rarity_obj.value.upper()
    else:
        key = str(rarity_obj).lower()
        raw = str(rarity_obj).upper()

    # Color theme per rarity (feel free to tweak)
    palette = {
        "common":    "37",   # gray
        "uncommon":  "32",   # green
        "rare":      "34",   # blue
        "epic":      "35",   # magenta
        "legendary": "33",   # yellow
    }
    return _style(raw, palette.get(key, "37"), color)


# =========================
# Save/load helpers
# =========================



# =========================
# Serialization helpers
# =========================

SAVE_VERSION = 2  # bump if you change format later



# =========================
# Validation helpers
# =========================


def validate_events_against_items() -> None:
    # ensure all ask_item in EVENTS_REGISTRY reference catalog items
    for eid, ev in EVENTS_REGISTRY.items():
        if ev.get("type") == "ask_item":
            iid = canonical_item_id(ev.get("item", ""))
            if iid not in ITEM_CATALOG:
                raise ValueError(f"Event '{eid}' references unknown item '{iid}'.")


# =========================
# Loaders
# =========================



# =========================
#  Console-layer Functions
# =========================



def run_special_event(session: NegotiationSession, event: EventPayload) -> Dict[str, Any]:
    """
    Console interaction for special events. Returns a decision dict.
    """
    et = str(event.get("type", "")).lower()
    msg = event.get("message")
    if msg:
        print(f"\n[Evento] {msg}")

    # --- Ask gold or whim(kind=ask_gold) ---
    if et in ("ask_gold", "whim") and (event.get("kind") == "ask_gold" or et == "ask_gold"):
        amount = int(event.get("amount", 0))
        print(f"Te quedan {session.player.gold} monedas.")
        while True:
            ans = input(f"¿Pagar {amount} monedas? (s/n): ").strip().lower()
            if ans in {"s", "n"}:
                return {"pay": ans == "s"}

    # --- Ask item (classic SMT flow) ---
    if et == "ask_item":
        raw_item = str(event.get("item", "")).strip()
        amount = int(event.get("amount", 1))
        iid = canonical_item_id(raw_item)
        meta = ITEM_CATALOG.get(iid, {})
        disp = meta.get("display_name", raw_item.title())
        have = session.player.inventory.get(iid, 0)

        print(f"{session.demon.name} quiere {amount}x {disp}. (Tienes: {have})")
        if have < amount:
            print("No tienes suficientes. (No puedes aceptar.)")
            return {"give": False}

        while True:
            ans = input(f"¿Entregar {amount}x {disp}? (s/n): ").strip().lower()
            if ans in {"s", "n"}:
                return {"give": ans == "s"}

    if et == "trap":
        print("Notas tensión en el aire…")
        return {}

    return {}




# =========================
#  Main function
# =========================


def main() -> None:
    """Bootstrap the game, load all registries, and run one negotiation session."""
    print_banner()

    # Config: limits, UI delay, RNG seed (may print status)
    try:
        load_config("config.json")
    except Exception as e:
        # Fail-fast is fine; but you can opt to continue with defaults
        print(f"[config] Error loading config.json: {e}. Using defaults.")

    # RNG: create a single Random to inject everywhere (deterministic if RNG_SEED is set)
    rng = random.Random(RNG_SEED) if RNG_SEED is not None else random.Random()

    # Personality weights/cues (optional: neutral if file missing)
    try:
        load_personality_weights("data/personality_weights.json")
    except Exception as e:
        print(f"[weights] Error: {e}. Personality bonuses disabled.")

    try:
        load_personality_cues("data/personality_cues.json")
    except Exception as e:
        print(f"[weights] Error: {e}. Personality bonuses disabled.")


    # Items catalog (needed before validating events/questions that reference items)
    try:
        load_item_catalog("data/items.json")
    except Exception as e:
        print(f"[items] Error: {e}. Loading empty catalog.")
        # ITEM_CATALOG will be {} (your loader already handles this case)

    # Event templates (events.json) and 6) Whims config (whims.json)
    try:
        load_events("data/events.json")
    except Exception as e:
        print(f"[events] Error: {e}. Events registry is empty.")

    try:
        load_whims("data/whims.json")
    except Exception as e:
        print(f"[whims] Error: {e}. Whims disabled.")

    # Questions (after events/items so we can validate references)
    try:
        questions_pool = load_questions("data/questions.json")
    except Exception as e:
        raise RuntimeError(f"[questions] Failed to load questions: {e}") from e

    # Cross-validations (fail fast if data is inconsistent)
    try:
        validate_events_against_items()              # events ask_item → must exist in ITEM_CATALOG
        validate_questions_against_items(questions_pool)  # choices with ask_item → must exist in ITEM_CATALOG
        validate_event_refs(questions_pool)          # event_ref in questions → must exist in EVENTS_REGISTRY
        validate_portraits(demons_catalog, strict=True)
    except Exception as e:
        raise RuntimeError(f"[validate] Data validation failed: {e}") from e

    # Demons
    try:
        demons_catalog = load_demons("data/demons.json")
    except Exception as e:
        raise RuntimeError(f"[demons] Failed to load demons: {e}") from e

    try:
        load_assets_manifest("assets_manifest.json")
    except Exception as e:
        raise RuntimeError(f"[demons] Failed to load assets: {e}") from e

    # Difficulty input (validated and clamped inside the function)
    diff_level = read_difficulty()

    session = bootstrap_session(demons_catalog, questions_pool, rng)

    # Run loop with graceful keyboard interrupt handling
    try:
        run_game_loop(session, diff_level, demons_catalog)
    except (KeyboardInterrupt, EOFError):
        print("\n[!] Interrupted by user. Ending negotiation softly…")
        session.in_progress = False
        session.fled = True
    finally:
        summarize_session(session)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        # Covers interruptions before main builds the session
        print("\nBye!")

