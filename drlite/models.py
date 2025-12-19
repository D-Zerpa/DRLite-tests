from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Set, Any, Optional
from drlite.utils import canonical_item_id

from drlite.config import AXIS_MIN, AXIS_MAX


class Personality(Enum):
    UPBEAT = auto()
    TIMID = auto()
    IRRITABLE = auto()  
    GLOOMY = auto()
    CUNNING = auto()    
    KIND = auto()
    AGGRESSIVE = auto()
    PLAYFUL = auto()
    PROUD = auto()
    # Fallback
    DEFAULT = auto()

class Rarity(Enum):
    COMMON = auto()
    UNCOMMON = auto()
    RARE = auto()
    EPIC = auto()
    LEGENDARY = auto()

class ItemEffect(Enum):
    NONE = auto()
    HEAL_HP = auto()
    HEAL_MP = auto()
    FULL_RESTORE = auto()
    CURE_AILMENT = auto() # For future implementations
    REVIVE = auto() # For future implementations


@dataclass(slots=True)
class Alignment:
    """Aligment axis: LC (Law/Chaos), LD (Light/Dak)"""
    law_chaos: int = 0
    light_dark: int = 0

    def clamp(self) -> None:
        """ Adjusts the values to the ranges """
        self.law_chaos  = max(AXIS_MIN, min(AXIS_MAX, self.law_chaos))
        self.light_dark = max(AXIS_MIN, min(AXIS_MAX, self.light_dark))

    def manhattan_distance(self, other: "Alignment") -> int:
        """ Compare with other alignments to make decisions """
        return abs(self.law_chaos - other.law_chaos) + abs(self.light_dark - other.light_dark)

@dataclass(slots=True)
class Question:
    """Loads the Question from the .json and transforms it into an object"""
    id: str
    text: str
    # Format: List[Tuple[ResponseText, StatsDict]]
    responses: List[Tuple[str, Dict[str, Any]]] 
    tags: List[str] = field(default_factory=list)

@dataclass(slots=True)
class ReactionFeedback:
    """Outcome summary to present to the UI layer (no prints here)."""
    tone: str                 # "Delighted", "Pleased", "Neutral", "Annoyed", "Enraged"
    cue: str                  # short cue like "*giggles*" or emoji
    delta_rapport: int        # clamped per-turn change actually applied
    delta_distance: int       # stance→demon Manhattan distance change (negative = closer)
    liked_tags: List[str]     # tags that matched positive weights
    disliked_tags: List[str]  # tags that matched negative weights
    notes: List[str]          # extra notes (e.g. “Not enough gold.”)

@dataclass(eq= False, slots = True)
class Demon:

    id: str
    dex_no: int             
    name: str
    aliases: List[str]       
    rarity: Rarity
    description: str         
    personality: Personality
    alignment: Alignment
    patience: int            
    tolerance: int          
    rapport_needed: int
    sprite_source: str = "" 
    sprite_key: str = ""


@dataclass(slots=True, eq=False)
class Player:

    # Progress
    name: str = "Nahobino"
    lvl: int = 1
    exp: int = 0
    exp_next: int = 100

    # HP/MP
    hp: int = 50
    max_hp: int = 50
    mp: int = 20
    max_mp: int = 20

    # Economy and Alignment
    core_alignment: Alignment = field(default_factory=lambda: Alignment(0, 0))
    stance_alignment: Alignment = field(default_factory=lambda: Alignment(0, 0))
    roster: List[Demon] = field(default_factory=list)
    gold: int = 10
    inventory: Dict[str, int] = field(default_factory= dict)

    def __post_init__(self) -> None:
        self.stance_alignment = Alignment(
            law_chaos=self.core_alignment.law_chaos,
            light_dark=self.core_alignment.light_dark)

    def relax_posture(self, step: int = 1):
        """
        Move stance 1 step per axis toward core, then clamp.
        """
        cx, cy = self.core_alignment.law_chaos, self.core_alignment.light_dark
        sx, sy = self.stance_alignment.law_chaos, self.stance_alignment.light_dark

        if sx < cx: sx += 1
        elif sx > cx: sx -= 1
        
        if sy < cy: sy += 1
        elif sy > cy: sy -= 1
        
        self.stance_alignment.law_chaos = sx
        self.stance_alignment.light_dark = sy

    def add_item(self, name: str, qty: int = 1) -> None:
        """Add items to the inventory using canonical IDs."""
        iid = canonical_item_id(name)
        if not iid:
            return
        self.inventory[iid] = self.inventory.get(iid, 0) + max(0, int(qty))

    def has_item(self, name: str, qty: int = 1) -> bool:
        """Check if the player has at least `qty` of the item."""
        iid = canonical_item_id(name)
        return self.inventory.get(iid, 0) >= max(1, int(qty))

    def remove_item(self, name: str, qty: int = 1) -> bool:
        """Consume items if available; return True if removed."""
        iid = canonical_item_id(name)
        need = max(1, int(qty))
        have = self.inventory.get(iid, 0)
        if have < need:
            return False
        newq = have - need
        if newq > 0:
            self.inventory[iid] = newq
        else:
            self.inventory.pop(iid, None)
        return True

    def count_item(self, item_id: str) -> int:
        """Return current quantity for item_id."""
        return self.inventory.get(item_id, 0)

    def has_demon(self, demon_id: str) -> bool:
        """
        Checks if a specific demon ID is already in the player's roster.
        """
        for d in self.roster:
            if d.id == demon_id:
                return True
        return False

    def change_gold(self, amount: int) -> int:
        """Modifica el oro del jugador. No permite negativos."""
        self.gold += amount
        if self.gold < 0: self.gold = 0
        return self.gold

    def change_hp(self, amount: int) -> int:
        """Modify HP, returns new HP"""
        self.hp += amount
        if self.hp > self.max_hp: self.hp = self.max_hp
        # No capeamos a 0 aquí para detectar la muerte fuera
        return self.hp

    def change_mp(self, amount: int) -> int:
        """Modify MP, returns new MP"""
        self.mp += amount
        if self.mp < 0: self.mp = 0
        if self.mp > self.max_mp: self.mp = self.max_mp
        return self.mp

    def gain_exp(self, amount: int) -> bool:
        """
        Exp gain, returns true if LvlUP.
        """
        self.exp += amount
        if self.exp >= self.exp_next:
            self._level_up()
            return True
        return False

    def _level_up(self):
        """Grows and reset HP/MP."""
        self.lvl += 1
        self.exp -= self.exp_next
        
        # Simple EXP curve (lvl*100)
        self.exp_next = self.lvl * 100
        
        # Stats increment
        self.max_hp += 15
        self.max_mp += 5
        
        # Post-Lvlup Healing
        self.hp = self.max_hp
        self.mp = self.max_mp


    def apply_death_penalty(self) -> str:
        """
        Death Logic:
        - Si Lvl > 1: Baja 1 nivel, resetea stats al nuevo max.
        - Si Lvl == 1: Game Over real (o reset de XP).
        """
        if self.lvl > 1:
            self.lvl -= 1
            # Stats down
            self.max_hp -= 15
            self.max_mp -= 5
            # Reset EXP
            self.exp = 0 
            self.exp_next = self.lvl * 100
            # Ress
            self.hp = self.max_hp
            self.mp = self.max_mp
            return "LEVEL_DOWN"
        else:
            # Lvl1 Death
            self.hp = self.max_hp # You're born again
            self.exp = 0
            return "GAME_OVER"

    def use_item(self, item_id: str, item_def: ItemDef) -> Tuple[bool, str]:
        """
        Attempts to use an item. 
        Returns (Success, Feedback Message).
        """
        # 1. Check possession
        if not self.has_item(item_id, 1):
            return False, "You don't have that item."

        # 2. Apply Effect
        msg = ""
        used = False

        if item_def.effect_type == ItemEffect.HEAL_HP:
            if self.hp >= self.max_hp:
                return False, "Your HP is already full."
            old_hp = self.hp
            self.change_hp(item_def.effect_amount)
            recovered = self.hp - old_hp
            msg = f"Recovered {recovered} HP."
            used = True

        elif item_def.effect_type == ItemEffect.HEAL_MP:
            if self.mp >= self.max_mp:
                return False, "Your MP is already full."
            old_mp = self.mp
            self.change_mp(item_def.effect_amount)
            recovered = self.mp - old_mp
            msg = f"Recovered {recovered} MP."
            used = True

        elif item_def.effect_type == ItemEffect.FULL_RESTORE:
            if self.hp >= self.max_hp and self.mp >= self.max_mp:
                return False, "Tu salud y energía ya están al máximo."

            self.hp = self.max_hp
            self.mp = self.max_mp
            msg = "¡Tu HP y MP han sido totalmente restaurados!"
            used = True
            
        elif item_def.effect_type == ItemEffect.NONE:
            msg = "This item cannot be used here."
            used = False

        # 3. Consume
        if used and item_def.consumable:
            self.remove_item(item_id, 1)

        return used, msg

@dataclass
class EventResult:
    applied: bool
    message: str = ""
    delta_rapport: int = 0
    consumed_gold: int = 0
    consumed_items: Dict[str, int] = field(default_factory=dict)
    join_now: bool = False      # e.g., pay-to-join
    fled_now: bool = False      # e.g., trap caused flee

@dataclass
class WhimResult:
    triggered: bool
    message: str = ""
    delta_rapport: int = 0
    delta_turns: int = 0

    def pretty_inventory(self) -> str:
        """Return a human-readable inventory string using display names."""
        if not self.inventory:
            return "(empty)"
        parts = []
        for iid, qty in self.inventory.items():
            meta = ITEM_CATALOG.get(iid, {})
            name = meta.get("display_name", iid.title())
            parts.append(f"{qty}x {name}")
        return ", ".join(parts)