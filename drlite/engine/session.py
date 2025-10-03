from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional
import random

from drlite.config import RAPPORT_MIN, RAPPORT_MAX, ROUND_DELAY_SEC
from drlite.models import Player, Demon, Question, ReactionFeedback
from drlite.utils import weighted_choice


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



    def process_answer(self, effect: Dict[str, int]) -> ReactionFeedback:
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
            cue=flavor_cue(self.demon.personality, tone, default_emoji),
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


