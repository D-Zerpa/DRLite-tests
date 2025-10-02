"""
SMT-lite: Demon Recruitment.
Description: 
    - Light mini game to simulate the Demon Recruitment system on SMT. 
    - Made to be implemented in Cognitas Discord Bot.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, TypedDict, Set, Final, Any, Literal, NotRequired
from enum import Enum
import os, json, tempfile
import random
import time

# ====== Global registry and Defaults ======
RAPPORT_MIN, RAPPORT_MAX = -3, 3
AXIS_MIN, AXIS_MAX       = -5, 5
TOL_MIN, TOL_MAX         = 1, 5
RNG_SEED                 = None
ROUND_DELAY_SEC          = 0
PERSONALITY_TAG_WEIGHTS: dict[Personality, dict[str, int]] = {}
ITEM_CATALOG: Dict[str, ItemDef] = {}
EVENTS_REGISTRY: Dict[str, EventPayload] = {}
WHIMS_CONFIG: Dict[str, Any] = {}
WHIM_TEMPLATES: List[EventPayload] = []
PERSONALITY_CUES_BY_NAME: Dict[str, Dict[str, str]] = {}
SAVE_PATH = "saves/slot1.json"

# =========================
# OOP Models
# =========================

class Personality(Enum):
    PLAYFUL = "PLAYFUL"
    CHILDISH = "CHILDISH"
    MOODY = "MOODY"
    CUNNING = "CUNNING"
    PROUD = "PROUD"


class EventPayload(TypedDict, total=False):
    type: Literal["ask_gold", "ask_item", "trap", "whim"]
    # Common:
    message: NotRequired[str]

    # ask_gold:
    amount: NotRequired[int]
    pay_rapport: NotRequired[int]
    refuse_rapport: NotRequired[int]
    flee_on_refuse: NotRequired[bool]
    join_on_pay: NotRequired[bool]

    # ask_item:
    item: NotRequired[str]
    amount: NotRequired[int]
    consume: NotRequired[bool]
    give_rapport: NotRequired[int]
    decline_rapport: NotRequired[int]
    ammount_range: NotRequired[List[int]]
    join_on_give: NotRequired[int]

    # trap:
    penalty_rapport: NotRequired[int]
    flee_chance: NotRequired[float]

    # whims:
    kind: NotRequired[str]
    only_if_has_item: NotRequired[bool]
    weight: NotRequired[int]

class Effect(TypedDict, total=False):
    dLC: int
    dLD: int
    dRapport: int
    tags: List[str]
    event: EventPayload
    event_ref: str

class ItemDef(TypedDict, total=False):
    display_name: str
    rarity: Literal["common", "uncommon", "rare", "epic", "legendary"]
    value: int
    stackable: bool
    description: str

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
   

@dataclass
class NegotiationSession:

    player: Player
    demon: Demon
    question_pool: List[Question]

    # State

    rapport: int = 0 
    turns_left: int = field(init=False)
    in_progress: bool = True
    recruited: bool = False
    fled: bool = False
    round_no: int = 1
    rng: Optional[random.Random] = None
    

    # Avoid repeating questions within the session
    last_feedback: Optional[ReactionFeedback] = field(default=None, repr=False)
    _used_question_ids: Set[str] = field(default_factory = set, repr = False)

    def __post_init__(self):
        """Initialize values that depend on demon at runtime."""
        self.turns_left = self.demon.patience
        
        if self.rng is None:
            try:
                # prefer your config seed if available
                self.rng = random.Random(RNG_SEED) if RNG_SEED is not None else random.Random()
            except NameError:
                self.rng = random.Random()


    def pick_question(self) -> "Question":
        """
        Pick a question for this turn. Minimal version:
        - Prefer questions not used in this session.
        - If none left, reset and use the full pool.
        - Choose randomly.
        """
        candidates = [q for q in self.question_pool if q.id not in self._used_question_ids]
        if not candidates:
            candidates = self.question_pool[:]     # reset
            self._used_question_ids.clear()

        q = self.rng.choice(candidates)
        self._used_question_ids.add(q.id)
        return q

    def ask(self) -> Effect:
        """
        Show a question, collect a valid choice, and return the chosen option's effect.
        Merges question-level tags into the effect so Demon.react() can consider both.
        """
        q = self.pick_question()

        # 1) Print the question and enumerate options
        print(f"\nQ: {q.text}")
        options = list(q.choices.items())  # [(label, effect_dict), ...] (dict preserves insertion order)
        for idx, (label, _) in enumerate(options, start=1):
            print(f"  {idx}) {label}")

        # 2) Get a valid option index
        while True:
            raw = input("Choose an option number: ").strip()  # replace with safe_input(...) if you added it
            if raw.isdigit():
                i = int(raw)
                if 1 <= i <= len(options):
                    _, effect = options[i - 1]

                    # 3) Merge question-level tags into the effect (without mutating the pool)
                    eff_copy = dict(effect)  # shallow copy is enough for our flat dict
                    eff_tags = eff_copy.get("tags", [])
                    if not isinstance(eff_tags, list):
                        eff_tags = [eff_tags]

                    eff_copy = resolve_event_ref(eff_copy)

                    # Normalize to lowercase and deduplicate while preserving order
                    q_tags = q.tags if isinstance(q.tags, list) else [q.tags]
                    merged = list(dict.fromkeys(
                        [*(str(t).lower() for t in eff_tags), *(str(t).lower() for t in q_tags)]
                    ))
                    eff_copy["tags"] = merged

                    return eff_copy

            print("Invalid choice. Try again.")

    def process_event(self, event: EventPayload, decision: Dict[str, Any] | None) -> None:
        """Apply consequences of a special event to session/player."""
        et = str(event.get("type", "")).lower()
        decision = decision or {}

        if et == "ask_gold":
            amount = int(event.get("amount", 0))
            pay = bool(decision.get("pay", False))
            if pay and self.player.gold >= amount:
                self.player.gold -= amount
                self.rapport = min(RAPPORT_MAX, self.rapport + int(event.get("pay_rapport", 0)))
                if event.get("join_on_pay", False):
                    self.recruited = True
                    self.in_progress = False
            else:
                self.rapport = max(RAPPORT_MIN, self.rapport - int(event.get("refuse_rapport", 0)))
                if event.get("flee_on_refuse", False):
                    self.fled = True
                    self.in_progress = False

        elif et == "ask_item":
            iid = canonical_item_id(event.get("item", ""))
            amount = int(event.get("amount", 1))
            consume = bool(event.get("consume", True))
            give = bool(decision.get("give", False))

            if iid not in ITEM_CATALOG:
                print(f"[warn] Unknown item in event: '{iid}'. Treating as decline.")
                give = False

            if give and self.player.has_item(iid, amount):
                if consume:
                    self.player.remove_item(iid, amount)
                self.rapport = min(RAPPORT_MAX, self.rapport + int(event.get("give_rapport", 0)))
                if event.get("join_on_give", False):
                    self.recruited = True
                    self.in_progress = False
            else:
                self.rapport = max(RAPPORT_MIN, self.rapport - int(event.get("decline_rapport", 0)))


        elif et == "trap":
            pen = int(event.get("penalty_rapport", 0))
            self.rapport = max(RAPPORT_MIN, self.rapport - abs(pen))
            p = float(event.get("flee_chance", 0.0))
            if self.rng.random() < p:
                self.fled = True
                self.in_progress = False

        elif et == "whim":
            kind = str(event.get("kind", "")).lower()
            if kind == "ask_gold":
                amount = int(event.get("amount", 1))
                pay = bool(decision.get("pay", False))
                if pay and self.player.gold >= amount:
                    self.player.gold -= amount
                    self.rapport = min(RAPPORT_MAX, self.rapport + int(event.get("pay_rapport", 1)))
                else:
                    self.rapport = max(RAPPORT_MIN, self.rapport - int(event.get("refuse_rapport", 1)))



    def process_answer(self, effect: Dict[str, int]) -> None:
        """
        Apply the chosen effect to stance and session metrics.
        - Update stance (dLC/dLD) and clamp.
        - Ask demon to react (get delta_rapport).
        - Clamp rapport.
        - Decrement turns and relax player's posture.
        - Print a compact summary.
        """
        # Pre-state
        stance = self.player.stance_alignment
        dist_before = stance.manhattan_distance(self.demon.alignment)
        rapport_before = self.rapport

        # 1) Apply stance deltas
        d_lc = int(effect.get("dLC", 0))
        d_ld = int(effect.get("dLD", 0))
        stance.law_chaos += d_lc
        stance.light_dark += d_ld
        stance.clamp()

        # 2) Demon reaction → rapport delta (Phase B uses personality weights)
        d_rep, _ = self.demon.react(effect)
        self.rapport = max(RAPPORT_MIN, min(RAPPORT_MAX, self.rapport + d_rep))

        # 3) Advance turn and relax posture
        self.turns_left -= 1
        self.player.relax_posture()

        # 4) Compute distance change AFTER relaxation (more informative)
        dist_after = stance.manhattan_distance(self.demon.alignment)
        delta_distance = dist_after - dist_before  # negative means closer

        # 5) Build feedback
        tone, default_emoji = _tone_from_delta(d_rep)
        tags = effect.get("tags", []) if isinstance(effect, dict) else getattr(effect, "tags", [])
        if not isinstance(tags, list): tags = [tags]
        tags = [str(t).lower() for t in tags]
        liked, disliked = _split_tag_sentiment(self.demon.personality, tags)

        fb = ReactionFeedback(
            tone=tone,
            cue=_flavor_cue(self.demon.personality, tone, default_emoji),
            delta_rapport=d_rep,
            delta_distance=delta_distance,
            liked_tags=liked,
            disliked_tags=disliked,
            notes=[f"Δ Stance: LC {d_lc:+}, LD {d_ld:+}",
                f"Rapport: {rapport_before} → {self.rapport}",
                f"Distance: {dist_before} → {dist_after} ({delta_distance:+})"]
        )
        self.last_feedback = fb
        return fb



    def show_status(self) -> None:
        """
        Print the current session HUD:
        - round, turns_left, rapport
        - player's stance alignment
        - demon name/alignment and Manhattan distance
        """
        stance = self.player.stance_alignment
        dist = stance.manhattan_distance(self.demon.alignment)
        print(
            f"\n-- Session --\n"
            f"Round: {self.round_no} | Turns left: {self.turns_left} | Rapport: {self.rapport}\n"
            f"Stance LC/LD: ({stance.law_chaos}, {stance.light_dark})\n"
            f"Demon: {self.demon.name} | Demon LC/LD: "
            f"({self.demon.alignment.law_chaos}, {self.demon.alignment.light_dark}) | "
            f"Distance: {dist}"
        )
   
    def difficulty(self, level: int) -> None:
        """
        Light pressure mechanics:
        - Decrease rapport randomly by 0..(nivel//2), not below the minimum.
        - Optionally nudge stance 1 step away from the demon with probability nivel/10.
        Then clamp stance and keep state consistent.
        """
        # 1) Rapport pressure
        drop = self.rng.randint(0, max(0, level // 2))
        self.rapport = max(RAPPORT_MIN, self.rapport - drop)

        # 2) Optional nudge away from the demon (probability nivel/10)
        if self.rng.random() < (level / 10.0):
            axis = self.rng.choice(("law_chaos", "light_dark"))
            s = getattr(self.player.stance_alignment, axis)
            d = getattr(self.demon.alignment, axis)
            # Move 1 step away from the demon along the chosen axis
            if s < d:
                setattr(self.player.stance_alignment, axis, s - 1)
            elif s > d:
                setattr(self.player.stance_alignment, axis, s + 1)
            # If equal, do nothing (already centered relative to demon)
            self.player.stance_alignment.clamp()

    def check_union(self) -> None:
        """
        If distance <= demon.tolerance AND rapport >= demon.rapport_needed,
        mark as recruited and stop the session.
        """
        dist = self.player.stance_alignment.manhattan_distance(self.demon.alignment)
        if dist <= self.demon.tolerance and self.rapport >= self.demon.rapport_needed:
            print(f"{self.demon.name} seems willing to join you.")
            self.recruited = True
            self.in_progress = False

    def check_fled(self) -> None:
        """
        If distance > demon.tolerance + 2 OR turns_left <= 0,
        mark as fled and stop the session.
        """
        dist = self.player.stance_alignment.manhattan_distance(self.demon.alignment)
        if dist > self.demon.tolerance + 2 or self.turns_left <= 0:
            print(f"{self.demon.name} loses interest and leaves.")
            self.fled = True
            self.in_progress = False

    def finish_union(self) -> None:
        """If recruited, add demon to the roster, mark it unavailable, and notify."""
        if self.recruited:
            if self.demon not in self.player.roster:
                self.player.roster.append(self.demon)
            # Match your field name; if you used 'available' in Demon, set that.
            if hasattr(self.demon, "available"):
                self.demon.available = False
            print(f"{self.demon.name} has joined your roster!")

    def maybe_trigger_whim(self) -> Optional[EventPayload]:
        """Use WHIMS_CONFIG/WHIM_TEMPLATES to maybe emit a whim event."""
        if not WHIM_TEMPLATES:
            return None
        base = float(WHIMS_CONFIG.get("base_chance", 0.0))
        mod = WHIMS_CONFIG.get("personality_mod", {})
        base += float(mod.get(self.demon.personality.name, 0.0))
        if self.rng.random() >= max(0.0, min(1.0, base)):
            return None

        # filter by conditions (e.g., only_if_has_item)
        candidates: List[EventPayload] = []
        for e in WHIM_TEMPLATES:
            etype = e.get("type")
            if etype == "ask_item" and e.get("only_if_has_item", False):
                item = canonical_item_id(e.get("item", ""))
                amt = int(e.get("amount", 1))
                if not self.player.has_item(item, amt):
                    continue
            candidates.append(e)

        if not candidates:
            return None

        tmpl = _weighted_choice(self.rng, candidates)
        if not tmpl:
            return None

        # Instantiate ranges (amount_range) into concrete values
        inst = dict(tmpl)
        if "amount_range" in inst and isinstance(inst["amount_range"], list) and len(inst["amount_range"]) == 2:
            lo, hi = int(inst["amount_range"][0]), int(inst["amount_range"][1])
            inst["amount"] = self.rng.randint(min(lo, hi), max(lo, hi))
            inst.pop("amount_range", None)

        # Mark as whim so your process_event path can treat it specially if desired
        inst["type"] = inst.get("type", "whim")
        inst["kind"] = inst.get("type")  # optional
        return inst  # EventPayload 

    def finish_fled(self) -> None:
            """If fled, notify."""
            if self.fled:
                print(f"The negotiation with {self.demon.name} ended. The demon walked away.")

# =========================
# OOP Models (Save state)
# =========================

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

# =========================
# Helpers
# =========================

def _weighted_choice(rng, entries: List[EventPayload]) -> Optional[EventPayload]:
    total = sum(max(0, int(e.get("weight", 1))) for e in entries)
    if total <= 0:
        return None
    pick = rng.uniform(0, total)
    acc = 0.0
    for e in entries:
        w = max(0, int(e.get("weight", 1)))
        acc += w
        if pick <= acc:
            return e
    return None

def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def _ensure_list_of_str(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x) for x in value]
    if value is None:
        return []
    # single string or other → put into a one-element list
    return [str(value)]

def _parse_personality(val: Any) -> Personality:
    if isinstance(val, Personality):
        return val
    if isinstance(val, str):
        key = val.strip().upper()
        try:
            return Personality[key]
        except KeyError:
            # Accept values already like "PLAYFUL" or with proper casing
            for p in Personality:
                if p.value.upper() == key:
                    return p
    raise ValueError(f"Invalid personality value: {val!r}")

def clamp(x: int, lo: int, hi: int) -> int:
    return lo if x < lo else hi if x > hi else x

def canonical_item_id(name: str) -> str:
    """Normalize any item name to a canonical ID (lowercase, stripped)."""
    return str(name).strip().lower()

def resolve_event_ref(effect: Effect) -> Effect:
    """Return a copy of effect with an embedded 'event' if it had 'event_ref'."""
    if not isinstance(effect, dict):
        return effect
    ref = effect.get("event_ref")
    if not ref:
        return effect
    payload = EVENTS_REGISTRY.get(str(ref))
    if not payload:
        print(f"[warn] Unknown event_ref '{ref}'. Ignoring.")
        return effect
    eff = dict(effect)
    eff["event"] = payload  # do NOT delete event_ref; harmless to keep or remove
    return eff

def _flavor_cue(personality: Personality, tone: str, default_emoji: str) -> str:
    return PERSONALITY_CUES_BY_NAME.get(personality, {}).get(tone, default_emoji)

def _split_tag_sentiment(personality: Personality, tags: List[str]) -> tuple[List[str], List[str]]:
    """Classify which tags were liked/disliked based on loaded weights (JSON)."""
    weights = PERSONALITY_TAG_WEIGHTS.get(personality, {})
    liked, disliked = [], []
    for t in tags:
        w = int(weights.get(t, 0))
        if w > 0:  liked.append(t)
        elif w < 0: disliked.append(t)
    return liked, disliked

def rapport_gauge(val: int, lo: int = RAPPORT_MIN, hi: int = RAPPORT_MAX) -> str:
    """
    Text gauge for rapport. Example (min=-3..max=3):
    [··|·#··]  → '|' marks 0; '#' marks current value.
    """
    width = hi - lo + 1
    width = max(3, width)  # safety
    cells = ["·"] * width

    # current index and zero-index (clamped)
    idx = max(0, min(width - 1, val - lo))
    zero = max(0, min(width - 1, 0 - lo))

    cells[zero] = "|"     # zero marker
    cells[idx] = "#"      # current value
    return "[" + "".join(cells) + "]"


def distance_trend(delta: int) -> str:
    """
    Arrow showing how distance changed this turn:
      < 0 → closer; > 0 → farther; 0 → unchanged.
    """
    if delta < 0:
        return "↘ closer"
    if delta > 0:
        return "↗ farther"
    return "→ unchanged"

def flavor_cue(personality: Personality, tone: str, default_emoji: str = "😐") -> str:
    """
    Return a personality-flavored cue string for a given tone.
    Falls back to default_emoji when missing.
    """
    per = PERSONALITY_CUES_BY_NAME.get(personality.name, {})
    return per.get(tone, default_emoji)

def _tone_from_delta(delta_rapport: int) -> tuple[str, str]:
    """Map rapport delta to a tone label and a generic cue emoji."""
    if delta_rapport >= 2:   return ("Delighted", "😄")
    if delta_rapport == 1:   return ("Pleased",   "🙂")
    if delta_rapport == 0:   return ("Neutral",   "😐")
    if delta_rapport == -1:  return ("Annoyed",   "🙁")
    return ("Enraged", "😠")  # delta <= -2


# =========================
# Save/load helpers
# =========================

def player_to_save(p: "Player") -> SavePlayer:
    inv = getattr(p, "inventory", {}) or {}
    return {
        "core":  alignment_to_save(p.core_alignment),
        "stance": alignment_to_save(p.stance_alignment),
        "gold": int(getattr(p, "gold", 0)),
        "inventory": {str(k): int(v) for k, v in inv.items()},
        "roster": [demon_id(d) for d in getattr(p, "roster", [])],
    }

def world_to_save(demons: List["Demon"]) -> SaveWorld:
    return {
        "demons": {demon_id(d): {"available": bool(getattr(d, "available", True))}
                   for d in demons}
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

def dex_to_save(player: "Player") -> Optional[SaveDex]:
    # Placeholder simple: si aún no llevas estos sets, guarda vacío o None
    seen = list(getattr(player, "dex_seen", []))
    caught = [demon_id(d) for d in getattr(player, "roster", [])]
    return {"seen": seen, "caught": caught} if (seen or caught) else None

def save_game(path: str, player: "Player", demons: List["Demon"],
              session: Optional["NegotiationSession"]) -> None:
    data: SaveGame = {
        "version": SAVE_VERSION,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "player": player_to_save(player),
        "world": world_to_save(demons),
        "session": session_to_save(session) if session and session.in_progress else None,
        "demondex": dex_to_save(player),
    }

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_save_", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)  # atomic on same filesystem
        print(f"[save] Saved to {path}")
    except Exception:
        try: os.remove(tmp)
        except OSError: pass
        raise

def load_game(path: str, demons: List["Demon"], questions_pool: List["Question"],
              rng: "random.Random") -> Tuple["Player", Optional["NegotiationSession"]]:
    with open(path, "r", encoding="utf-8") as f:
        data: SaveGame = json.load(f)

    if int(data.get("version", 0)) != SAVE_VERSION:
        raise ValueError(f"Incompatible save version: {data.get('version')} != {SAVE_VERSION}")

    # Player
    sp = data["player"]
    player = Player(core_alignment=alignment_from_save(sp["core"]))
    player.stance_alignment = alignment_from_save(sp["stance"])
    player.gold = int(sp.get("gold", 0))
    player.inventory = {str(k): int(v) for k, v in sp.get("inventory", {}).items()}

    # Demons: index + availability + roster
    idx = build_demon_index(demons)

    for did, meta in data.get("world", {}).get("demons", {}).items():
        if did in idx and hasattr(idx[did], "available"):
            idx[did].available = bool(meta.get("available", True))

    for did in sp.get("roster", []):
        if did in idx:
            d = idx[did]
            if d not in player.roster:
                player.roster.append(d)
            if hasattr(d, "available"):
                d.available = False
        else:
            print(f"[load] Warning: roster demon '{did}' not found in catalog.")

    # DemonDex (opcional)
    dex = data.get("demondex")
    if dex:
        player.dex_seen = set(dex.get("seen", []))
        # caught ya se reflejó en roster; puedes sincronizar si quieres

    # Session (opcional)
    ss = data.get("session")
    if ss:
        demon_id_in_save = ss["demon_id"]
        if demon_id_in_save not in idx:
            raise KeyError(f"Saved demon '{demon_id_in_save}' missing from catalog.")
        d = idx[demon_id_in_save]
        sess = NegotiationSession(player=player, demon=d, question_pool=questions_pool, rng=rng)
        sess.in_progress = bool(ss.get("in_progress", True))
        sess.rapport = int(ss.get("rapport", 0))
        sess.turns_left = int(ss.get("turns_left", d.patience))
        sess.round_no = int(ss.get("round_no", 1))
        sess.recruited = bool(ss.get("recruited", False))
        sess.fled = bool(ss.get("fled", False))
        return player, sess

    return player, None

# =========================
# Serialization helpers
# =========================

SAVE_VERSION = 2  # bump if you change format later

def demon_id(d: "Demon") -> str:
    return d.id  # ahora existe siempre

def build_demon_index(demons: List["Demon"]) -> Dict[str, "Demon"]:
    idx = {}
    for d in demons:
        if d.id in idx:
            raise ValueError(f"Duplicate demon id: {d.id}")
        idx[d.id] = d
    return idx

def alignment_to_save(a: "Alignment") -> SaveAlignment:
    return {"lc": int(a.law_chaos), "ld": int(a.light_dark)}

def alignment_from_save(d: SaveAlignment) -> "Alignment":
    return Alignment(law_chaos=int(d["lc"]), light_dark=int(d["ld"]))

def save_game(path: str, player: "Player", demons: List["Demon"],
              session: Optional["NegotiationSession"]) -> None:
    data: SaveGame = {
        "version": SAVE_VERSION,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "player": player_to_save(player),
        "world": world_to_save(demons),
        "session": session_to_save(session) if session and session.in_progress else None,
        "demondex": dex_to_save(player),
    }

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_save_", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)  # atomic on same filesystem
        print(f"[save] Saved to {path}")
    except Exception:
        try: os.remove(tmp)
        except OSError: pass
        raise

# =========================
# Validation helpers
# =========================

def validate_questions_against_items(questions: List[Question]) -> None:
    """
    Scan all choices for ask_item events and ensure items exist in ITEM_CATALOG.
    Raise ValueError on first mismatch (fail fast).
    """
    for q in questions:
        for label, eff in q.choices.items():
            evt = eff.get("event")
            if isinstance(evt, dict) and str(evt.get("type", "")).lower() == "ask_item":
                iid = canonical_item_id(evt.get("item", ""))
                if iid not in ITEM_CATALOG:
                    raise ValueError(
                        f"Question '{q.id}' choice '{label}' references unknown item '{iid}'."
                        " Add it to data/items.json or fix the name."
                    )

def validate_event_refs(questions: List[Question]) -> None:
    for q in questions:
        for label, eff in q.choices.items():
            ref = eff.get("event_ref")
            if ref and ref not in EVENTS_REGISTRY:
                raise ValueError(f"Question '{q.id}' choice '{label}' references unknown event_ref '{ref}'.")

def validate_events_against_items() -> None:
    # ensure all ask_item in EVENTS_REGISTRY reference catalog items
    for eid, ev in EVENTS_REGISTRY.items():
        if ev.get("type") == "ask_item":
            iid = canonical_item_id(ev.get("item", ""))
            if iid not in ITEM_CATALOG:
                raise ValueError(f"Event '{eid}' references unknown item '{iid}'.")


# =========================
# Loaders
# =========================

def load_config(path: str = "config.json") -> None:
    """
    Read config.json and update global limits/seed/UI settings.
    If the file is missing, continue with defaults.

    Validates that min < max for each range.

    Side effects:
      - Sets global RAPPORT_MIN/MAX, AXIS_MIN/MAX, TOL_MIN/MAX
      - Sets RNG_SEED and seeds the RNG if not None
      - Sets ROUND_DELAY_SEC
      - Prints a short status message
    """

    global RAPPORT_MIN, RAPPORT_MAX, AXIS_MIN, AXIS_MAX
    global TOL_MIN, TOL_MAX, RNG_SEED, ROUND_DELAY_SEC

    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        print(f"[config] {path} not found. Using defaults.")
        return

    def nested_get(d, keys, default=None):
        cur = d
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

    rmin = nested_get(cfg, ["rapport", "min"], RAPPORT_MIN)
    rmax = nested_get(cfg, ["rapport", "max"], RAPPORT_MAX)
    amin = nested_get(cfg, ["alignment", "min"], AXIS_MIN)
    amax = nested_get(cfg, ["alignment", "max"], AXIS_MAX)
    tmin = nested_get(cfg, ["tolerance", "min"], TOL_MIN)
    tmax = nested_get(cfg, ["tolerance", "max"], TOL_MAX)
    seed = cfg.get("rng_seed", RNG_SEED)
    delay = nested_get(cfg, ["ui", "round_delay_seconds"], ROUND_DELAY_SEC)

    # Minimal validation
    if rmin >= rmax: raise ValueError("rapport.min must be < rapport.max")
    if amin >= amax: raise ValueError("alignment.min must be < alignment.max")
    if tmin >= tmax: raise ValueError("tolerance.min must be < tolerance.max")

    RAPPORT_MIN, RAPPORT_MAX = int(rmin), int(rmax)
    AXIS_MIN, AXIS_MAX       = int(amin), int(amax)
    TOL_MIN, TOL_MAX         = int(tmin), int(tmax)
    ROUND_DELAY_SEC          = int(delay) if delay is not None else 0
    RNG_SEED                 = int(seed) if seed is not None else None

    if RNG_SEED is not None:
        random.seed(RNG_SEED)
        print(f"[config] RNG seeded with {RNG_SEED}")

    print(
        f"[config] Loaded. Rapport {RAPPORT_MIN}..{RAPPORT_MAX}, "
        f"Alignment {AXIS_MIN}..{AXIS_MAX}, Tolerance {TOL_MIN}..{TOL_MAX}, "
        f"Delay {ROUND_DELAY_SEC}s."
    )

def load_demons(path: str) -> List[Demon]:
    """
    Load demons from JSON:
    [
      {
        "name": "Pixie",
        "alignment": {"law_chaos": 1, "light_dark": 2},
        "personality": "PLAYFUL",
        "patience": 5, "tolerance": 4, "rapport_needed": 2
      }, ...
    ]
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Demons file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    demons: List[Demon] = []
    if not isinstance(raw, list):
        raise ValueError("demons.json must contain a list of demons.")

    for i, item in enumerate(raw, start=1):
        try:
            name = str(item["name"])
            al = item.get("alignment", {})
            lc = _coerce_int(al.get("law_chaos", 0))
            ld = _coerce_int(al.get("light_dark", 0))
            align = Alignment(law_chaos=lc, light_dark=ld)

            personality = _parse_personality(item.get("personality", "PLAYFUL"))
            patience = _coerce_int(item.get("patience", 4), 4)
            tolerance = _coerce_int(item.get("tolerance", 3), 3)
            rapport_needed = _coerce_int(item.get("rapport_needed", 2), 2)

            demons.append(
                Demon(
                    name=name,
                    alignment=align,
                    personality=personality,
                    patience=patience,
                    tolerance=tolerance,
                    rapport_needed=rapport_needed,
                )
            )
        except Exception as e:
            raise ValueError(f"Invalid demon at index {i}: {e}") from e

    return demons

def load_questions(path: str) -> List[Question]:
    """
    Load questions from JSON:
    [
      {
        "id": "...",
        "text": "...",
        "tags": ["..."],
        "choices": {
           "Option label": {"dLC":0,"dLD":1,"dRapport":1,"tags":["..."]},
           ...
        }
      }, ...
    ]
    """
    # Allow singular/plural fallback if you wish
    if not os.path.exists(path):
        alt = path.replace("question.json", "questions.json")
        if os.path.exists(alt):
            path = alt
        else:
            raise FileNotFoundError(f"Questions file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        raise ValueError("questions.json must contain a list of questions.")

    questions: List[Question] = []
    for i, q in enumerate(raw, start=1):
        try:
            qid = str(q["id"])
            text = str(q["text"])
            tags = _ensure_list_of_str(q.get("tags", []))

            choices_raw = q.get("choices", {})
            if not isinstance(choices_raw, dict) or not choices_raw:
                raise ValueError("choices must be a non-empty object.")

            # Normalize effects
            norm_choices: Dict[str, Effect] = {}
            for label, eff in choices_raw.items():
                if not isinstance(eff, dict):
                    raise ValueError(f"choice '{label}' must be an object with dLC/dLD/dRapport.")
                norm_choices[str(label)] = Effect(
                    dLC=_coerce_int(eff.get("dLC", 0)),
                    dLD=_coerce_int(eff.get("dLD", 0)),
                    dRapport=_coerce_int(eff.get("dRapport", 0)),
                    tags=_ensure_list_of_str(eff.get("tags", [])),
                )

            questions.append(Question(id=qid, text=text, tags=tags, choices=norm_choices))

        except Exception as e:
            raise ValueError(f"Invalid question at index {i}: {e}") from e

    return questions

def load_personality_weights(path: str = "data/personality_weights.json") -> None:
    """
    Load personality tag weights from JSON into PERSONALITY_TAG_WEIGHTS.
    JSON schema:
      { "PLAYFUL": {"humor": 2, "order": -1, ...}, "CUNNING": {...}, ... }

    - Keys must be Personality names (case-insensitive).
    - Inner keys are tag strings (we normalize to lowercase).
    - Values are ints; clamped to [-2, 2].
    If file is missing or empty, we fall back to neutral (no bonuses).
    """
    global PERSONALITY_TAG_WEIGHTS

    if not os.path.exists(path):
        print(f"[weights] {path} not found. Using neutral weights (no personality bonuses).")
        PERSONALITY_TAG_WEIGHTS = {}
        return

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError("personality_weights.json must be a JSON object mapping personality -> tag map.")

    weights: dict[Personality, dict[str, int]] = {}
    for p_name, tagmap in raw.items():
        if not isinstance(tagmap, dict):
            raise ValueError(f"Invalid tag map for personality {p_name!r}: must be an object.")

        # Map string to Personality enum (case-insensitive)
        try:
            p = Personality[p_name.strip().upper()]
        except KeyError as e:
            raise ValueError(f"Unknown personality name: {p_name!r}") from e

        inner: dict[str, int] = {}
        for tag, val in tagmap.items():
            try:
                v = int(val)
            except (TypeError, ValueError):
                raise ValueError(f"Weight for tag {tag!r} under {p_name!r} must be an integer.")
            # Clamp to [-2, 2]
            if v < -2: v = -2
            if v >  2: v =  2
            inner[str(tag).lower()] = v  # normalize tag key to lowercase

        weights[p] = inner

    PERSONALITY_TAG_WEIGHTS = weights
    total = sum(len(m) for m in weights.values())
    print(f"[weights] Loaded {total} tag weights across {len(weights)} personalities.")

def load_item_catalog(path: str = "data/items.json") -> None:
    """
    Load item catalog from JSON into ITEM_CATALOG.
    JSON schema (recommended): a single object mapping item_id -> ItemDef.
    All keys are normalized to lowercase.
    Defaults:
      rarity="common", value=0, stackable=True, description=""
      display_name = Title Case of the key if missing.
    """
    global ITEM_CATALOG

    if not os.path.exists(path):
        print(f"[items] {path} not found. Loaded empty catalog.")
        ITEM_CATALOG = {}
        return

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError("items.json must be a JSON object mapping item_id -> item metadata.")

    catalog: Dict[str, ItemDef] = {}
    for raw_key, meta in raw.items():
        key = canonical_item_id(raw_key)
        if not isinstance(meta, dict):
            raise ValueError(f"Item '{raw_key}' must have an object as value.")
        display = str(meta.get("display_name") or raw_key.title())
        rarity = str(meta.get("rarity") or "common").lower()
        if rarity not in {"common", "uncommon", "rare", "epic", "legendary"}:
            raise ValueError(f"Item '{raw_key}' has invalid rarity: {rarity}")
        try:
            value = int(meta.get("value", 0))
        except (TypeError, ValueError):
            value = 0
        stackable = bool(meta.get("stackable", True))
        desc = str(meta.get("description", ""))

        catalog[key] = ItemDef(
            display_name=display,
            rarity=rarity,      # type: ignore[assignment]
            value=value,
            stackable=stackable,
            description=desc,
        )

    ITEM_CATALOG = catalog
    print(f"[items] Loaded {len(ITEM_CATALOG)} items.")

def load_events(path: str = "data/events.json") -> None:
    """Load event templates by id into EVENTS_REGISTRY."""
    global EVENTS_REGISTRY
    if not os.path.exists(path):
        print(f"[events] {path} not found. Loaded empty registry.")
        EVENTS_REGISTRY = {}
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("events.json must be an object mapping id -> event payload.")
    # normalize a bit (clamp ranges later if needed)
    EVENTS_REGISTRY = {str(k): v for k, v in data.items()}
    print(f"[events] Loaded {len(EVENTS_REGISTRY)} events.")


def load_whims(path: str = "data/whims.json") -> None:
    """Load whim config and templates."""
    global WHIMS_CONFIG, WHIM_TEMPLATES
    if not os.path.exists(path):
        print(f"[whims] {path} not found. Whims disabled.")
        WHIMS_CONFIG, WHIM_TEMPLATES = {}, []
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("whims.json must be an object with base_chance, personality_mod, entries[].")
    WHIMS_CONFIG = {
        "base_chance": float(data.get("base_chance", 0.0)),
        "personality_mod": {str(k).upper(): float(v) for k, v in data.get("personality_mod", {}).items()},
    }
    entries = data.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("whims.json 'entries' must be a list.")
    # normalize ids and ensure required fields
    norm_entries: List[EventPayload] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        e = dict(e)
        e["type"] = str(e.get("type", "")).lower()  # ask_gold/ask_item
        e["id"] = str(e.get("id", ""))
        e["weight"] = int(e.get("weight", 1))
        norm_entries.append(e)  # we keep validation light for now
    WHIM_TEMPLATES = norm_entries
    print(f"[whims] Loaded {len(WHIM_TEMPLATES)} whim templates.")

def load_personality_cues(path: str = "data/personality_cues.json") -> None:
    """
    Load textual cues per Personality from JSON into PERSONALITY_CUES_BY_NAME.
    JSON schema: { "PLAYFUL": {"Delighted":"...", "Pleased":"...", ...}, ... }
    Keys are personality names (case-insensitive). Tone keys are used as-is.
    Missing file → empty table (fallback to default emoji at usage).
    """
    global PERSONALITY_CUES_BY_NAME

    if not os.path.exists(path):
        print(f"[cues] {path} not found. Using default emoji-only cues.")
        PERSONALITY_CUES_BY_NAME = {}
        return

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError("personality_cues.json must be an object mapping personality -> {tone: cue}.")

    # Normalize personality keys to upper-case names
    table: Dict[str, Dict[str, str]] = {}
    for pname, tones in raw.items():
        if not isinstance(tones, dict):
            raise ValueError(f"Cues for '{pname}' must be an object.")
        table[str(pname).strip().upper()] = {str(k): str(v) for k, v in tones.items()}

    PERSONALITY_CUES_BY_NAME = table
    total = sum(len(v) for v in table.values())
    print(f"[cues] Loaded {total} cues across {len(table)} personalities.")

# =========================
#  Console-layer Functions
# =========================

def show_menu(session) -> str:
    if not session.in_progress:
        print("La negociación ha terminado...")
        return "0"
    print("\n¿Qué deseas hacer?")
    print("1) Responder la siguiente pregunta")
    print("2) Bromear (minijuego rápido para ajustar rapport)")
    print("3) Mostrar estado de la sesión")
    print("4) Intentar cerrar trato ahora (evaluar unión)")
    print("5) Despedirse (terminar negociación)")
    print("6) Guardar y salir")  # NEW
    valid = {"1","2","3","4","5","6"}
    while True:
        choice = input("Elige una opción (1-6): ").strip()
        if choice in valid:
            return choice
        print("OPCION NO VALIDA. Intenta de nuevo.")


def dispatch_action(session, option: str) -> None:
    """
    Dispatch the selected option to the corresponding session action.
    Follows your spec strictly.
    """
    if option == "1":
        effect = session.ask()
        feedback = session.process_answer(effect)  # now returns ReactionFeedback

        # Show reaction feedback (console layer)
        print(f"{session.demon.name} looks {feedback.tone.lower()}. {feedback.cue}")
        # Optional hints (only print if non-empty)
        if feedback.liked_tags:
            print("  Liked tags: " + ", ".join(feedback.liked_tags))
        if feedback.disliked_tags:
            print("  Disliked tags: " + ", ".join(feedback.disliked_tags))
        # Compact numbers (you already show a HUD elsewhere, this is just a quick glance)
        print("  " + " | ".join(feedback.notes))

        # Intuitive indicators

        print(f"  Rapport gauge: {rapport_gauge(session.rapport)}")
        print(f"  Distance trend: {distance_trend(feedback.delta_distance)}")

    elif option == "2":
        # Simple rapport mini-game: guess a number 0..2
        secret = random.randint(0, 2)

        while True:
            raw = input("Adivina un número (0-2): ").strip()
            if raw in {"0", "1", "2"}:
                guess = int(raw)
                break
            print("Entrada inválida. Intenta de nuevo (0, 1 o 2).")

        if guess == secret:
            print("¡Correcto!")
            session.rapport = min(RAPPORT_MAX, session.rapport + 2)
        else:
            print("Incorrecto.")
            session.rapport = max(RAPPORT_MIN, session.rapport - 1)

    elif option == "3":
        session.show_status()
    elif option == "4":
        session.check_union()
    elif option == "5":
        session.in_progress = False
        session.fled = True
        print(f"{session.demon.name} se marcha...")
    elif option == "6":
        save_game(SAVE_PATH, session.player, demons_catalog, session)
        print("Game saved. Exiting…")
        session.in_progress = False
        session.fled = True
    else:
        print("OPCION NO VALIDA.")

    else:
        print("OPCION NO VALIDA.")


def print_banner() -> None:
    print("SMT-lite Demon Recruitment 1.0 beta")
    print("Negocia con demonios usando alineamiento y rapport.")

def read_difficulty() -> int:
    """
    Ask the user for a difficulty level (1..5). Clamp and return an int.
    """
    while True:
        raw = input("Elige nivel de dificultad (1-5): ").strip()
        if raw.isdigit():
            lvl = int(raw)
            return max(1, min(5, lvl))
        print("Entrada inválida. Intenta con un número entre 1 y 5.")

def choose_demon(demons: list[Demon]) -> Demon:
    available = [d for d in demons if getattr(d, "available", True)]
    if not available:
        # Fallback: if all are taken, reuse the full list
        available = demons[:]
    return random.choice(available)


def run_game_loop(session: NegotiationSession, diff_level: int) -> None:
    """
    Core loop: show status, run menu, apply actions, check join/leave,
    apply difficulty pressure, and advance rounds until the session ends.
    """
    # Optional: if you loaded ROUND_DELAY_SEC from config, use it; else fallback
    try:
        delay = ROUND_DELAY_SEC
    except NameError:
        delay = 0  # or 3 if you want a default pause


    try:

        while session.in_progress:
            print(f"\nEsta es la ronda número {session.round_no}.")
            session.show_status()

            whim = session.maybe_trigger_whim()
            if whim:
                decision = run_special_event(session, whim)
                session.process_event(whim, decision)

            opcion = show_menu(session)           # returns "1".."5" or "0" if ended
            if opcion == "0":
                break

            dispatch_action(session, opcion)

            # Per your spec, check both conditions after actions:
            session.check_union()
            session.check_fled()

            # Optional pause
            if delay > 0:
                time.sleep(delay)

            # Difficulty pressure
            session.difficulty(diff_level)

            # Advance round
            session.round_no += 1

            # autosave at end of round
            save_game(SAVE_PATH, session.player, demons_catalog, session)           
    
    except (KeyboardInterrupt, EOFError):
        # Smooth exit: stop the session and mark as fled
        print("\n[!] Interrupted by user. Ending negotiation softly…")
        save_game(SAVE_PATH, session.player, demons_catalog, session)
        session.in_progress = False
        session.fled = True

def summarize_session(session: NegotiationSession) -> None:
    """
    Print a final summary: alignments, distance, outcome, rounds, and roster.
    """
    # Finalization according to flags
    if session.recruited:
        session.finish_union()
    elif session.fled:
        session.finish_fled()

    # Summary data
    core = session.player.core_alignment
    stance = session.player.stance_alignment
    dist = stance.manhattan_distance(session.demon.alignment)
    roster_names = [d.name for d in session.player.roster]

    print("\n===== Session Summary =====")
    print(f"Player core LC/LD:   ({core.law_chaos}, {core.light_dark})")
    print(f"Player stance LC/LD: ({stance.law_chaos}, {stance.light_dark})")
    print(f"Demon: {session.demon.name} | Final distance: {dist}")
    print(f"Outcome: {'Recruited' if session.recruited else 'Fled' if session.fled else 'Ended'}")
    print(f"Rounds played: {session.round_no - 1}")
    print(f"Roster: {', '.join(roster_names) if roster_names else '(empty)'}")

def run_special_event(session: NegotiationSession, event: EventPayload) -> Dict[str, Any]:
    """
    Console interaction for special events. Returns a decision dict.
    """
    et = str(event.get("type", "")).lower()
    msg = event.get("message")
    if msg:
        print(f"\n[Evento] {msg}")

    # --- Ask gold or whim(kind=ask_gold) ---
    if et in ("ask_gold", "whim") and (event.get("kind") == "ask_gold" or et == "ask_gold"):
        amount = int(event.get("amount", 0))
        print(f"Te quedan {session.player.gold} monedas.")
        while True:
            ans = input(f"¿Pagar {amount} monedas? (s/n): ").strip().lower()
            if ans in {"s", "n"}:
                return {"pay": ans == "s"}

    # --- Ask item (classic SMT flow) ---
    if et == "ask_item":
        raw_item = str(event.get("item", "")).strip()
        amount = int(event.get("amount", 1))
        iid = canonical_item_id(raw_item)
        meta = ITEM_CATALOG.get(iid, {})
        disp = meta.get("display_name", raw_item.title())
        have = session.player.inventory.get(iid, 0)

        print(f"{session.demon.name} quiere {amount}x {disp}. (Tienes: {have})")
        if have < amount:
            print("No tienes suficientes. (No puedes aceptar.)")
            return {"give": False}

        while True:
            ans = input(f"¿Entregar {amount}x {disp}? (s/n): ").strip().lower()
            if ans in {"s", "n"}:
                return {"give": ans == "s"}

    if et == "trap":
        print("Notas tensión en el aire…")
        return {}

    return {}


def bootstrap_session(demons: list["Demon"], questions_pool: list["Question"],
                      rng: "random.Random") -> "NegotiationSession":
    if os.path.exists(SAVE_PATH):
        ans = input("Found a save. Load it? (y/n): ").strip().lower()
        if ans == "y":
            player, sess = load_game(SAVE_PATH, demons, questions_pool, rng)
            if sess:
                return sess
            # if no active session in save, start a new negotiation
            current_demon = choose_demon(demons)  # (optionally bias to available-only)
            return NegotiationSession(player=player, demon=current_demon, question_pool=questions_pool, rng=rng)

    # New game
    player = Player(core_alignment=Alignment(0, 0))
    player.gold = 0
    player.inventory = {}
    current_demon = choose_demon(demons)
    return NegotiationSession(player=player, demon=current_demon, question_pool=questions_pool, rng=rng)

# =========================
#  Main function
# =========================


def main() -> None:
    """Bootstrap the game, load all registries, and run one negotiation session."""
    print_banner()

    # 1) Config: limits, UI delay, RNG seed (may print status)
    try:
        load_config("config.json")
    except Exception as e:
        # Fail-fast is fine; but you can opt to continue with defaults
        print(f"[config] Error loading config.json: {e}. Using defaults.")

    # 2) RNG: create a single Random to inject everywhere (deterministic if RNG_SEED is set)
    rng = random.Random(RNG_SEED) if RNG_SEED is not None else random.Random()

    # 3) Personality weights (optional: neutral if file missing)
    try:
        load_personality_weights("data/personality_weights.json")
    except Exception as e:
        print(f"[weights] Error: {e}. Personality bonuses disabled.")
        # if you want, keep PERSONALITY_TAG_WEIGHTS = {} here

    try:
        load_personality_cues("data/personality_cues.json")
    except Exception as e:
        print(f"[weights] Error: {e}. Personality bonuses disabled.")


    # 4) Items catalog (needed before validating events/questions that reference items)
    try:
        load_item_catalog("data/items.json")
    except Exception as e:
        print(f"[items] Error: {e}. Loading empty catalog.")
        # ITEM_CATALOG will be {} (your loader already handles this case)

    # 5) Event templates (events.json) and 6) Whims config (whims.json)
    try:
        load_events("data/events.json")
    except Exception as e:
        print(f"[events] Error: {e}. Events registry is empty.")

    try:
        load_whims("data/whims.json")
    except Exception as e:
        print(f"[whims] Error: {e}. Whims disabled.")

    # 7) Questions (after events/items so we can validate references)
    try:
        questions_pool = load_questions("data/questions.json")
    except FileNotFoundError:
        # Fallback to singular name if you prefer it
        questions_pool = load_questions("data/question.json")
    except Exception as e:
        raise RuntimeError(f"[questions] Failed to load questions: {e}") from e

    # 8) Cross-validations (fail fast if data is inconsistent)
    try:
        validate_events_against_items()              # events ask_item → must exist in ITEM_CATALOG
        validate_questions_against_items(questions_pool)  # choices with ask_item → must exist in ITEM_CATALOG
        validate_event_refs(questions_pool)          # event_ref in questions → must exist in EVENTS_REGISTRY
    except Exception as e:
        raise RuntimeError(f"[validate] Data validation failed: {e}") from e

    # 9) Demons (independent of the above; do it now)
    try:
        demons = load_demons("data/demons.json")
    except Exception as e:
        raise RuntimeError(f"[demons] Failed to load demons: {e}") from e

    # Difficulty input (validated and clamped inside the function)
    diff_level = read_difficulty()

    # Choose a demon using the same RNG (consistent with the session RNG)
    current_demon = choose_demon(demons)  # If you added rng param: choose_demon(demons, rng=rng)

    session = bootstrap_session(demons, questions_pool, rng)

    # 11) Run loop with graceful keyboard interrupt handling
    try:
        run_game_loop(session, diff_level)
    except (KeyboardInterrupt, EOFError):
        print("\n[!] Interrupted by user. Ending negotiation softly…")
        session.in_progress = False
        session.fled = True
    finally:
        summarize_session(session)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        # Covers interruptions before main builds the session
        print("\nBye!")

