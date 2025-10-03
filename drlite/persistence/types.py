from typing import TypedDict, Dict, List, Optional


class SaveAlignment(TypedDict):
    lc: int
    ld: int

class SavePlayer(TypedDict):
    core: SaveAlignment
    stance: SaveAlignment
    gold: int
    inventory: Dict[str, int]     # item_id -> qty
    roster: List[str]             # demon ids

class SaveWorld(TypedDict):
    demons: Dict[str, Dict[str, bool]]  # demon_id -> {"available": bool}

class SaveDex(TypedDict, total=False):
    seen: List[str]
    caught: List[str]

class SaveSession(TypedDict, total=False):
    in_progress: bool
    demon_id: str
    rapport: int
    turns_left: int
    round_no: int
    recruited: bool
    fled: bool

class SaveGame(TypedDict):
    version: int
    timestamp: str
    player: SavePlayer
    world: SaveWorld
    session: Optional[SaveSession]
    demondex: Optional[SaveDex]