import json
import os
from enum import Enum
from typing import Any, Dict, Optional, List, Tuple
from dataclasses import asdict, is_dataclass
from drlite.models import Player, Alignment, Demon, Personality, Rarity

# ==============================================================================
#  Robust JSON Encoder
# ==============================================================================

class DRLiteEncoder(json.JSONEncoder):
    """
    Custom encoder to serialize complex objects (Enums, Classes, Sets)
    into native JSON types.
    """
    def default(self, obj: Any) -> Any:
        # 1. Enums -> String (e.g., Personality.CUNNING -> "CUNNING")
        if isinstance(obj, Enum):
            return obj.name
        
        # 2. Sets -> List (JSON does not support sets)
        if isinstance(obj, set):
            return list(obj)
            
        # 3. Objects with __dict__ -> Dictionary
        if hasattr(obj, "__dict__"):
            return obj.__dict__
            
        try:
            return super().default(obj)
        except TypeError:
            # Final fallback: string representation
            return str(obj)

# ==============================================================================
#  Atomic I/O System (Safe Save)
# ==============================================================================

def get_save_path(user_id: str) -> str:
    """Returns the absolute path for the save file."""
    # Ensure directory exists
    folder = os.path.join("data", "saves")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{user_id}.json")

def save_game(user_id: str, player: Player, demons_catalog: list, session=None):
    """
    Saves the player state to JSON.
    """
    path = get_save_path(user_id)
    
    # 1. Serialize Roster (Save IDs only)
    roster_ids = [d.id for d in player.roster]

    # 2. Serialize Alignments
    core_align = {
        "law_chaos": player.core_alignment.law_chaos,
        "light_dark": player.core_alignment.light_dark
    }
    stance_align = {
        "law_chaos": player.stance_alignment.law_chaos,
        "light_dark": player.stance_alignment.light_dark
    }

    # 3. Data Structure
    data = {
        "user_id": user_id,
        "player": {
            "name": player.name,
            "lvl": player.lvl,
            "exp": player.exp,
            "exp_next": player.exp_next,
            "hp": player.hp,
            "max_hp": player.max_hp,
            "mp": player.mp,
            "max_mp": player.max_mp,
            "gold": player.gold,
            "inventory": player.inventory, # Dict {id: qty} is serializable
            "core_alignment": core_align,
            "stance_alignment": stance_align,
            "roster": roster_ids
        }
    }

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        # DEBUG: Imprimimos la ruta absoluta para que sepas dónde está
        abs_path = os.path.abspath(path)
        print(f"\n[Sistema] Partida guardada correctamente en:\n -> {abs_path}")
    except Exception as e:
        print(f"[Error] No se pudo guardar la partida: {e}")

def load_game(user_id: str, demons_catalog: List[Demon]) -> Tuple[Player, List[Demon]]:
    """
    Loads player data. If no save exists, returns a NEW Player.
    Reconstructs Roster objects from IDs using the Catalog.
    """
    path = get_save_path(user_id)

    if not os.path.exists(path):
        # New Game
        return Player(name=user_id), demons_catalog

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        p_data = data["player"]
        
        # 1. Reconstruct Alignments
        c_al = p_data.get("core_alignment", {})
        s_al = p_data.get("stance_alignment", {})
        
        core_obj = Alignment(c_al.get("law_chaos", 0), c_al.get("light_dark", 0))
        stance_obj = Alignment(s_al.get("law_chaos", 0), s_al.get("light_dark", 0))

        # 2. Reconstruct Roster (ID -> Demon Object)
        roster_objs = []
        saved_ids = p_data.get("roster", [])
        
        # Map catalog for speed
        catalog_map = {d.id: d for d in demons_catalog}
        
        for d_id in saved_ids:
            if d_id in catalog_map:
                # IMPORTANT: In a real game, you might clone this object 
                # to track individual HP/MP. For Lite, reference is fine.
                roster_objs.append(catalog_map[d_id])
        
        # 3. Create Player
        player = Player(
            name=p_data.get("name", user_id),
            lvl=p_data.get("lvl", 1),
            exp=p_data.get("exp", 0),
            exp_next=p_data.get("exp_next", 100),
            hp=p_data.get("hp", 50),
            max_hp=p_data.get("max_hp", 50),
            mp=p_data.get("mp", 20),
            max_mp=p_data.get("max_mp", 20),
            gold=p_data.get("gold", 0),
            inventory=p_data.get("inventory", {}),
            roster=roster_objs,
            core_alignment=core_obj,
            stance_alignment=stance_obj
        )
        
        return player, demons_catalog

    except Exception as e:
        print(f"[Error] Save file corrupt or incompatible ({e}). Starting new game.")
        return Player(name=user_id), demons_catalog

# ==============================================================================
#  Rehydration Logic (Data -> Objects Translator)
# ==============================================================================

def rehydrate_game_state(raw_data: Dict[str, Any], player_class: Any, demons_catalog: list) -> Any:
    """
    Converts raw data back into live objects, with safety checks.
    
    Args:
        raw_data: The dictionary loaded from JSON.
        player_class: The Player class type (injected to avoid circular imports).
        demons_catalog: The master list of loaded Demon objects.
    """
    version = raw_data.get('version', '?')
    print(f"[System] Rehydrating state (v{version})...")
    
    # 1. Restore World Availability
    world_avail = raw_data.get("world_availability", {})
    if world_avail:
        for demon in demons_catalog:
            # Keys in JSON are always strings
            if demon.id in world_avail:
                demon.available = world_avail[demon.id]

    # 2. Reconstruct Player
    p_data = raw_data.get("player", {})
    player = player_class() # Create fresh instance
    
    # Restore simple properties (with safe defaults)
    player.gold = int(p_data.get("gold", 0))
    
    # Restore and Sanitize Inventory
    # Ensure keys are strings and values are ints > 0
    raw_inv = p_data.get("inventory", {})
    clean_inv = {}
    for k, v in raw_inv.items():
        try:
            qty = int(v)
            if qty > 0:
                clean_inv[str(k)] = qty
        except (ValueError, TypeError):
            continue
    player.inventory = clean_inv

    # 3. Reconstruct Alignment (Defensive)
    # Helper to handle legacy formats (list) vs new formats (dict)
    def _extract_align(source, key):
        val = source.get(key)
        if isinstance(val, dict):
            return int(val.get("law_chaos", 0)), int(val.get("light_dark", 0))
        # Fallback for old saves if any
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            return int(val[0]), int(val[1])
        return 0, 0

    # Core Alignment
    lc, ld = _extract_align(p_data, "core")
    if hasattr(player, "core_alignment"):
        player.core_alignment.law_chaos = lc
        player.core_alignment.light_dark = ld

    # Stance Alignment
    lc, ld = _extract_align(p_data, "stance")
    if hasattr(player, "stance_alignment"):
        player.stance_alignment.law_chaos = lc
        player.stance_alignment.light_dark = ld
        
    # 4. Reconstruct Roster (CRITICAL: Map IDs to Real Objects)
    raw_roster = p_data.get("roster", [])
    player.roster = []
    
    loaded_ids = set() # Track to avoid duplicates
    
    for entry in raw_roster:
        # entry might be the serialized dict or just the ID string
        d_id = entry.get("id") if isinstance(entry, dict) else str(entry)
        
        if d_id in loaded_ids:
            continue # Skip duplicates
            
        # Find the REAL object in the memory catalog
        # We do not create new Demon objects; we reference existing ones.
        found = next((d for d in demons_catalog if d.id == d_id), None)
        
        if found:
            player.roster.append(found)
            loaded_ids.add(d_id)
        else:
            print(f"[Warning] Demon '{d_id}' found in save file but missing from catalog.")

    return player

