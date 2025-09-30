"""
SMT-lite: Demon Recruitment.
Description: 
    - Light mini game to simulate the Demon Recruitment system on SMT. 
    - Made to be implemented in Cognitas Discord Bot.
"""

from __future__ import annotations
from dataclasses import dataclass, field
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

    def __init__ (self, core_alignment: Alignment):

        self.core_alignment = core_alignment
        self.stance_alignment = Alignment(law_chaos = core_alignment.law_chaos, light_dark = core_alignment.light_dark)
        self.roster: list[Demon] = []


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

    _used_question_ids: Set[str] = field(default_factory = set, repr = False)

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
        candidates = [q for q in self.question_pool if q.id not in self._used_question_ids]
        if not candidates:
            candidates = self.question_pool[:]     # reset
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


    def process_answer(self, effect: Dict[str, int]) -> None:
        """
        Apply the chosen effect to stance and session metrics.
        - Update stance (dLC/dLD) and clamp.
        - Ask demon to react (get delta_rapport).
        - Clamp rapport.
        - Decrement turns and relax player's posture.
        - Print a compact summary.
        """
        # 1) Apply stance deltas
        d_lc = int(effect.get("dLC", 0))
        d_ld = int(effect.get("dLD", 0))
        self.player.stance_alignment.law_chaos += d_lc
        self.player.stance_alignment.light_dark += d_ld
        self.player.stance_alignment.clamp()  # keeps stance within global bounds

        # 2) Demon reaction → rapport delta (tolerance stays unchanged in Phase A)
        d_rep, _ = self.demon.react(effect)

        # 3) Clamp rapport using global limits
        new_rapport = self.rapport + d_rep
        self.rapport = max(RAPPORT_MIN, min(RAPPORT_MAX, new_rapport))

        # 4) Turns and posture relaxation
        self.turns_left -= 1
        self.player.relax_posture()

        # 5) Summary
        print(f"Δ Stance: LC {d_lc:+}, LD {d_ld:+} | Rapport: {self.rapport} | Turns left: {self.turns_left}")



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
   
    def difficulty(self, nivel: int) -> None:
        """
        Light pressure mechanics:
        - Decrease rapport randomly by 0..(nivel//2), not below the minimum.
        - Optionally nudge stance 1 step away from the demon with probability nivel/10.
        Then clamp stance and keep state consistent.
        """
        # 1) Rapport pressure
        drop = random.randint(0, max(0, nivel // 2))
        self.rapport = max(RAPPORT_MIN, self.rapport - drop)

        # 2) Optional nudge away from the demon (probability nivel/10)
        if random.random() < (nivel / 10.0):
            axis = random.choice(("law_chaos", "light_dark"))
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

    def finish_fled(self) -> None:
            """If fled, notify."""
            if self.fled:
                print(f"The negotiation with {self.demon.name} ended. The demon walked away.")

def show_menu(session) -> str:
    """
    Print the console menu and return the chosen option as a string.
    If the session already ended, return "0".
    """
    if not session.in_progress:
        print("La negociación ha terminado...")
        return "0"

    print("\n¿Qué deseas hacer?")
    print("1) Responder la siguiente pregunta")
    print("2) Bromear (minijuego rápido para ajustar rapport)")
    print("3) Mostrar estado de la sesión")
    print("4) Intentar cerrar trato ahora (evaluar unión)")
    print("5) Despedirse (terminar negociación)")

    valid = {"1", "2", "3", "4", "5"}
    while True:
        choice = input("Elige una opción (1-5): ").strip()
        if choice in valid:
            return choice
        print("OPCION NO VALIDA. Intenta de nuevo.")


def dispatch_action(session, option: str) -> None:
    """
    Dispatch the selected option to the corresponding session action.
    Follows your spec strictly.
    """
    if option == "1":
        # Ask a question and process the returned effect
        effect = session.ask()                 # returns a dict like {"dLC":0,"dLD":1,"dRapport":1}
        session.process_answer(effect)

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
            # Clamp rapport using your global limits
            try:
                # Prefer globals if already present in this module
                new_val = session.rapport + 2
                session.rapport = min(RAPPORT_MAX, new_val)
            except NameError:
                # Fallback: no globals visible; be explicit or import from your settings module
                # Example fallback clamps to [-3, 3]
                session.rapport = min(3, session.rapport + 2)
        else:
            print("Incorrecto.")
            try:
                new_val = session.rapport - 1
                session.rapport = max(RAPPORT_MIN, new_val)
            except NameError:
                # Fallback: clamp to [-3, 3] if constants not in scope
                session.rapport = max(-3, session.rapport - 1)

    elif option == "3":
        # Show current session HUD
        session.show_status()

    elif option == "4":
        # Try to close the deal now
        session.check_union()

    elif option == "5":
        # End the negotiation voluntarily
        session.in_progress = False
        session.fled = True
        print(f"{session.demon.name} se marcha...")

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


def build_prototype_data():
    # 1) Player: core at (0, 0), stance as a copy
    core = Alignment(0, 0)
    player = Player(core_alignment=core)
    # (If your Player.__init__ already clones stance, you don't need to set it again.)

    # 2) Demons (2 examples)
    demons = [
        Demon(name="Pixie", alignment=Alignment(1, 2), personality=Personality.PLAYFUL,
              patience=5, tolerance=4, rapport_needed=2),
        Demon(name="Onmoraki", alignment=Alignment(-2, -2), personality=Personality.MOODY,
              patience=4, tolerance=3, rapport_needed=2),
    ]

    # 3) Questions (minimal pool; choices are simple dicts)
    questions_pool = [
        Question(
            id="q_mercy_1",
            text="Un enemigo derrotado suplica por su vida. ¿Qué haces?",
            tags=["mercy", "order", "ruthless"],
            choices={
                "Mostrar piedad":        {"dLC": 0, "dLD": 1,  "dRapport": 1},
                "Capturarlo y juzgarlo": {"dLC": 1, "dLD": 0,  "dRapport": 0},
                "Acabar con él":         {"dLC": 0, "dLD": -1, "dRapport": -1},
            },
        ),
        Question(
            id="q_order_1",
            text="Hay toque de queda en la ciudad. Tus amigos quieren salir.",
            tags=["order", "freedom", "reckless"],
            choices={
                "Cumplirlo estrictamente": {"dLC": 1,  "dLD": 0,  "dRapport": 1},
                "Hacer una excepción":     {"dLC": -1, "dLD": 0,  "dRapport": 0},
                "Ignorarlo y festejar":    {"dLC": -1, "dLD": 0,  "dRapport": -1},
            },
        ),
        Question(
            id="q_humor_1",
            text="Un guardia te pide la contraseña.",
            tags=["humor", "trick", "order"],
            choices={
                "Broma ingeniosa":        {"dLC": -1, "dLD": 0,  "dRapport": 1},
                "Seguir el protocolo":    {"dLC": 1,  "dLD": 0,  "dRapport": 0},
                "Sobornar discretamente": {"dLC": 0,  "dLD": 0,  "dRapport": -1},
            },
        ),
        Question(
            id="q_honor_1",
            text="Te retan a un duelo formal.",
            tags=["honor", "trick", "freedom"],
            choices={
                "Aceptar el duelo":    {"dLC": 1,  "dLD": 1,  "dRapport": 1},
                "Tender una trampa":   {"dLC": -1, "dLD": 0,  "dRapport": 0},
                "Rehusar y retirarte": {"dLC": 0,  "dLD": 0,  "dRapport": -1},
            },
        ),
    ]
    return player, demons, questions_pool


def run_game_loop(sesion: NegotiationSession, nivel_dificultad: int) -> None:
    """
    Core loop: show status, run menu, apply actions, check join/leave,
    apply difficulty pressure, and advance rounds until the session ends.
    """
    # Optional: if you loaded ROUND_DELAY_SEC from config, use it; else fallback
    try:
        delay = ROUND_DELAY_SEC
    except NameError:
        delay = 0  # or 3 if you want a default pause

    while sesion.in_progress:
        print(f"\nEsta es la ronda número {sesion.round_no}.")
        sesion.show_status()

        opcion = show_menu(sesion)           # returns "1".."5" or "0" if ended
        if opcion == "0":
            break

        dispatch_action(sesion, opcion)

        # Per your spec, check both conditions after actions:
        sesion.check_union()
        sesion.check_fled()

        # Optional pause
        if delay > 0:
            time.sleep(delay)

        # Difficulty pressure
        sesion.difficulty(nivel_dificultad)

        # Advance round
        sesion.round_no += 1

def summarize_session(sesion: NegotiationSession) -> None:
    """
    Print a final summary: alignments, distance, outcome, rounds, and roster.
    """
    # Finalization according to flags
    if sesion.recruited:
        sesion.finish_union()
    elif sesion.fled:
        sesion.finish_fled()

    # Summary data
    core = sesion.player.core_alignment
    stance = sesion.player.stance_alignment
    dist = stance.manhattan_distance(sesion.demon.alignment)
    roster_names = [d.name for d in sesion.player.roster]

    print("\n===== Session Summary =====")
    print(f"Player core LC/LD:   ({core.law_chaos}, {core.light_dark})")
    print(f"Player stance LC/LD: ({stance.law_chaos}, {stance.light_dark})")
    print(f"Demon: {sesion.demon.name} | Final distance: {dist}")
    print(f"Outcome: {'Recruited' if sesion.recruited else 'Fled' if sesion.fled else 'Ended'}")
    print(f"Rounds played: {sesion.round_no - 1}")
    print(f"Roster: {', '.join(roster_names) if roster_names else '(empty)'}")

def main():
    print_banner()
    
    try:
        load_config("config.json")  # sets RAPPORT_MIN/MAX, AXIS_MIN/MAX, TOL_MIN/MAX, RNG_SEED, etc.
    except NameError:
        # If load_config is not available yet, you can skip it during the first run.
        pass

    player, demons, questions_pool = build_prototype_data()
    diff_level = read_difficulty()
    current_demon = choose_demon(demons)
    session = NegotiationSession(player=player, demon=current_demon, question_pool=questions_pool)
    run_game_loop(session, diff_level)
    summarize_session(session)

if __name__ == "__main__":
    main()
