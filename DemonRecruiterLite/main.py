"""
SMT-lite: Demon Recruitment.
Description: 
    - Light mini game to simulate the Demon Recruitment system on SMT. 
    - Made to be implemented in Cognitas Discord Bot.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
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

@dataclass(eq= False)
class Demon:

    name: str
    alignment: Alignment
    personality: random.choice("PLAYFUL","CHILDISH","MOODY","CUNNING","PROUD")
    patience: int = 4
    tolerance: int = 3
    rapport_needed: int = 2
    available = bool = field(default=True, repr=False, compare=False)

    def pick_question(self, session):
        pass


    def reaction(self, choice_effect):
        pass


if __name__ == "__main__":
    main()