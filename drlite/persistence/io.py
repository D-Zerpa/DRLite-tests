import json
import os
from enum import Enum
from typing import Any, Dict, Optional, List

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
    1. Writes to a temp file (.tmp).
    2. Flushes to disk.
    3. Renames .tmp to .json (atomic replacement).
    
    This prevents data corruption if the bot crashes during write operations.
    """
    final_path = get_save_path(user_id)
    temp_path = f"{final_path}.tmp"
    
    # Prepare data structure
    data = {
        "version": 2,
        "player": player,
        # Only save world availability state to avoid duplication
        "world_availability": {d.id: d.available for d in demons_catalog},
        "stats": {
            "session_active": session.in_progress if session else False,
            # Add extra metrics here if needed
        }
    }

    try:
        # Step 1: Write to temp file
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, cls=DRLiteEncoder)
            f.flush()            # Force write to buffer
            os.fsync(f.fileno()) # Force write to physical disk

        # Step 2: Atomic replacement
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

def load_game_raw(user_id: str | int) -> Optional[Dict[str, Any]]:
    """Loads the raw JSON dictionary from disk."""
    path = get_save_path(user_id)
    if not os.path.exists(path):
        return None
        
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"[System] WARNING: Corrupt save file for {user_id}. File will be ignored.")
        return None
    except Exception as e:
        print(f"[System] I/O Error reading save {path}: {e}")
        return None

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

