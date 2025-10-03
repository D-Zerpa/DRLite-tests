from __future__ import annotations

from typing import List, Dict, Optional, Tuple, TYPE_CHECKING
from datetime import datetime
import os, json, tempfile, random

from drlite.models import Player, Demon, Alignment, Question
from drlite.persistence.types import (
    SaveAlignment, SaveGame, SavePlayer, SaveWorld, SaveSession, SaveDex
)

# IMPORTANT: do NOT import NegotiationSession here to avoid circular import.
# If you want type checking support:
if TYPE_CHECKING:
    from drlite.engine.session import NegotiationSession

SAVE_VERSION = 2

def demon_id(d: Demon) -> str:
    return d.id

def build_demon_index(demons: List[Demon]) -> Dict[str, Demon]:
    return {d.id: d for d in demons}

def alignment_to_save(a: Alignment) -> SaveAlignment:
    return {"lc": int(a.law_chaos), "ld": int(a.light_dark)}

def alignment_from_save(d: SaveAlignment) -> Alignment:
    return Alignment(law_chaos=int(d["lc"]), light_dark=int(d["ld"]))

def player_to_save(p: Player) -> SavePlayer:
    return {
        "core":  alignment_to_save(p.core_alignment),
        "stance": alignment_to_save(p.stance_alignment),
        "gold": int(getattr(p, "gold", 0)),
        "inventory": {str(k): int(v) for k, v in getattr(p, "inventory", {}).items()},
        "roster": [demon_id(d) for d in getattr(p, "roster", [])],
    }

def world_to_save(demons: List[Demon]) -> SaveWorld:
    return {
        "demons": {
            demon_id(d): {"available": bool(getattr(d, "available", True))}
            for d in demons
        }
    }

def session_to_save(s: Optional["NegotiationSession"]) -> Optional[SaveSession]:
    if not s:
        return None
    return {
        "in_progress": bool(s.in_progress),
        "demon_id": demon_id(s.demon),
        "rapport": int(s.rapport),
        "turns_left": int(s.turns_left),
        "round_no": int(s.round_no),
        "recruited": bool(s.recruited),
        "fled": bool(s.fled),
    }

def dex_to_save(player: Player) -> Optional[SaveDex]:
    seen = list(getattr(player, "dex_seen", []))
    caught = [demon_id(d) for d in getattr(player, "roster", [])]
    return {"seen": seen, "caught": caught} if (seen or caught) else None

def save_game(path: str, player: Player, demons: List[Demon],
              session: Optional["NegotiationSession"]) -> None:
    data: SaveGame = {
        "version": SAVE_VERSION,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "player": player_to_save(player),
        "world": world_to_save(demons),
        "session": session_to_save(session) if (session and session.in_progress) else None,
        "demondex": dex_to_save(player),
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_save_", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        print(f"[save] Saved to {path}")
    except Exception:
        try: os.remove(tmp)
        except OSError: pass
        raise

def load_game(path: str,
              demons: List[Demon],
              questions_pool: List[Question],
              rng: random.Random) -> tuple[Player, Optional["NegotiationSession"]]:
    """
    Late-import pattern: we import NegotiationSession INSIDE this function
    to avoid a circular import between persistence.io and engine.session.
    """
    with open(path, "r", encoding="utf-8") as f:
        data: SaveGame = json.load(f)

    ver = int(data.get("version", 0))
    if ver != SAVE_VERSION:
        raise ValueError(f"Incompatible save version: {ver} (expected {SAVE_VERSION})")

    # Rebuild player
    sp = data["player"]
    player = Player(core_alignment=alignment_from_save(sp["core"]))
    player.stance_alignment = alignment_from_save(sp["stance"])
    player.gold = int(sp.get("gold", 0))
    player.inventory = {str(k): int(v) for k, v in sp.get("inventory", {}).items()}

    # Apply world availability + roster
    idx = build_demon_index(demons)
    for did, meta in data.get("world", {}).get("demons", {}).items():
        d = idx.get(did)
        if d is not None and hasattr(d, "available"):
            d.available = bool(meta.get("available", True))

    for did in sp.get("roster", []):
        d = idx.get(did)
        if d and d not in player.roster:
            player.roster.append(d)
            if hasattr(d, "available"):
                d.available = False

    sess_data = data.get("session")
    if not sess_data:
        return player, None

    # >>> IMPORT HERE TO BREAK THE CYCLE <<<
    from drlite.engine.session import NegotiationSession

    did = sess_data["demon_id"]
    demon = idx.get(did)
    if demon is None:
        raise KeyError(f"Saved demon '{did}' missing from catalog.")

    sess = NegotiationSession(player=player, demon=demon,
                              question_pool=questions_pool, rng=rng)
    sess.in_progress = bool(sess_data.get("in_progress", True))
    sess.rapport     = int(sess_data.get("rapport", 0))
    sess.turns_left  = int(sess_data.get("turns_left", demon.patience))
    sess.round_no    = int(sess_data.get("round_no", 1))
    sess.recruited   = bool(sess_data.get("recruited", False))
    sess.fled        = bool(sess_data.get("fled", False))
    return player, sess

