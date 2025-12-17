from __future__ import annotations
from typing import List, Optional
import time

from drlite.models import Demon
from drlite.engine.session import NegotiationSession
from drlite.persistence.io import save_game
from drlite.config import ROUND_DELAY_SEC

# Import UI components from console (which handles the visual layer)
from drlite.ui.console import (
    show_menu, 
    dispatch_action, 
    ask_yes_no, 
    ask_pay, 
    ask_give_item, 
    clear_screen, 
    rapport_gauge
)

def run_game_loop(
    session: NegotiationSession, 
    diff_level: int, 
    demons_catalog: list[Demon],
    user_id: str,
    weights: dict,
    whims: list,
    cues: dict,
    events_registry: dict,
    whim_config: dict) -> None:
    """
    Main synchronous game loop for the CLI.
    
    Orchestrates the flow:
    1. Render UI (Clear screen + Status)
    2. Check for Whims (Random events)
    3. Show Menu & Dispatch Action
    4. Validate Logic (Union, Fled, Time)
    5. Auto-save
    """
    
    # Apply difficulty settings to the session constraints
    session.difficulty(diff_level)
    
    # Determine delay for pacing
    try:
        delay = ROUND_DELAY_SEC
    except NameError:
        delay = 0

    try:
        while session.in_progress:
            # --- 1. UI REFRESH ---
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
            
            # --- 2. WHIMS (Random Events) ---
            # Check if the demon wants something before the main action
            whim_payload = session.maybe_trigger_whim(whims, whim_config)
            
            if whim_payload:
                print("\n[!] ¡El demonio quiere algo antes de continuar!")
                # Pass UI callbacks so the engine can ask the user questions
                result = session.process_event(
                    whim_payload,
                    ask_yes_no=ask_yes_no,
                    ask_pay=ask_pay,
                    ask_give_item=ask_give_item
                )
                
                # Feedback from the event
                if result.message:
                    print(f">> {result.message}")
                    input("(Presiona Enter...)")
                
                # If the event ended the session (e.g., fatal trap), break immediately
                if not session.in_progress:
                    break

            # --- 3. MENU / ACTION ---
            option = show_menu(session)
            
            if option == "0":
                # Fallback exit
                break 

            # Dispatch the chosen option (1=Talk, 2=Flee, 3=Analyze)
            # We pass all injected data catalogs to the dispatch function
            dispatch_action(session, option, demons_catalog, weights, cues, events_registry)

            # --- 4. POST-TURN CHECKS ---
            # Check if recruitment conditions are met
            session.check_union()
            
            # If the game ended in this turn, stop the loop
            if not session.in_progress:
                break
            
            # Advance round counter
            session.round_no += 1
            
            # Optional pacing delay
            if delay > 0:
                time.sleep(delay)
            
            # Autosave state for safety (persists items/gold changes)
            save_game(user_id, session.player, demons_catalog, session)

    except (KeyboardInterrupt, EOFError):
        print("\n\n[Sistema] Juego interrumpido por el usuario.")
        session.in_progress = False
        # Save on exit
        save_game(user_id, session.player, demons_catalog, session)

    # === END OF SESSION SUMMARY ===
    handle_end_game(session, user_id, demons_catalog)

def handle_end_game(session: NegotiationSession, user_id: str, demons_catalog: list[Demon]) -> None:
    """
    Displays the final result screen, prints stats summary, and performs the final save.
    Replaces the old 'summarize_session' logic.
    """
    clear_screen()
    print("=== FIN DE LA NEGOCIACIÓN ===\n")
    
    outcome_msg = ""

    player = session.player
    
    if session.recruited:
        if player.has_demon(session.demon.id):
            pass
        else:
            print(f"\n¡ÉXITO! {session.demon.name} se ha unido a tu equipo!")
            player.roster.append(session.demon)
        
        # 2. Add to Player Roster (Memory)
        # Check duplicates just in case, though session.check_union handles logic
        # We ensure we append the object, not just the ID, for consistency
        already_in_roster = any(d.id == session.demon.id for d in session.player.roster)
        if not already_in_roster:
            session.player.roster.append(session.demon)
        
    elif session.fled:
        outcome_msg = "HUIDA"
        print("Huiste de la negociación.")
        
    else:
        outcome_msg = "FRACASO"
        # Failed negotiation (Rapport too low or turns run out)
        print(f"{session.demon.name} se ha marchado.")
        print("No lograste convencerle a tiempo.")
    
    # --- 3. Final Save (Disk) ---
    # We save regardless of outcome to persist inventory changes, turn usage, etc.
    save_game(user_id, session.player, demons_catalog, None)
    
    # --- 4. Print Statistics (Restored functionality) ---
    print("\n" + "="*30)
    print(" RESUMEN DE SESIÓN")
    print("="*30)
    
    # Alignment Stats
    core = session.player.core_alignment
    stance = session.player.stance_alignment
    demon_align = session.demon.alignment
    final_dist = stance.manhattan_distance(demon_align)
    
    print(f"Resultado:       {outcome_msg}")
    print(f"Rapport Final:   {session.rapport}")
    print(f"Distancia Final: {final_dist}")
    print(f"Rondas jugadas:  {session.round_no}")
    print("-" * 30)
    print(f"Tu Alineación Base:    ({core.law_chaos}, {core.light_dark})")
    print(f"Tu Postura (Stance):   ({stance.law_chaos}, {stance.light_dark})")
    print(f"Alineación de {session.demon.name}: ({demon_align.law_chaos}, {demon_align.light_dark})")
    
    # Optional: Print current roster count
    print(f"Demonios en equipo:    {len(session.player.roster)}")
    print("\n")