from __future__ import annotations
import random
import re
from drlite.config import load_config, RNG_SEED
from drlite.data.loaders import (
    load_demons, load_questions, load_personality_weights, 
    load_personality_cues, load_item_catalog, load_events, load_whims
)
from drlite.assets.manifest import load_assets_manifest
from drlite.ui.console import print_banner, read_difficulty
from drlite.ui.gameplay import run_game_loop 
from drlite.persistence.io import load_game, save_game 
from drlite.engine.session import NegotiationSession

# --- HELPER: INPUT USER ---
def ask_player_identity() -> tuple[str, str]:
    print("\n" + "="*40)
    print(" BIENVENIDO AL MUNDO DE LAS SOMBRAS ".center(40, " "))
    print("="*40)
    print("\n[Sistema] Identifícate para acceder a tu Registro.")
    
    while True:
        raw_name = input("Nombre de Usuario > ").strip()
        if not raw_name:
            continue
            
        safe_id = re.sub(r'[^a-zA-Z0-9]', '_', raw_name).lower()
        safe_id = re.sub(r'_+', '_', safe_id)
        
        if len(safe_id) < 1:
            print("Nombre inválido.")
            continue
            
        return safe_id, raw_name

def main() -> None:
    print_banner()
    load_config("config.json")
    rng = random.Random(RNG_SEED) if RNG_SEED is not None else random.Random()

    # 1. LOAD DATA
    print("[Sistema] Cargando recursos...")
    p_weights = load_personality_weights("data/personality_weights.json")
    p_cues = load_personality_cues("data/personality_cues.json")
    items_cat = load_item_catalog("data/items.json")
    events_reg= load_events("data/events.json")
    whim_config, whim_templates = load_whims("data/whims.json")
    load_assets_manifest("assets_manifest.json")
    demons_catalog = load_demons("data/demons.json")
    questions_pool = load_questions("data/questions.json")

    # 2. LOGIN
    user_id, display_name = ask_player_identity()
    player, demons_catalog = load_game(user_id, demons_catalog)

    # New User Check
    if player.exp == 0 and player.lvl == 1 and not player.roster:
        print(f"\n[Sistema] Creando nuevo registro para: {display_name}...")
        player.name = display_name
        save_game(user_id, player, demons_catalog)
    else:
        print(f"\n[Sistema] Registro cargado. Bienvenido, {player.name}.")

    # 3. PRE-GAME CHECKS
    diff = read_difficulty()

    if player.mp <= 0:
        print("\n[Sistema] Estás exhausto (0 MP). Debes descansar.")
        return
    
    if not demons_catalog:
        print("[Error] No hay demonios cargados en el sistema.")
        return

    # 4. START SESSION
    demon_template = rng.choice(demons_catalog)

    session = NegotiationSession(
        player=player, 
        demon=demon_template, 
        question_pool=questions_pool, 
        items_catalog=items_cat, 
        rng=rng, 
        events_registry=events_reg
    )
    
    # 5. RUN LOOP
    run_game_loop(
        session, 
        diff, 
        demons_catalog, 
        weights=p_weights, 
        whims=whim_templates, 
        cues=p_cues, 
        events_registry=events_reg, 
        whim_config=whim_config
    )

if __name__ == "__main__":
    main()
