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

def show_menu(session) -> str:
    if not session.in_progress:
        print("La negociación ha terminado...")
        return "0"
    print("\n¿Qué deseas hacer?")
    print("1) Responder la siguiente pregunta")
    print("2) Bromear (minijuego rápido para ajustar rapport)")
    print("3) Mostrar estado de la sesión")
    print("4) Intentar cerrar trato ahora (evaluar unión)")
    print("5) Despedirse (terminar negociación)")
    print("6) Guardar y salir")  # NEW
    valid = {"1","2","3","4","5","6"}
    while True:
        choice = input("Elige una opción (1-6): ").strip()
        if choice in valid:
            return choice
        print("OPCION NO VALIDA. Intenta de nuevo.")


def dispatch_action(session, option: str, demons_catalog: list[Demon]) -> None:
    """
    Dispatch the selected option to the corresponding session action.
    Follows your spec strictly.
    """
    if option == "1":
        effect = session.ask()
        feedback = session.process_answer(effect)  # now returns ReactionFeedback

        # Show reaction feedback (console layer)
        print(f"{session.demon.name} looks {feedback.tone.lower()}. {feedback.cue}")
        # Optional hints (only print if non-empty)
        if feedback.liked_tags:
            print("  Liked tags: " + ", ".join(feedback.liked_tags))
        if feedback.disliked_tags:
            print("  Disliked tags: " + ", ".join(feedback.disliked_tags))
        # Compact numbers (you already show a HUD elsewhere, this is just a quick glance)
        print("  " + " | ".join(feedback.notes))

        # Intuitive indicators

        print(f"  Rapport gauge: {rapport_gauge(session.rapport)}")
        print(f"  Distance trend: {distance_trend(feedback.delta_distance)}")

    elif option == "2":
        # Simple rapport mini-game: guess a number 0..2
        secret = session.rng.randint(0, 2)

        while True:
            raw = input("Adivina un número (0-2): ").strip()
            if raw in {"0", "1", "2"}:
                guess = int(raw)
                break
            print("Entrada inválida. Intenta de nuevo (0, 1 o 2).")

        if guess == secret:
            print("¡Correcto!")
            session.rapport = min(RAPPORT_MAX, session.rapport + 2)
        else:
            print("Incorrecto.")
            session.rapport = max(RAPPORT_MIN, session.rapport - 1)

    elif option == "3":
        session.show_status()
    elif option == "4":
        session.check_union()
    elif option == "5":
        session.in_progress = False
        session.fled = True
        print(f"{session.demon.name} se marcha...")
    elif option == "6":
        save_game(SAVE_PATH, session.player, demons_catalog, session)
        print("Game saved. Exiting…")
        session.in_progress = False
        session.fled = True
    else:
        print("OPCION NO VALIDA.")


def print_banner() -> None:
    print("SMT-lite Demon Recruitment 1.0 beta")
    print("Negocia con demonios usando alineamiento y rapport.")

def read_difficulty() -> int:
    """
    Ask the user for a difficulty level (1..5). Clamp and return an int.
    """
    while True:
        raw = input("Elige nivel de dificultad (1-5): ").strip()
        if raw.isdigit():
            lvl = int(raw)
            return max(1, min(5, lvl))
        print("Entrada inválida. Intenta con un número entre 1 y 5.")

def choose_demon(demons: list[Demon], rng: Optional[random.Random] = None) -> Demon:
    r = rng or random
    available = [d for d in demons if getattr(d, "available", True)] or demons[:]
    return r.choice(available)

def print_dex_card(d: "Demon", show_portrait: bool = True, color: bool = True) -> None:
    # Header fields (robust against missing attrs)
    dex_no = getattr(d, "dex_no", None)
    rarity = getattr(d, "rarity", "COMMON")
    rarity_txt = _rarity_label(rarity, color)
    perso = getattr(d, "personality", None)
    perso_txt = perso.name if isinstance(perso, Enum) else str(perso)

    lc = d.alignment.law_chaos
    ld = d.alignment.light_dark

    # Resolve portrait path (may be None)
    portrait_path = None
    if show_portrait:
        try:
            from assets_manifest import get_portrait_path  # adjust import to your layout
            portrait_path = get_portrait_path(d)
        except Exception:
            portrait_path = None

    # Layout
    width = max(60, min(90, get_terminal_size((80, 20)).columns))
    hr = "─" * (width - 2)

    title_left = f"{d.name}"
    title_right = f"#{dex_no}" if isinstance(dex_no, int) else ""
    title = title_left if not title_right else f"{title_left}  {title_right}"

    # Wrap description
    desc = getattr(d, "description", "") or ""
    wrapped_desc = textwrap.wrap(desc, width=width - 4) if desc else []

    # Print card
    print(f"╭{hr}╮")
    print("│ " + _style(title, "1", color).ljust(width - 3) + "│")  # bold name
    print("│ " + f"Rarity: {rarity_txt}".ljust(width - 3) + "│")
    print("│ " + f"Personality: {perso_txt}".ljust(width - 3) + "│")
    print("│ " + f"Alignment (LC/LD): ({lc}, {ld})".ljust(width - 3) + "│")
    stats_line = f"Patience: {d.patience}  |  Tolerance: {d.tolerance}  |  Rapport needed: {d.rapport_needed}"
    print("│ " + stats_line.ljust(width - 3) + "│")

    if portrait_path:
        print("│ " + f"Portrait: {portrait_path}".ljust(width - 3) + "│")

    if wrapped_desc:
        print("│ " + "Description:".ljust(width - 3) + "│")
        for line in wrapped_desc:
            print("│ " + line.ljust(width - 3) + "│")

    print(f"╰{hr}╯")

def run_game_loop(session: NegotiationSession, diff_level: int, demons_catalog: list[Demon]) -> None:
    """
    Core loop: show status, run menu, apply actions, check join/leave,
    apply difficulty pressure, and advance rounds until the session ends.
    """
    # Optional: if you loaded ROUND_DELAY_SEC from config, use it; else fallback
    try:
        delay = ROUND_DELAY_SEC
    except NameError:
        delay = 0  # or 3 if you want a default pause


    try:

        while session.in_progress:
            print(f"\nEsta es la ronda número {session.round_no}.")
            session.show_status()

            whim = session.maybe_trigger_whim()
            if whim:
                decision = run_special_event(session, whim)
                session.process_event(whim, decision)

            opcion = show_menu(session)           # returns "1".."5" or "0" if ended
            if opcion == "0":
                break

            dispatch_action(session, opcion, demons_catalog)

            # Per your spec, check both conditions after actions:
            session.check_union()
            session.check_fled()

            # Optional pause
            if delay > 0:
                time.sleep(delay)

            # Difficulty pressure
            session.difficulty(diff_level)

            # Advance round
            session.round_no += 1

            # autosave at end of round
            save_game(SAVE_PATH, session.player, demons_catalog, session)           
    
    except (KeyboardInterrupt, EOFError):
        # Smooth exit: stop the session and mark as fled
        print("\n[!] Interrupted by user. Ending negotiation softly…")
        save_game(SAVE_PATH, session.player, demons_catalog, session)
        session.in_progress = False
        session.fled = True

def summarize_session(session: NegotiationSession) -> None:
    """
    Print a final summary: alignments, distance, outcome, rounds, and roster.
    """
    # Finalization according to flags
    if session.recruited:
        session.finish_union()
    elif session.fled:
        session.finish_fled()

    # Summary data
    core = session.player.core_alignment
    stance = session.player.stance_alignment
    dist = stance.manhattan_distance(session.demon.alignment)
    roster_names = [d.name for d in session.player.roster]

    print("\n===== Session Summary =====")
    print(f"Player core LC/LD:   ({core.law_chaos}, {core.light_dark})")
    print(f"Player stance LC/LD: ({stance.law_chaos}, {stance.light_dark})")
    print(f"Demon: {session.demon.name} | Final distance: {dist}")
    print(f"Outcome: {'Recruited' if session.recruited else 'Fled' if session.fled else 'Ended'}")
    print(f"Rounds played: {session.round_no - 1}")
    print(f"Roster: {', '.join(roster_names) if roster_names else '(empty)'}")

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


def bootstrap_session(demons_catalog:list["Demon"], questions_pool: list["Question"],
                      rng: "random.Random") -> "NegotiationSession":
    if os.path.exists(SAVE_PATH):
        ans = input("Found a save. Load it? (y/n): ").strip().lower()
        if ans == "y":
            player, sess = load_game(SAVE_PATH, demons_catalog, questions_pool, rng)
            if sess:
                return sess
            # if no active session in save, start a new negotiation
            current_demon = choose_demon(demons_catalog, rng)  # (optionally bias to available-only)
            return NegotiationSession(player=player, demon=current_demon, question_pool=questions_pool, rng=rng)

    # New game
    player = Player(core_alignment=Alignment(0, 0))
    player.gold = 0
    player.inventory = {}
    current_demon = choose_demon(demons_catalog, rng)
    return NegotiationSession(player=player, demon=current_demon, question_pool=questions_pool, rng=rng)

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

