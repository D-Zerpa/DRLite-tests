# main.py
from __future__ import annotations
import random

from drlite.config import load_config, RNG_SEED
from drlite.data.loaders import load_demons, load_questions, load_personality_weights, load_personality_cues, load_item_catalog, load_events, load_whims
from drlite.assets.manifest import load_assets_manifest
from drlite.data.validators import validate_questions_against_items, validate_event_refs, validate_events_against_items
from drlite.ui.console import print_banner, read_difficulty
from drlite.ui.gameplay import run_game_loop, handle_end_game
from drlite.models import Player, Alignment 
from drlite.persistence.io import save_game, load_game_raw, rehydrate_game_state
from drlite.engine.session import NegotiationSession


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

    validate_event_refs(questions_pool, events_reg)
    validate_questions_against_items(questions_pool, items_cat)
    validate_events_against_items(events_reg, items_cat)


    # === LOAD / NEW GAME LOGIC ===
    user_id = "local_player" 
    
    raw_save = load_game_raw(user_id)
    player = None

    if raw_save:
        print(f"Partida encontrada para {user_id}. Cargando...")
        try:
            player = rehydrate_game_state(raw_save, Player, demons_catalog)
        except Exception as e:
            print(f"Error rehidratando partida: {e}. Se creará una nueva.")
            player = None

    if player is None:
        print("Iniciando nueva partida...")
        player = Player(core_alignment=Alignment(0,0))
        save_game(user_id, player, demons_catalog)

    diff = read_difficulty()

    # === GAME LOOP ===
    
    # 1. Verify Availability 
    available_demons = [d for d in demons_catalog if d.available]
    if not available_demons:
        print("\n¡Felicidades! Has reclutado a todos los demonios disponibles.")
        return

    # 2. Choose demon
    demon = rng.choice(available_demons)

    # 3. Run Loop
    session = NegotiationSession(player=player, demon=demon, question_pool=questions_pool, rng=rng)
    run_game_loop(session, diff, demons_catalog, weights=p_weights, whims=whim_templates, cues=p_cues, events_registry=events_reg, whim_config=whim_config)
    handle_end_game(session)

if __name__ == "__main__":
    main()
