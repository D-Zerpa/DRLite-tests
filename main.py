from __future__ import annotations
import random
import re  # <--- NUEVO: Para limpiar el nombre de archivo
import os

from drlite.config import load_config, RNG_SEED
from drlite.data.loaders import load_demons, load_questions, load_personality_weights, load_personality_cues, load_item_catalog, load_events, load_whims
from drlite.assets.manifest import load_assets_manifest
from drlite.ui.console import print_banner, read_difficulty
from drlite.ui.gameplay import run_game_loop, handle_end_game
from drlite.models import Player, Alignment 
from drlite.persistence.io import save_game, load_game
from drlite.engine.session import NegotiationSession

def ask_player_identity() -> tuple[str, str]:
    """
    Pide el nombre al usuario.
    Retorna una tupla: (ID_ARCHIVO, NOMBRE_MOSTRAR)
    Ejemplo: Input "  Dante Sparda  " -> ("dante_sparda", "Dante Sparda")
    """
    print("\n" + "="*40)
    print(" BIENVENIDO AL MUNDO DE LAS SOMBRAS ".center(40, " "))
    print("="*40)
    print("\n[Sistema] Identifícate para acceder a tu Registro.")
    
    while True:
        raw_name = input("Nombre de Usuario > ").strip()
        
        if not raw_name:
            print("Debes escribir un nombre.")
            continue
            
        # 1. Create a safe-to-save name, being careful with special characters
        safe_id = re.sub(r'[^a-zA-Z0-9]', '_', raw_name).lower()
        # Just in case, delete the double "_"
        safe_id = re.sub(r'_+', '_', safe_id)
        
        if len(safe_id) < 1:
            print("Ese nombre contiene caracteres inválidos para crear un archivo. Intenta otro.")
            continue
            
        return safe_id, raw_name

def main() -> None:
    print_banner()
    load_config("config.json")
    rng = random.Random(RNG_SEED) if RNG_SEED is not None else random.Random()

    p_weights = load_personality_weights("data/personality_weights.json")
    p_cues = load_personality_cues("data/personality_cues.json")
    items_cat = load_item_catalog("data/items.json")
    events_reg= load_events("data/events.json")
    whim_config, whim_templates = load_whims("data/whims.json")
    load_assets_manifest("assets_manifest.json")

    demons_catalog = load_demons("data/demons.json")
    questions_pool = load_questions("data/questions.json")


    # === LOAD / NEW GAME LOGIC ===
    user_id, display_name = ask_player_identity()
    
    player, demons_catalog = load_game(user_id, demons_catalog)

    #If it's a new player, we create the save.
    if player.exp == 0 and player.lvl == 1 and not player.roster:
        print(f"\n[Sistema] Creando nuevo registro para: {display_name}...")
        
        # We assign the name given by the user
        player.name = display_name
        
        # Save game to create the .json
        save_game(user_id, player, demons_catalog)
    else:
        print(f"\n[Sistema] Registro encontrado. Bienvenido de nuevo, {player.name}.")

    diff = read_difficulty()

    # === GAME LOOP ===

    if player.mp <= 0:
        print("\n[Sistema] Estás exhausto (0 MP).")
        print("No tienes energía espiritual para negociar con demonios.")
        return
    
    # 1. Verify Availability 
    available_demons = [d for d in demons_catalog if d.available]

    if not available_demons:
        print("[System] No hay demonios disponibles.")
        return

    # 2. Choose demon
    demon = rng.choice(available_demons)

    # 3. Run Loop
    session = NegotiationSession(player=player, demon=demon, question_pool=questions_pool, items_catalog= items_cat, rng=rng, events_registry = events_reg)
    run_game_loop(session, diff, demons_catalog, user_id= user_id, weights=p_weights, whims=whim_templates, cues=p_cues, events_registry=events_reg, whim_config=whim_config)

    # PostGame punishment to dead user
    if player.hp <= 0:
        print("\n" + "="*40)
        print(" HAS MUERTO ".center(40, "="))
        print("="*40)
        
        result = player.apply_death_penalty()
        
        if result == "LEVEL_DOWN":
            print(f"\n[Sanción] Has revivido, pero tu alma se ha debilitado.")
            print(f"Nivel reducido a: {player.lvl}")
        else:
            print(f"\n[Game Over] Apenas lograste escapar con vida.")
            print("Tu experiencia se ha perdido.")
        
        handle_end_game(session, user_id, demons_catalog)

if __name__ == "__main__":
    main()
