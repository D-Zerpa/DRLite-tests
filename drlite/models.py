from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Set

from drlite.config import AXIS_MIN, AXIS_MAX


class Personality(Enum):
    PLAYFUL = "PLAYFUL"
    CHILDISH = "CHILDISH"
    MOODY = "MOODY"
    CUNNING = "CUNNING"
    PROUD = "PROUD"

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
    choices: Dict[str, Effect]
    tags: List[str]

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
    name: str
    alignment: Alignment
    personality: Personality
    patience: int = 4
    tolerance: int = 3
    rapport_needed: int = 2
    available: bool = field(default=True, repr=False, compare=False)


    def react(self, effect) -> tuple[int, int]:
        """
        Compute the demon's reaction to the chosen option.

        PHASE A (prototype): only forward the rapport change defined by the option.
        Do NOT modify tolerance or any demon/session state here.
        PHASE B (actual): base dRapport + personality tag-based bonus (from JSON). Tolerance unchanged.
        Parameters
        ----------
        effect : dict or object with attribute 'dRapport'
            The effect payload from the chosen option, e.g.:
            {"dLC": int, "dLD": int, "dRapport": int, ...}
            In this phase we only care about 'dRapport'.

        Returns
        -------
        (delta_rapport, delta_tolerance) : tuple[int, int]
        """

        # Base dRapport

        try:
            base = effect.get("dRapport", 0)
        except AttributeError:
            base = getattr(effect, "dRapport", 0)
        if not isinstance(base, (int, float)):
            raise TypeError("dRapport must be numeric (int or float).")
        base = int(base)

        # Tags (prefer effect-level; you can also merge question-level tags in ask())
        tags = effect.get("tags", []) if isinstance(effect, dict) else getattr(effect, "tags", [])
        if not isinstance(tags, list):
            tags = [tags]
        tags = [str(t).lower() for t in tags]

        # Lookup weights from the loaded registry
        weights = PERSONALITY_TAG_WEIGHTS.get(self.personality, {})
        bonus = 0
        for t in tags:
            bonus += int(weights.get(t, 0))

        delta_rapport = clamp(base + bonus, -2, 2)
        return delta_rapport, 0


@dataclass(slots=True, eq=False)
class Player:
    core_alignment: Alignment
    stance_alignment: Alignment = field(init=False)
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
        for attr in ("law_chaos", "light_dark"):
            s = getattr(self.stance_alignment, attr)
            c = getattr(self.core_alignment, attr)

            # Direction: -1, 0, or +1
            direction = 0 if s == c else (1 if c > s else -1)

            delta = direction * min(step, abs(c - s))
            setattr(self.stance_alignment, attr, s + delta)

        self.stance_alignment.clamp()

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


"""
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

"""