from __future__ import annotations
from typing import List
import random

from drlite.models import Demon
from drlite.engine.session import NegotiationSession

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

def ask_yes_no(prompt: str) -> bool:
    while True:
        ans = input(f"{prompt} [y/n]: ").strip().lower()
        if ans in ("y","yes"): return True
        if ans in ("n","no"):  return False
        print("Please answer y/n.")

def ask_pay(amount: int, player_gold: int) -> bool:
    print(f"The demon requests {amount} gold. You have {player_gold}.")
    return ask_yes_no("Do you want to pay?")

def ask_give_item(item_id: str, amount: int, have: int) -> bool:
    print(f"The demon asks for {amount}x {item_id}. You have {have}.")
    return ask_yes_no("Do you want to give it?")