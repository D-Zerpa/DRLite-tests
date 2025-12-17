from __future__ import annotations
from typing import List, Dict, Any
import os
import textwrap
from shutil import get_terminal_size

from drlite.config import RAPPORT_MIN, RAPPORT_MAX
from drlite.models import Demon
# Try to import asset helper, fail silently if missing (safe for CLI)
try:
    from drlite.assets.manifest import get_portrait_path
except ImportError:
    get_portrait_path = lambda d: None

# ==============================================================================
#  System Helpers
# ==============================================================================

def clear_screen() -> None:
    """Clears the terminal screen for a cleaner UI experience."""
    os.system('cls' if os.name == 'nt' else 'clear')

# ==============================================================================
#  Visual Helpers (Styles & Gauges)
# ==============================================================================

def _style(text: str, code: str, enable: bool = True) -> str:
    """Apply ANSI color code."""
    return f"\033[{code}m{text}\033[0m" if enable else text

def _rarity_label(rarity_obj: Any, color: bool = True) -> str:
    """Format rarity with color and translated text."""
    if hasattr(rarity_obj, "value"): 
        key = str(rarity_obj.value).lower()
    else:
        key = str(rarity_obj).lower()

    # Spanish translation map
    trans = {
        "common": "Común",
        "uncommon": "Poco Común",
        "rare": "Raro",
        "epic": "Épico",
        "legendary": "Legendario"
    }
    label = trans.get(key, key.title())

    # Colors
    palette = {
        "common": "37",    # White
        "uncommon": "32",  # Green
        "rare": "34",      # Blue
        "epic": "35",      # Magenta
        "legendary": "33", # Yellow
    }
    return _style(label.upper(), palette.get(key, "37"), color)

def rapport_gauge(val: int, lo: int = RAPPORT_MIN, hi: int = RAPPORT_MAX) -> str:
    """Visual bar for rapport: [··|·#··]"""
    width = hi - lo + 1
    width = max(3, width)
    cells = ["·"] * width

    idx = max(0, min(width - 1, val - lo))
    zero = max(0, min(width - 1, 0 - lo))

    cells[zero] = "|"
    cells[idx] = "#"
    if idx == zero:
        cells[idx] = "X"

    return "[" + "".join(cells) + "]"

def distance_trend(delta: int) -> str:
    """Returns a visual indicator of alignment shift."""
    if delta < 0: return ">>> (Acercándose)"
    if delta > 0: return "<<< (Alejándose)"
    return "--- (Sin cambios)"

def print_dex_card(d: Demon, show_portrait: bool = True, color: bool = True) -> None:
    """Prints a translated, detailed card of the demon."""
    rarity_txt = _rarity_label(getattr(d, "rarity", "COMMON"), color)
    perso = getattr(d, "personality", None)
    perso_txt = perso.name if hasattr(perso, "name") else str(perso)
    
    lc = d.alignment.law_chaos
    ld = d.alignment.light_dark

    try:
        ts = get_terminal_size((80, 20))
        width = max(60, min(90, ts.columns))
    except Exception:
        width = 60
        
    hr = "─" * (width - 2)
    title = f" {d.name} "
    
    print(f"╭{hr}╮")
    print(f"│ {_style(title, '1', color).ljust(width + 4)} │") # +4 heuristic for bold codes
    print(f"│ Rareza: {rarity_txt}".ljust(width + 7) + "│")
    print(f"│ Personalidad: {perso_txt}".ljust(width - 3) + "│")
    print(f"│ Alineación (LC/LD): ({lc}, {ld})".ljust(width - 3) + "│")
    
    stats_line = f"Paciencia: {d.patience} | Tolerancia: {d.tolerance}"
    print(f"│ {stats_line}".ljust(width - 3) + "│")

    if show_portrait:
        path = get_portrait_path(d)
        if path:
            # We just show the path in CLI, in Discord this would be the image attachment
            print(f"│ Imagen: {os.path.basename(path)}".ljust(width - 3) + "│")

    desc = getattr(d, "description", "")
    if desc:
        print(f"│ {'Descripción:'.ljust(width - 4)} │")
        wrapped = textwrap.wrap(desc, width=width - 6)
        for line in wrapped:
            print(f"│   {line}".ljust(width - 3) + "│")

    print(f"╰{hr}╯")

# ==============================================================================
#  Interaction Callbacks (Spanish)
# ==============================================================================

def ask_yes_no(prompt: str) -> bool:
    """Generic Yes/No prompt in Spanish."""
    while True:
        ans = input(f"{prompt} (s/n): ").strip().lower()
        if ans in ("s", "si", "sí", "y", "yes"): return True
        if ans in ("n", "no"):  return False
        print(">> Por favor responde 's' (sí) o 'n' (no).")

def ask_pay(amount: int, current_gold: int) -> bool:
    """Callback for 'ask_gold' event."""
    print(f"\n[Evento] El demonio te pide {amount} macca. (Tienes: {current_gold})")
    return ask_yes_no("¿Aceptas pagar?")

def ask_give_item(item_id: str, amount: int, have: int) -> bool:
    """Callback for 'ask_item' event."""
    display_name = item_id.replace("_", " ").title()
    print(f"\n[Evento] Te piden {amount}x {display_name}. (Tienes: {have})")
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
    clear_screen()
    if option == "1":
        clear_screen()
        p = session.player
        print(f"--- RONDA {session.round_no} | {p.name} Lv.{p.lvl} ---")
        print(f"HP: {p.hp}/{p.max_hp}  |  MP: {p.mp}/{p.max_mp}  |  Macca: {p.gold}")
        print(f"XP: {p.exp}/{p.exp_next}")
        print("-" * 40 + "\n")
        
        # Status Bar
        # We use the visual gauge for rapport
        print(f"Turnos: {session.turns_left} | Rapport: {rapport_gauge(session.rapport)}")
        print(f"Demonio: {session.demon.name} (Rara: {session.demon.rarity.name})")
        print("-" * 40)
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

        # Pause to read the reaction
        input("\n(Presiona Enter para continuar...)")

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

        input("\n(Presiona Enter para continuar...)")

    elif option == "3":
        session.show_status()
        input("\n(Presiona Enter para volver al menú...)")
    elif option == "4":
        session.check_union()
        input("\n(Presiona Enter para volver al menú...)")
    elif option == "5":
        session.in_progress = False
        session.fled = True
        print(f"{session.demon.name} se marcha...")
        input("\n(Presiona Enter para continuar...)")
    elif option =="6":
        clear_screen()
        print_dex_card(session.demon)
        input("\n(Presiona Enter para volver al menú...)")
    elif option == "7":
        print("Juego guardado. Saliendo...")
        session.in_progress = False
    else:
        print("OPCION NO VALIDA.")