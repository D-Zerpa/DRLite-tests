import json
import os
from typing import List, Dict, Any, Tuple
from drlite.data.types import ItemDef
from drlite.models import (
    Demon, Question, Rarity, 
    Alignment, Personality, ItemEffect
)

def load_json(path: str) -> Any:
    if not os.path.exists(path):
        print(f"[Warning] File not found: {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[Error] Failed to parse JSON {path}: {e}")
        return {}

# ==============================================================================
#  DEMONS
# ==============================================================================

def load_demons(path: str) -> List[Demon]:
    data = load_json(path)
    if not isinstance(data, list):
        if isinstance(data, dict):
            data = list(data.values())
        else:
            print(f"[Error] demons.json must be a list. Loaded empty.")
            return []

    demons = []
    for d_data in data:
        try:
            # Parse Rarity Enum safely (Handle lowercase inputs like "common")
            r_str = d_data.get("rarity", "COMMON").upper()
            rarity = getattr(Rarity, r_str, Rarity.COMMON)

            # Parse Personality Enum safely (Handle "PLAYFUL" etc.)
            p_str = d_data.get("personality", "DEFAULT").upper()
            personality = getattr(Personality, p_str, Personality.DEFAULT)

            # Parse Alignment
            align_data = d_data.get("alignment", {})
            alignment = Alignment(
                law_chaos=align_data.get("law_chaos", 0),
                light_dark=align_data.get("light_dark", 0)
            )

            demon = Demon(
                id=d_data["id"],
                dex_no=d_data.get("dex_no", 0),
                name=d_data["name"],
                aliases=d_data.get("aliases", []),
                rarity=rarity,
                description=d_data.get("description", "A mysterious demon."),
                personality=personality,
                alignment=alignment,
                patience=d_data.get("patience", 5),
                tolerance=d_data.get("tolerance", 3),
                rapport_needed=d_data.get("rapport_needed", 30),
                sprite_source=d_data.get("sprite_source", ""),
                sprite_key=d_data.get("sprite_key", "")
            )
            demons.append(demon)
        except Exception as e:
            print(f"[Error] Skipping demon {d_data.get('name', 'Unknown')}: {e}")
    
    print(f"[Demons] Loaded {len(demons)} demons.")
    return demons

# ==============================================================================
#  QUESTIONS
# ==============================================================================

def load_questions(path: str) -> List[Question]:
    """
    Loads questions from a JSON Dictionary or List.
    Structure: { "q_id": { "text": "...", "choices": {...} } }
    """
    data = load_json(path)
    questions = []

    raw_list = []
    if isinstance(data, dict):
        raw_list = list(data.values())
    elif isinstance(data, list):
        raw_list = data
    else:
        print("[Error] questions.json must be a dict or list.")
        return []

    for q_data in raw_list:
        try:
            responses = []
            raw_choices = q_data.get("choices", {})
            
            # Convert choice dict to list of tuples
            for choice_text, choice_stats in raw_choices.items():
                responses.append((choice_text, choice_stats))

            q = Question(
                id=q_data.get("id", "unknown"),
                text=q_data["text"],
                responses=responses,
                tags=q_data.get("tags", [])
            )
            questions.append(q)
        except Exception as e:
            print(f"[Error] Skipping question {q_data.get('id')}: {e}")

    print(f"[Questions] Loaded {len(questions)} questions.")
    return questions

# ==============================================================================
#  ITEMS
# ==============================================================================

def load_item_catalog(path: str) -> Dict[str, ItemDef]:
    data = load_json(path)
    catalog = {}
    
    raw_items = data if isinstance(data, dict) else {i["id"]: i for i in data}

    for item_id, i_data in raw_items.items():
        try:
            r_str = i_data.get("rarity", "COMMON").upper()
            rarity = getattr(Rarity, r_str, Rarity.COMMON)
            
            eff_str = i_data.get("effect_type", "NONE").upper()
            eff_type = getattr(ItemEffect, eff_str, ItemEffect.NONE)

            item = ItemDef(
                id=item_id, 
                display_name=i_data.get("display_name", item_id),
                description=i_data.get("description", ""),
                rarity=rarity,
                base_value=i_data.get("value", 10),
                consumable=i_data.get("consumable", False),
                effect_type=eff_type,
                effect_amount=i_data.get("effect_amount", 0)
            )
            catalog[item_id] = item
        except Exception as e:
            print(f"[Error] Skipping item {item_id}: {e}")

    print(f"[Items] Loaded {len(catalog)} items.")
    return catalog

# ==============================================================================
#  EVENTS & CONFIG
# ==============================================================================

def load_events(path: str) -> Dict[str, Any]:
    data = load_json(path)
    if not isinstance(data, dict):
        print("[Error] events.json must be a dictionary.")
        return {}
    print(f"[Events] Loaded {len(data)} event definitions.")
    return data

def load_whims(path: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    data = load_json(path)
    config = data.get("config", {})
    templates = data.get("templates", [])
    print(f"[Whims] Loaded {len(templates)} whim templates.")
    return config, templates

def load_personality_weights(path: str) -> Dict[str, Dict[str, float]]:
    data = load_json(path)
    print(f"[weights] Loaded weights for {len(data)} personalities.")
    return data

def load_personality_cues(path: str) -> Dict[str, List[str]]:
    data = load_json(path)
    total = sum(len(v) for v in data.values())
    print(f"[cues] Loaded {total} cues across {len(data)} personalities.")
    return data