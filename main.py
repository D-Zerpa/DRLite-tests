# main.py
from __future__ import annotations
import random

from drlite.config import load_config, RNG_SEED
from drlite.data.loaders import load_demons, load_questions, load_personality_weights, load_personality_cues, load_item_catalog, load_events, load_whims
from drlite.assets.manifest import load_assets_manifest, validate_portraits
from drlite.data.validators import validate_questions_against_items, validate_event_refs, validate_events_against_items
from drlite.ui.console import print_banner, read_difficulty
from drlite.ui.gameplay import bootstrap_session, run_game_loop, summarize_session

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
    validate_portraits(demons_catalog, strict=False)

    diff = read_difficulty()
    session = bootstrap_session(demons_catalog, questions_pool, rng)
    run_game_loop(session, diff, demons_catalog, weights=p_weights, whims=whim_templates, cues=p_cues, events_registry=events_reg, whim_config=whim_config)
    summarize_session(session)

if __name__ == "__main__":
    main()
