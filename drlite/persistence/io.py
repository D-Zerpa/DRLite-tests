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

def get_save_path(user_id: str | int) -> str:
    """Returns the standardized path for the user's save file."""
    os.makedirs("saves", exist_ok=True)
    return f"saves/user_{user_id}.json"

def save_game(user_id: str | int, player: Any, demons_catalog: list, session=None) -> bool:
    """
    Saves the game state ATOMICALLY.
    
    CRITICAL FIX: Explicitly converts the Player dataclass to a dictionary
    using `asdict`. This prevents the JSON serializer from writing the 
    player object as a string string "Player(...)", which causes 
    loading errors later.
    """
    # Ensure we have the path (assuming this function exists in your scope)
    final_path = get_save_path(user_id)
    temp_path = f"{final_path}.tmp"
    
    # 1. Convert Player Dataclass to Dictionary
    if is_dataclass(player):
        player_data = asdict(player)
    elif isinstance(player, dict):
        player_data = player
    else:
        # Fallback: try to get __dict__ or convert to string (last resort)
        player_data = getattr(player, "__dict__", str(player))

    # 2. Extract World State (Demon Availability)
    # We only save the availability boolean to save space
    world_data = {d.id: d.available for d in demons_catalog}

    # 3. Construct the Final Data Structure
    data = {
        "version": 2,
        "player": player_data,  # This is now a clean Dictionary
        "world_availability": world_data,
        "stats": {
            "session_active": session.in_progress if session else False,
        }
    }

    try:
        # Step 4: Write to temp file
        with open(temp_path, "w", encoding="utf-8") as f:
            # use default=str to automatically handle Enums (like Personality.UPBEAT)
            # if they are present inside the dictionary
            json.dump(data, f, indent=2, default=str)
            
            f.flush()            # Force write to buffer
            os.fsync(f.fileno()) # Force write to physical disk

        # Step 5: Atomic replacement
        os.replace(temp_path, final_path)
        print(f"[System] Atomic save successful for user: {user_id}")
        return True

    except Exception as e:
        print(f"[System] CRITICAL ERROR saving {user_id}: {e}")
        # Cleanup temp file if it exists
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return False

def load_game(user_id: str | int, demons_catalog: List[Demon]) -> Tuple[Player, List[Demon]]:
    """
    Loads the game state and reconstructs the Player object with RPG stats.
    Re-links roster IDs to actual Demon objects from the catalog.
    """
    path = get_save_path(user_id)
    
    # If no save exists, return a fresh player
    if not os.path.exists(path):
        print(f"[System] No save found for {user_id}. Creating new.")
        return Player(), demons_catalog

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        p_data = data.get("player", {})

        # --- 1. Reconstruct Alignments ---
        # Helper to convert dict back to Alignment object
        def parse_align(d: dict) -> Alignment:
            if not d: return Alignment(0, 0)
            return Alignment(int(d.get("law_chaos", 0)), int(d.get("light_dark", 0)))

        core_align = parse_align(p_data.get("core_alignment", {}))
        stance_align = parse_align(p_data.get("stance_alignment", {}))

        # --- 2. Reconstruct Roster ---
        # Convert saved IDs back into references to the Demon objects in memory
        roster_objs = []
        raw_roster = p_data.get("roster", [])
        
        for item in raw_roster:
            # Handle if roster is saved as a list of dicts or list of IDs
            d_id = item.get("id") if isinstance(item, dict) else item
            
            # Find the matching demon in the master catalog
            found_demon = next((d for d in demons_catalog if d.id == d_id), None)
            if found_demon:
                roster_objs.append(found_demon)

        # --- 3. Instantiate Player ---
        player = Player(
            name=str(p_data.get("name", "Nahobino")),
            
            # RPG Stats
            lvl=int(p_data.get("lvl", 1)),
            exp=int(p_data.get("exp", 0)),
            exp_next=int(p_data.get("exp_next", 100)),
            
            hp=int(p_data.get("hp", 50)),
            max_hp=int(p_data.get("max_hp", 50)),
            mp=int(p_data.get("mp", 20)),
            max_mp=int(p_data.get("max_mp", 20)),
            
            # Economy & Inventory
            gold=int(p_data.get("gold", 0)),
            inventory=p_data.get("inventory", {}),
            
            # Objects
            core_alignment=core_align,
            stance_alignment=stance_align,
            roster=roster_objs
        )

        print(f"[System] Save loaded. {player.name} Lv.{player.lvl} (HP {player.hp}/{player.max_hp})")
        return player, demons_catalog

    except Exception as e:
        print(f"[System] Error loading save for {user_id}: {e}")
        return Player(), demons_catalog

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

