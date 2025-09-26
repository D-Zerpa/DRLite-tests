"""
SMT-lite: Demon Recruitment.
Description: 
    - Light mini game to simulate the Demon Recruitment system on SMT. 
    - Made to be implemented in Cognitas Discord Bot.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import random

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
        self.law_chaos = max(lo, min(hi, self.law_chaos))
        self.light_dark = max(lo, min(hi, self.light_dark))

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

    