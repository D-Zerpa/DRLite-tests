from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Any
import random

from drlite.config import RAPPORT_MIN, RAPPORT_MAX, ROUND_DELAY_SEC
from drlite.models import Player, Demon, Question, ReactionFeedback, EventResult, WhimResult
from drlite.utils import weighted_choice, tone_from_delta, flavor_cue, ensure_list_of_str


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

    def process_event(
    self,
    payload: Mapping[str, Any],
    *,
    ask_yes_no: Callable[[str], bool],
    ask_pay: Callable[[int, int], bool],
    ask_give_item: Callable[[str, int, int], bool],
    items_catalog: Optional[Mapping[str, dict]] = None,
    ) -> EventResult:
    """
    Apply a special event embedded in a choice. Pure logic:
    - Uses UI hooks to ask the user (no prints here).
    - Mutates session/player state (gold, inventory, rapport) as needed.
    - Returns EventResult so UI can display a coherent message.

    Supported payload examples:
      {"type":"ask_gold", "amount":5, "pay_rapport":2, "refuse_rapport":-1,
       "join_on_pay":false, "flee_on_refuse":false, "message":"..."}
      {"type":"ask_item", "item":"leaf_of_life", "amount":1, "consume":true,
       "give_rapport":2, "decline_rapport":0, "join_on_give":false, "message":"..."}
      {"type":"trap", "penalty_rapport":2, "flee_chance":0.25, "message":"..."}
    """
    # stub minimal: wire the structure, fill later with your current logic
    etype = str(payload.get("type", "")).lower()

    if etype == "ask_gold":
        amount = int(payload.get("amount", 0))
        if amount <= 0:
            return EventResult(applied=False, message="No gold requested.")
        can = self.player.gold >= amount
        ok = ask_pay(amount, self.player.gold) if can else False
        if ok:
            self.player.gold -= amount
            dr = int(payload.get("pay_rapport", 0))
            self.rapport = max(self.rapport + dr, self.rapport)  # clamp later if needed
            return EventResult(applied=True, message="Gold paid.", delta_rapport=dr, consumed_gold=amount,
                               join_now=bool(payload.get("join_on_pay", False)))
        else:
            dr = int(payload.get("refuse_rapport", 0))
            self.rapport += dr
            fled = bool(payload.get("flee_on_refuse", False))
            if fled:
                self.in_progress = False
                self.fled = True
            return EventResult(applied=True, message="Refused to pay.", delta_rapport=dr, fled_now=fled)

    if etype == "ask_item":
        item_id = str(payload.get("item", ""))
        amt = int(payload.get("amount", 1))
        consume = bool(payload.get("consume", True))
        have = self.player.count_item(item_id)
        ok = have >= amt and ask_give_item(item_id, amt, have)
        if ok:
            if consume:
                self.player.remove_item(item_id, amt)
            dr = int(payload.get("give_rapport", 0))
            self.rapport += dr
            return EventResult(applied=True, message="Item given.", delta_rapport=dr,
                               consumed_items={item_id: amt},
                               join_now=bool(payload.get("join_on_give", False)))
        else:
            dr = int(payload.get("decline_rapport", 0))
            self.rapport += dr
            return EventResult(applied=True, message="Did not give the item.", delta_rapport=dr)

    if etype == "trap":
        dr = -abs(int(payload.get("penalty_rapport", 1)))
        self.rapport += dr
        # flee chance
        import random as _r
        fled = _r.random() < float(payload.get("flee_chance", 0.0))
        if fled:
            self.in_progress = False
            self.fled = True
        return EventResult(applied=True, message="It was a trap.", delta_rapport=dr, fled_now=fled)

    # Unknown event type
    return EventResult(applied=False, message="No event applied.")




    def process_answer(self, effect: Dict[str, int]) -> ReactionFeedback:
        """
        Apply the chosen effect to stance and session state, then build a ReactionFeedback
        object for the UI layer. Pure logic: no prints, no input().

        Steps:
        1) Read deltas (dLC, dLD) and apply to stance; clamp.
        2) Ask demon to react -> dRapport; clamp rapport.
        3) Advance turn and relax player's posture toward core.
        4) Compute Manhattan distance delta (negative => closer).
        5) Derive tone and personality cue (using registries if available).
        6) Derive liked/disliked tags from personality weights (best-effort).

        Returns:
        ReactionFeedback dataclass.
        """
        # --- Pre-state ---
        stance = self.player.stance_alignment
        demon_align = self.demon.alignment
        dist_before = stance.manhattan_distance(demon_align)
        rapport_before = self.rapport

        # --- 1) Stance deltas ---
        d_lc = int(effect.get("dLC", 0))
        d_ld = int(effect.get("dLD", 0))
        stance.law_chaos += d_lc
        stance.light_dark += d_ld
        stance.clamp()

        # --- 2) Demon reaction -> rapport delta (personality may influence inside .react) ---
        d_rep, _ = self.demon.react(effect)
        self.rapport = max(RAPPORT_MIN, min(RAPPORT_MAX, self.rapport + int(d_rep)))

        # --- 3) Advance turn & relax posture ---
        self.turns_left -= 1
        self.player.relax_posture()

        # --- 4) Distance delta (after relaxation is more informative for the player) ---
        dist_after = stance.manhattan_distance(demon_align)
        delta_distance = dist_after - dist_before  # negative means closer

        # --- 5) Tone & cue ---
        tone = tone_from_delta(int(d_rep))
        # try to use loaded cues; fall back to simple ellipsis
        try:
            # your loader should expose a dict like: {"PLAYFUL": {"Pleased": "...", ...}, ...}
            from drlite.data.loaders import PERSONALITY_CUES  # type: ignore
            cue = flavor_cue(self.demon.personality, tone, PERSONALITY_CUES, default="…")
        except Exception:
            cue = "…"

        # --- 6) Tag sentiment (liked/disliked) using personality weights, best-effort ---
        raw_tags = effect.get("tags", [])
        tags = ensure_list_of_str(raw_tags)
        tags = [t.lower() for t in tags]

        liked: list[str] = []
        disliked: list[str] = []
        try:
            # weights example: {"PLAYFUL": {"mercy": +1.0, "order": -0.5, ...}, ...}
            from drlite.data.loaders import PERSONALITY_WEIGHTS  # type: ignore
            pkey = getattr(self.demon.personality, "name", str(self.demon.personality))
            weights = PERSONALITY_WEIGHTS.get(str(pkey), {})
            for t in tags:
                w = float(weights.get(t, 0.0))
                if w > 0:
                    liked.append(t)
                elif w < 0:
                    disliked.append(t)
        except Exception:
            # no weights loaded; leave both empty
            pass

        # --- 7) Build feedback object (notes are optional/debug-friendly) ---
        notes = [
            f"Δ Stance: LC {d_lc:+}, LD {d_ld:+}",
            f"Rapport: {rapport_before} → {self.rapport}",
            f"Distance: {dist_before} → {dist_after} ({delta_distance:+})",
        ]

        fb = ReactionFeedback(
            tone=tone,
            cue=cue,
            delta_rapport=int(d_rep),
            delta_distance=int(delta_distance),
            liked_tags=liked,
            disliked_tags=disliked,
            notes=notes,
        )
        self.last_feedback = fb  # optional: keep for UI to query
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
        """
        If recruited, add demon to roster and mark unavailable.
        No printing here; UI layer reports outcome.
        """
        if self.recruited:
            if self.demon not in self.player.roster:
                self.player.roster.append(self.demon)
            if hasattr(self.demon, "available"):
                self.demon.available = False

    def maybe_trigger_whim(
        self,
        whims: Optional[list[dict]] = None,
    ) -> Optional[WhimResult]:
        """
        Roll and optionally apply a demon 'whim' (caprice). Pure logic, no prints.
        Example whim entry (JSON):
        {"id":"w_tease", "chance":0.15, "delta_rapport":-1, "message":"teases you."}
        """
        if not whims:
            return None
        r = self.rng or random
        # simple pick: try each whim by chance
        for w in whims:
            chance = float(w.get("chance", 0.0))
            if chance > 0 and r.random() < chance:
                dr = int(w.get("delta_rapport", 0))
                dt = int(w.get("delta_turns", 0))
                self.rapport += dr
                self.turns_left += dt
                return WhimResult(triggered=True, message=str(w.get("message","")), delta_rapport=dr, delta_turns=dt)
        return None

    def finish_fled(self) -> None:
        """
        If fled, finalize session flags (pure state).
        """
        if self.fled:
            self.in_progress = False


