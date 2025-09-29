"""
SMT-lite: Demon Recruitment.
Description: 
    - Light mini game to simulate the Demon Recruitment system on SMT. 
    - Made to be implemented in Cognitas Discord Bot.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from enum import Enum
import random

# ====== Defaults (used if config.json is missing or incomplete) ======
RAPPORT_MIN, RAPPORT_MAX = -3, 3
AXIS_MIN, AXIS_MAX       = -5, 5
TOL_MIN, TOL_MAX         = 1, 5
RNG_SEED                 = None
ROUND_DELAY_SEC          = 0

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
    import json, random

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
    
# =========================
# OOP Models
# =========================

class Personality(Enum):
    PLAYFUL = "PLAYFUL"
    CHILDISH = "CHILDISH"
    MOODY = "MOODY"
    CUNNING = "CUNNING"
    PROUD = "PROUD"

@dataclass
class Alignment:
    """Aligment axis: LC (Law/Chaos), LD (Light/Dak)"""
    law_chaos: int = 0
    light_dark: int = 0

    def clamp(self, lo: int = -5, hi: int = 5) -> None:
        """ Adjusts the values to the ranges """
        self.law_chaos  = max(AXIS_MIN, min(AXIS_MAX, self.law_chaos))
        self.light_dark = max(AXIS_MIN, min(AXIS_MAX, self.light_dark))

    def manhattan_distance(self, other: "Alignment") -> int:
        """ Compare with other alignments to make decisions """
        return abs(self.law_chaos - other.law_chaos) + abs(self.light_dark - other.light_dark)

@dataclass
class Question:
    """Loads the Question from the .json and transforms it into an object"""
    id: str 
    text: str
    choices: Dict[str, ChoiceEffect]
    tags: List[str]

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

        Parameters
        ----------
        effect : dict or object with attribute 'dRapport'
            The effect payload from the chosen option, e.g.:
            {"dLC": int, "dLD": int, "dRapport": int, ...}
            In this phase we only care about 'dRapport'.

        Returns
        -------
        (delta_rapport, delta_tolerance) : tuple[int, int]
            For this phase: (dRapport, 0).
        """
        # 1) Read dRapport flexibly: dict first, then fallback to attribute.
        try:
            d_rep = effect.get("dRapport", 0)
        except AttributeError:
            d_rep = getattr(effect, "dRapport", 0)

        # 2) Minimal validation.
        if not isinstance(d_rep, (int, float)):
            raise TypeError("dRapport must be numeric (int or float).")

        # 3) Normalize to int for consistent arithmetic/clamping elsewhere.
        d_rep = int(d_rep)

        # 4) In this phase, tolerance does not change.
        delta_tolerance = 0

        # 5) Return the deltas (session applies them and clamps globally).
        return d_rep, delta_tolerance


class Player:

    def __init__ (self, core_alignment: Aligment):

        self.core_alignment = core_alignment
        self.stance_alignment = Aligment(law_chaos = core_alignment.law_chaos, light_dark = core_alignment.light_dark)
        self.roster: list[Demon] = []


     def relax_posture(self, step: int = 1) -> None:
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

    # Avoid repeating questions within the session

    _user_question_ids: Set[str] = field(default_factory = set, repr = False)

    def __post_init__(self):
        """Initialize values that depend on demon at runtime."""
        self.turns_left = self.demon.patience


    def pick_question(self) -> "Question":
        """
        Pick a question for this turn. Minimal version:
        - Prefer questions not used in this session.
        - If none left, reset and use the full pool.
        - Choose randomly.
        """
        candidates = [q for q in self.questions_pool if q.id not in self._used_question_ids]
        if not candidates:
            candidates = self.questions_pool[:]     # reset
            self._used_question_ids.clear()

        q = random.choice(candidates)
        self._used_question_ids.add(q.id)
        return q

    def ask(self) -> Dict[str, int]:
        """
        Show a question and collect a valid choice.
        Returns the chosen option's effect dict, e.g. {"dLC":0, "dLD":1, "dRapport":1}.
        """
        q = self.pick_question()

        # 1) Print question and numbered options
        print(f"\nQ: {q.text}")
        options = list(q.choices.items())  # [(label, effect_dict), ...]  (dict preserves insertion order)
        for idx, (label, _) in enumerate(options, start=1):
            print(f"  {idx}) {label}")

        # 2) Read a valid index
        while True:
            raw = input("Choose an option number: ").strip()
            if raw.isdigit():
                i = int(raw)
                if 1 <= i <= len(options):
                    _, effect = options[i - 1]
                    return effect
            print("Invalid choice. Try again.")


        

def main():
    load_config("config.json")   # 1) set limits/seed/UI first
    demons = load_demons("data/demons.json")
    questions = load_questions("data/questions.json")

    player = Player(core_alignment=Alignment(0, 0),
                    stance_alignment=Alignment(0, 0))
    demon = demons[0]
    session = NegotiationSession(player, demon, questions)
    run_loop(session)

if __name__ == "__main__":
    main()
