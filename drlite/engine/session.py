from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Any, Callable
import random

from drlite.config import RAPPORT_MIN, RAPPORT_MAX, ROUND_DELAY_SEC
from drlite.models import Player, Demon, Question, ReactionFeedback, EventResult, WhimResult
from drlite.utils import weighted_choice, tone_from_delta, flavor_cue, ensure_list_of_str, resolve_event_ref, canonical_item_id


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

    def ask(self, events_registry: Dict[str, Any]) -> Effect:
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

                    eff_copy = resolve_event_ref(eff_copy, events_registry)

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
        event: Dict[str, Any], 
        ask_yes_no: Callable[[str], bool], 
        ask_pay: Callable[[int, int], bool], 
        ask_give_item: Callable[[str, int, int], bool]
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
        etype = str(event.get("type", "")).lower()

        # --- CASE 1: ASK FOR GOLD ---
        if etype == "ask_gold":
            amount = int(event.get("amount", 0))
            if amount < 0: amount = 0 

            # Verification of quantity
            if self.player.gold < amount:
                # Demon realizes you don't have money.
                return EventResult(False, "No tienes suficiente dinero para pagar.")

            # Consult IU
            accepted = ask_pay(amount, self.player.gold)
            
            if accepted:
                # Doble verification.
                if self.player.gold >= amount:
                    self.player.gold -= amount
                    
                    # Success
                    d_rep = int(event.get("success_rapport", 1))
                    self.rapport += d_rep
                    return EventResult(True, f"Pagaste {amount} macca. (Rapport +{d_rep})")
                else:
                    return EventResult(False, "Error: Fondos insuficientes al intentar pagar.")
            else:
                # User refuses.
                return EventResult(False, "Decidiste no pagar.")

        # --- CASE 2: ASK FOR ITEMS ---
        elif etype == "ask_item":
            raw_name = str(event.get("item", "???"))
            # ID Normalization.
            item_id = canonical_item_id(raw_name) 
            amount = int(event.get("amount", 1))

            # Do you have the item?
            current_qty = self.player.inventory.get(item_id, 0)
            
            if current_qty < amount:
                # Automatic fail if you don't have the item.
                return EventResult(False, f"El demonio pide {amount}x {raw_name}, pero no tienes suficientes.")

            # Ask the UI
            accepted = ask_give_item(item_id, amount, current_qty)

            if accepted:
                # Transaction
                if self.player.inventory.get(item_id, 0) >= amount:
                    self.player.inventory[item_id] -= amount
                    # Inventory cleaning if ammount reaches 0
                    if self.player.inventory[item_id] <= 0:
                        del self.player.inventory[item_id]
                    
                    d_rep = int(event.get("success_rapport", 2))
                    self.rapport += d_rep
                    return EventResult(True, f"Entregaste {raw_name}. (Rapport +{d_rep})")
                else:
                     return EventResult(False, "Error: Ítem no disponible al intentar entregar.")
            else:
                # Cheap penalization.
                d_rep_fail = int(event.get("fail_rapport", -1))
                self.rapport += d_rep_fail
                return EventResult(False, f"Te negaste a dar el objeto. (Rapport {d_rep_fail})")

        # --- Other Events ---
        elif etype == "trap":
            damage = int(event.get("damage_rapport", -1))
            self.rapport += damage
            msg = event.get("message", "¡Es una trampa!")
            return EventResult(True, f"{msg} (Rapport {damage})")

        # Default.
        return EventResult(True, str(event.get("message", "")))


    def process_answer(
        self, 
        effect: Dict[str, Any], 
        personality_weights: Dict[str, Dict[str, int]],
        personality_cues: Dict[str, Dict[str, str]]) -> ReactionFeedback:

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
        d_rep, _ = self.demon.react(effect, personality_weights)
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
            cue = flavor_cue(self.demon.personality, tone, personality_cues, default="...")
        except Exception:
            cue = "…"

        # --- 6) Tag sentiment (liked/disliked) using personality weights, best-effort ---
        raw_tags = effect.get("tags", [])
        tags = ensure_list_of_str(raw_tags)
        tags = [t.lower() for t in tags]

        liked: list[str] = []
        disliked: list[str] = []
        try:
            p_key = getattr(self.demon.personality, "name", str(self.demon.personality))
            p_weights = personality_weights.get(p_key, {})

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
        Evaluate if negotiations are successful.
        Checks: Rapport threshold, Alignment distance, and Roster duplicates.
        """
    
        dist = self.player.stance_alignment.manhattan_distance(self.demon.alignment)
        stance_ok = (dist <= self.demon.tolerance)
        rapport_ok = (self.rapport >= self.demon.rapport_needed)

        if rapport_ok and stance_ok:
            already_have = False
            for owned in self.player.roster:
                owned_id = owned.id if hasattr(owned, "id") else str(owned)
                if owned_id == self.demon.id:
                    already_have = True
                    break
            
            if already_have:
                self.in_progress = False
                self.recruited = False 
                print(f"\n[Info] {self.demon.name} ya está en tu equipo. Se marcha satisfecho.") 
                return

            self.recruited = True
            self.in_progress = False
            

        elif self.turns_left <= 0:
            self.in_progress = False
            self.fled = True 


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

    def maybe_trigger_whim(self, whims_templates: List[dict], whim_config: Dict[str, Any]) -> Optional[dict]:
            """
            Roll for a whim but DO NOT apply it yet. Return the raw payload so 
            the controller can decide how to process it (e.g. via process_event).
            """
            if not whims_templates or not whim_config:
                return None

            base = float(whim_config.get("base_chance", 0.0))

            p_name = getattr(self.demon.personality, "name", str(self.demon.personality)).upper()
            mods = whim_config.get("personality_mod", {})
            mod = float(mods.get(p_name, 0.0))

            total_chance = base + mod

            if self.rng.random() > total_chance:
                return None

            selected_whim = weighted_choice(whims_templates, weight_key="weight")
                    
            return selected_whim

            
    def finish_fled(self) -> None:
            """
            If fled, finalize session flags (pure state).
            """
            if self.fled:
                self.in_progress = False


