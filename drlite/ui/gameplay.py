from __future__ import annotations
from typing import List, Dict, Any

from drlite.models import Demon, ItemEffect
from drlite.engine.session import NegotiationSession
from drlite.persistence.io import save_game

# Import tools from console.py
from drlite.ui.console import (
    clear_screen, 
    print_header, 
    print_rapport_bar, 
    print_dex_card, 
    wait_enter,
    ask_yes_no,
    _style, 
    print_separator
)

# ==============================================================================
#  MENUS (Spanish Text)
# ==============================================================================

def menu_inventory(session: NegotiationSession) -> None:
    """Displays inventory and handles item usage."""
    while True:
        clear_screen()
        print_header(session.player, session.demon)
        print(f"\n{_style('--- INVENTARIO ---', 'BOLD')}\n")
        
        if not session.player.inventory:
            print(" (Vacío)")
            wait_enter("[Enter] Volver")
            return

        # Build list
        item_list = []
        for i, (item_id, qty) in enumerate(session.player.inventory.items()):
            item_def = session.items_catalog.get(item_id)
            if not item_def: continue
            
            # Formatting
            name = _style(item_def.display_name, "WHITE")
            tag = ""
            if item_def.consumable:
                if item_def.effect_type != ItemEffect.NONE:
                    tag = _style(" [USAR]", "GREEN")
                else:
                    tag = _style(" [TRADEO]", "GREY")
            
            print(f" {i+1}. {name} x{qty}{tag}")
            print(f"    {_style(item_def.description, 'GREY')}")
            item_list.append((item_id, item_def))

        print(f" 0. Volver")

        choice = input("\nSelecciona objeto > ").strip()
        if choice == '0': return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(item_list):
                item_id, item_def = item_list[idx]
                
                if not item_def.consumable or item_def.effect_type == ItemEffect.NONE:
                    print(f"\n[Sistema] No puedes usar este objeto ahora.")
                    wait_enter()
                else:
                    used, msg = session.player.use_item(item_id, item_def)
                    color = "GREEN" if used else "RED"
                    print(f"\n[Sistema] {_style(msg, color)}")
                    wait_enter()
        except ValueError:
            pass

def menu_roster(session: NegotiationSession) -> None:
    """Displays Compendium."""
    while True:
        clear_screen()
        print(f"\n{_style('--- COMPENDIO DE DEMONIOS ---', 'BOLD')}\n")
        
        if not session.player.roster:
            print(" (Aún no has reclutado a nadie)")
            wait_enter()
            return

        # List Names
        for i, d in enumerate(session.player.roster):
            print(f" {i+1}. {d.name}")
        
        print("\n 0. Volver")
        
        choice = input("\nVer Detalles > ").strip()
        if choice == '0': return
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(session.player.roster):
                # Show the Card
                clear_screen()
                selected_demon = session.player.roster[idx]
                print_dex_card(selected_demon)
                wait_enter()
        except ValueError:
            pass

def menu_help() -> None:
    clear_screen()
    print(_style("--- AYUDA ---", "BOLD"))
    print("1. HABLAR: Elige respuestas que coincidan con la personalidad del Demonio.")
    print("2. OBJETO: Usa objetos para curar HP/MP.")
    print("3. SOBORNAR: Paga Macca para saltar la charla. (Chance depende de Rareza).")
    print("4. HUIR: Escapa del combate (Puedes recibir daño).")
    wait_enter()

# ==============================================================================
#  GAME FLOW
# ==============================================================================

def run_pre_negotiation(session: NegotiationSession) -> bool:
    """Lobby Phase."""
    while True:
        clear_screen()
        print_separator("=")
        print(f" ¡Un {_style(session.demon.name, 'RED')} Salvaje apareció!".center(70))
        print_separator("=")
        
        print_header(session.player, None)
        
        print("\n[ FASE DE PREPARACIÓN ]")
        print(" 1. LUCHAR (Iniciar Negociación)")
        print(" 2. INVENTARIO")
        print(" 3. COMPENDIO")
        print(" 4. AYUDA")

        choice = input("\n> ").strip()
        if choice == '1': return True
        elif choice == '2': menu_inventory(session)
        elif choice == '3': menu_roster(session)
        elif choice == '4': menu_help()

def run_game_loop(
    session: NegotiationSession, 
    difficulty: str,
    demons_catalog: List[Demon],
    weights: Dict,
    whims: List,
    cues: Dict,
    events_registry: Dict,
    whim_config: Dict):

    # 1. Lobby
    if not run_pre_negotiation(session): return

    # 2. Logic Helpers (Callbacks for Engine)
    
    def cb_pay(amount: int, current: int) -> bool:
        print(f" [Pide: {amount} Macca | Tienes: {current}]")
        return ask_yes_no("¿Pagar la cantidad?")

    def cb_give(item_id: str, qty: int, current: int) -> bool:
        print(f" [Pide: {qty}x {item_id} | Tienes: {current}]")
        return ask_yes_no("¿Entregar objeto?")
    
    # 3. Main Loop
    while session.in_progress:
        clear_screen()
        print_header(session.player, session.demon, session.round_no, session.max_rounds)
        print_rapport_bar(session.rapport, session.demon.rapport_needed)

        # --- EVENT TRIGGER (Whims) ---
        if session.rng.random() < whim_config.get("base_chance", 0.1):
            whim_id = session.trigger_whim(whims, whim_config)
            if whim_id:
                res = session.process_event(
                    {"id": whim_id}, 
                    ask_yes_no, 
                    cb_pay,     
                    cb_give     
                )
                print(f"\n> {res.message}")
                wait_enter()
                
                session.check_union()
                if not session.in_progress: break
                continue

        # --- MENU ---
        print(f"\n{_style('[ ACCIONES ]', 'BOLD')}")
        print(" 1. HABLAR")
        print(" 2. OBJETO")
        print(" 3. SOBORNAR")
        print(" 4. HUIR")
        
        action = input("\n> ").strip()

        if action == '1': # TALK
            q = session.pick_question()
            if not q:
                print(f"\n[{session.demon.name}] Se me acabaron las preguntas...")
                session.turns_left = 0
                session.check_union()
                break

            print(f"\n[{_style(session.demon.name, 'RED')}]: {q.text}")
            
            # Print Options
            print("")
            valid_opts = []
            for i, (txt, _) in enumerate(q.responses):
                print(f" {i+1}) {txt}")
                valid_opts.append(str(i+1))
            
            # Answer
            ans_idx = -1
            while True:
                sel = input("\nRespuesta > ").strip()
                if sel in valid_opts:
                    ans_idx = int(sel) - 1
                    break
            
            feedback = session.process_answer(q, ans_idx, cues, weights)
            
            # Feedback Tone Translation
            tone_es = feedback.tone
            tone_color = "WHITE"
            if feedback.tone == "HAPPY": 
                tone_es = "FELIZ"
                tone_color = "GREEN"
            elif feedback.tone == "ANGRY": 
                tone_es = "ENFADADO"
                tone_color = "RED"
            elif feedback.tone == "INTERESTED":
                tone_es = "INTERESADO"
                tone_color = "YELLOW"
            elif feedback.tone == "BORED":
                tone_es = "ABURRIDO"
                tone_color = "BLUE"
            
            print(f"\n> ¡Parece {_style(tone_es, tone_color)}!")
            wait_enter()
            session.check_union()

        elif action == '2': # ITEM
            menu_inventory(session)

        elif action == '3': # BRIBE
            msg = session.attempt_bribe()
            # Assuming msg comes in English from engine, you might want to wrap translation there or here.
            # For now, printing system msg directly.
            print(f"\n[Sistema] {msg}")
            wait_enter()
            session.check_union()

        elif action == '4': # FLEE
            msg = session.attempt_flee()
            print(f"\n[Sistema] {msg}")
            wait_enter()

    # 4. End
    safe_uid = "".join(x for x in session.player.name if x.isalnum() or x in "_").lower()
    if not safe_uid: safe_uid = "player"
    handle_end_game(session, safe_uid, demons_catalog)

# In drlite/ui/gameplay.py

def handle_end_game(session: NegotiationSession, user_id: str, demons_catalog: List[Demon]):
    # 1. APPLY DEATH PENALTY (If applicable) BEFORE SAVING
    if session.player.hp <= 0:
        penalty_res = session.player.apply_death_penalty()
        
        # We print the death logic here so it appears before the "Session Ended" screen
        clear_screen()
        print_header(session.player, session.demon)
        print(f"\n{_style('=== HAS MUERTO ===', 'RED')}")
        
        if penalty_res == "LEVEL_DOWN":
            print(f"\n[Sanción] Tu alma ha sido reconstruida, pero a un costo.")
            print(f"Has bajado al Nivel {session.player.lvl}.")
        else: # GAME_OVER
            print(f"\n[Game Over] Apenas lograste escapar con vida.")
            print("Tu experiencia acumulada se ha perdido.")
        
        wait_enter()

    # 2. SAVE GAME
    save_game(user_id, session.player, demons_catalog, session)

    # 3. SHOW SUMMARY
    clear_screen()
    print_header(session.player, session.demon)
    print("\n" + "="*40)
    print(" SESIÓN FINALIZADA ".center(40, " "))
    print("="*40)
    
    if session.recruited:
        print(f"\n{_style('¡VICTORIA!', 'GREEN')} {session.demon.name} se unió a ti.")
    elif session.fled:
        print(f"\n{_style('ESCAPASTE', 'YELLOW')} de la negociación.")
    elif not session.in_progress and session.turns_left <= 0:
        print(f"\n{_style('FALLO', 'RED')} Se acabó el tiempo.")
    elif session.player.hp <= 0:
        print(f"\n{_style('DERROTA', 'RED')} (Penalización aplicada).")

    wait_enter("Presiona Enter para volver al título...")