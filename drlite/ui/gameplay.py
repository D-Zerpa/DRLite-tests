from __future__ import annotations
from typing import List, Optional
import random, time, os

from drlite.models import Demon, Player, Alignment, Question
from drlite.engine.session import NegotiationSession
from drlite.config import SAVE_PATH, ROUND_DELAY_SEC
from drlite.persistence.io import save_game, load_game
from drlite.ui.console import show_menu


def choose_demon(demons: list[Demon], rng: Optional[random.Random] = None) -> Demon:
    r = rng or random
    available = [d for d in demons if getattr(d, "available", True)] or demons[:]
    return r.choice(available)

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