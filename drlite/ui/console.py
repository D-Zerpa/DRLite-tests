from __future__ import annotations
from typing import List, Dict
import random
import textwrap
from shutil import get_terminal_size
from enum import Enum

from drlite.models import Demon
from drlite.config import RAPPORT_MIN, RAPPORT_MAX
try:
    from drlite.assets.manifest import get_portrait_path
except ImportError:
    get_portrait_path = lambda d: None

# ==============================================================================
#  Visual Helpers (Styles & Gauges)
# ==============================================================================

def _style(text: str, code: str, enable: bool = True) -> str:
    """Apply ANSI color code."""
    return f"\033[{code}m{text}\033[0m" if enable else text

def rapport_gauge(val: int, lo: int = RAPPORT_MIN, hi: int = RAPPORT_MAX) -> str:
    """
    Visual bar for rapport: [··|·#··]
    """
    width = hi - lo + 1
    width = max(3, width)
    cells = ["·"] * width

    idx = max(0, min(width - 1, val - lo))
    zero = max(0, min(width - 1, 0 - lo))

    cells[zero] = "|"
    cells[idx] = "#"
    if idx == zero:
        cells[idx] = "X" # Overlap

    return "[" + "".join(cells) + "]"

def distance_trend(delta: int) -> str:
    if delta < 0: return ">>> (Acercándose)"
    if delta > 0: return "<<< (Alejándose)"
    return "---"

def _rarity_label(rarity_obj: Any, color: bool = True) -> str:
    """
    Format rarity with color.
    """
    # Handle Enum or string
    if hasattr(rarity_obj, "value"): 
        key = str(rarity_obj.value).lower()
        raw = str(rarity_obj.value).upper()
    else:
        key = str(rarity_obj).lower()
        raw = str(rarity_obj).upper()

    # Color theme per rarity
    palette = {
        "common":    "37",   # gray
        "uncommon":  "32",   # green
        "rare":      "34",   # blue
        "epic":      "35",   # magenta
        "legendary": "33",   # yellow
    }
    return _style(raw, palette.get(key, "37"), color)

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

# ==============================================================================
#  Interaction Callbacks (Injected into Session)
# ==============================================================================

def ask_yes_no(prompt: str) -> bool:
    """Generic Yes/No prompt."""
    while True:
        ans = input(f"{prompt} (y/n): ").strip().lower()
        if ans in ("y", "yes", "s", "si"): return True
        if ans in ("n", "no"):  return False
        print("Por favor responde 'y' o 'n'.")

def ask_pay(amount: int, current_gold: int) -> bool:
    """
    Callback for 'ask_gold' event.
    """
    print(f"\n[Evento] Te piden {amount} monedas. (Tienes: {current_gold})")
    if current_gold < amount:
        print("No tienes suficiente dinero.")
        return False
    return ask_yes_no("¿Aceptas pagar?")

def ask_give_item(item_id: str, amount: int, have: int) -> bool:
    """
    Callback for 'ask_item' event.
    """

    display_name = item_id.replace("_", " ").title()
    
    print(f"\n[Evento] Te piden {amount}x {display_name}. (Tienes: {have})")
    if have < amount:
        print("No tienes suficientes ítems.")
        return False
    return ask_yes_no(f"¿Entregar {amount}x {display_name}?")


# ==============================================================================
#  Menus & Dispatch
# ==============================================================================

def print_banner() -> None:
    print("========================================")
    print(" SMT NEGOTIATION SIMULATOR (CLI) v1.0")
    print("========================================")

def read_difficulty() -> int:
    while True:
        raw = input("\nElige dificultad (1-5) [Default 3]: ").strip()
        if not raw: return 3
        if raw.isdigit() and 1 <= int(raw) <= 5:
            return int(raw)
        print("Inválido.")

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
    print("6) Mostrar el DemonDex")
    print("7) Guardar y salir")  
    valid = {"1","2","3","4","5","6","7"}
    while True:
        choice = input("Elige una opción (1-6): ").strip()
        if choice in valid:
            return choice
        print("OPCION NO VALIDA. Intenta de nuevo.")


def dispatch_action(session, option: str, demons_catalog: list[Demon], weights: Dict[str, Dict[str, int]],cues: Dict[str, Dict[str, str]], events_registry: Dict[str, Any]) -> None:
    """
    Dispatch the selected option to the corresponding session action.
    Follows your spec strictly.
    """
    if option == "1":
        effect = session.ask(events_registry)
        feedback = session.process_answer(effect, weights, cues)

        # Show reaction feedback (console layer)
        print(f"{session.demon.name} parece {feedback.tone.lower()}. {feedback.cue}")

        # Optional hints (only print if non-empty)
        info_parts = []
        if feedback.liked_tags: info_parts.append(f"Le gustó: {', '.join(feedback.liked_tags)}")
        if feedback.disliked_tags: info_parts.append(f"Odió: {', '.join(feedback.disliked_tags)}")
        if info_parts:
            print(f"({'; '.join(info_parts)})")

        # Intuitive indicators

        print(f"  Afinidad (Rapport): {rapport_gauge(session.rapport)}")
        print(f"  Distancia: {distance_trend(feedback.delta_distance)}")

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
    elif option =="6":
        print_dex_card(session.demon)
    elif option == "7":
        print("Game saved. Exiting…")
        session.in_progress = False
    else:
        print("OPCION NO VALIDA.")