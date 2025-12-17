from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Any, Callable
import random

from drlite.config import RAPPORT_MIN, RAPPORT_MAX, ROUND_DELAY_SEC
from drlite.models import Player, Demon, Question, ReactionFeedback, EventResult, WhimResult, Rarity
from drlite.data.types import ItemDef
from drlite.utils import weighted_choice, tone_from_delta, flavor_cue, ensure_list_of_str, resolve_event_ref, canonical_item_id


@dataclass
class NegotiationSession:

    player: Player
    demon: Demon
    question_pool: List[Question]
    items_catalog: Dict[str, ItemDef]
    events_registry: Dict[str, Any]

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
            raw = input("Elige una opción: ").strip()
            if raw.isdigit():
                i = int(raw)
                if 1 <= i <= len(options):
                    _, effect = options[i - 1]

                    # 3) Merge question-level tags into the effect (without mutating the pool)
                    eff_copy = dict(effect)
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

    def _get_demand_multiplier(self) -> float:
        """
        Define how picky is the Demon
        """
        multipliers = {
            Rarity.COMMON: 1.0,      # x1 (Base)
            Rarity.UNCOMMON: 1.5,    # x1.5
            Rarity.RARE: 3.0,        # x3
            Rarity.EPIC: 5.0,        # x5
            Rarity.LEGENDARY: 10.0   # x10
        }
        return multipliers.get(self.demon.rarity, 1.0)

    def process_event(
        self, 
        whim_trigger: Dict[str, Any], 
        ask_yes_no: Callable,
        ask_pay: Callable,
        ask_give_item: Callable) -> EventResult:
        
        # 1. Hydrate
        event_id = whim_trigger.get("id")
        event_data = self.events_registry.get(event_id, whim_trigger)
        
        w_type = event_data.get("type")
        multiplier = self._get_demand_multiplier()
        
        # Base Text
        print(f"\n[Evento] {event_data.get('text', '...')}")

        # ======================================================================
        # ASK_GOLD
        # ======================================================================
        if w_type == "ask_gold":
            base_amt = event_data.get("amount", 100)
            amount = max(10, int(base_amt * multiplier)) # Escalado

            if ask_pay(amount, self.player.gold):
                if self.player.gold >= amount:
                    self.player.change_gold(-amount)
                    self.rapport += event_data.get("success_rapport", 5)
                    return EventResult(True, f"Pagaste {amount} Macca.")
                else:
                    self.rapport += event_data.get("fail_rapport", -5)
                    return EventResult(False, "No tienes suficiente dinero.")
            else:
                self.rapport += event_data.get("refuse_rapport", -2)
                return EventResult(False, "Te negaste a pagar.")

        # ======================================================================
        #  ASK_ITEM
        # ======================================================================
        elif w_type == "ask_item":
            # 1. Determine pickyness of the demon
            target_rarity_str = event_data.get("target_rarity", "COMMON").upper()
            
            # 2. Filter items from the catalogue
            candidates = []
            for pid, pdef in self.items_catalog.items():
                r_val = "COMMON"
                if hasattr(pdef, "rarity"):
                    r_val = getattr(pdef.rarity, "name", str(pdef.rarity))

                elif isinstance(pdef, dict):
                    r_val = str(pdef.get("rarity", "COMMON"))

                if r_val.upper() == target_rarity_str:
                    candidates.append(pid)

            
            # Fallback: If there are no items, fails
            if not candidates:
                candidates = list(self.items_catalog.keys())
                
            if not candidates:
                return EventResult(True, "(El demonio quería pedir algo, pero no existen items en el juego)")

            # 3. Pick random item
            item_id = self.rng.choice(candidates)
            
            # 4. Quantity
            base_qty = event_data.get("quantity", 1)
            qty = max(1, int(base_qty * (0.5 + (multiplier / 2))))

            # 5. Petition
            has_it = self.player.has_item(item_id, qty)
            curr_qty = self.player.inventory.get(item_id, 0)
            
            print(f"[Sistema] El demonio señala tu: {item_id} (Pide {qty})")
            
            if ask_give_item(item_id, qty, curr_qty):
                if has_it:
                    self.player.remove_item(item_id, qty)
                    self.rapport += event_data.get("success_rapport", 10)
                    return EventResult(True, f"Entregaste {qty}x {item_id}.")
                else:
                    self.rapport += event_data.get("fail_rapport", -5)
                    return EventResult(False, "No tienes el objeto.")
            else:
                self.rapport += event_data.get("refuse_rapport", -2)
                return EventResult(False, "Te negaste a dar el objeto.")

        # ======================================================================
        #  ASK_HP
        # ======================================================================
        elif w_type == "ask_hp":
            base_amt = event_data.get("amount", 10)
            # El daño escala con rareza
            cost = int(base_amt * multiplier)
            
            # Usamos ask_yes_no. Texto informativo.
            print(f"[Sistema] Costo: {cost} HP (Tu HP actual: {self.player.hp})")
            
            if ask_yes_no(f"¿Permites que drene tu energía?"):
                # Verificamos si sobreviviría (opcional, o dejamos que muera)
                if self.player.hp <= cost:
                    # El jugador acepta morir
                    self.player.change_hp(-cost)
                    return EventResult(False, "¡Te drenó toda la vida! (HP 0)")
                
                self.player.change_hp(-cost)
                self.rapport += event_data.get("success_rapport", 15)
                return EventResult(True, f"Sacrificaste {cost} HP.")
            else:
                self.rapport += event_data.get("refuse_rapport", -5)
                return EventResult(False, "Protegiste tu vida.")


        # ======================================================================
        #  ASK_MP
        # ======================================================================
        elif w_type == "ask_mp":
            base_amt = event_data.get("amount", 5)
            cost = int(base_amt * multiplier)

            print(f"[Sistema] Costo: {cost} MP (Tu MP actual: {self.player.mp})")

            if ask_yes_no("¿Compartes tu Mana?"):
                if self.player.mp >= cost:
                    self.player.change_mp(-cost)
                    self.rapport += event_data.get("success_rapport", 10)
                    return EventResult(True, f"Cediste {cost} MP.")
                else:
                    self.rapport += event_data.get("fail_rapport", -5)
                    return EventResult(False, "No tienes suficiente MP.")
            else:
                self.rapport += event_data.get("refuse_rapport", -2)
                return EventResult(False, "Te negaste.")


        # ======================================================================
        #  GAMBLE
        # ======================================================================
        elif w_type == "gamble":
            cost = int(event_data.get("amount", 100) * multiplier)
            
            if ask_pay(cost, self.player.gold):
                if self.player.gold >= cost:
                    self.player.change_gold(-cost)
                    
                    # 50% Gana item, 50% Nada
                    if self.rng.random() > 0.5:
                        # Gana algo (reutilizamos lógica de reward)
                        self._give_item_reward() # Método que creamos antes
                        self.rapport += 5
                        return EventResult(True, "¡Ganaste la apuesta!")
                    else:
                        self.rapport -= 2 # Se burla de ti
                        return EventResult(False, "El demonio se ríe. No obtuviste nada.")
                else:
                    return EventResult(False, "No tienes dinero para apostar.")
            else:
                return EventResult(False, "Ignoraste la apuesta.")

        # ======================================================================
        #  TRAMPA
        # ======================================================================
        elif w_type == "trap":
            base_dmg = event_data.get("damage_rapport", 5)
            dmg = int(base_dmg * (1 + (multiplier * 0.2)))
            self.rapport -= dmg
            return EventResult(False, f"¡Trampa! Perdiste {dmg} de afinidad.")

        return EventResult(True, "Evento desconocido o sin efecto.")


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
        Final cleanup when negotiation succeeds.
        Branching Logic:
        - If new demon: Recruit.
        - If existing demon: Give Reward (Macca/Items).
        """
        self.player.relax_posture()
        
        xp_gain = int(20 * self._get_demand_multiplier())
        lvl_up = self.player.gain_exp(xp_gain)
        
        print(f"\n[Progreso] ¡Ganaste {xp_gain} XP!")
        if lvl_up:
            print(f"[!!!] ¡LEVEL UP! Ahora eres Nivel {self.player.lvl}")
            print(f"      HP: {self.player.max_hp} | MP: {self.player.max_mp}")

        # Check if the player already has this demon
        if self.player.has_demon(self.demon.id):
            self._give_duplicate_reward()
        else:
            # Here we just mark the success state.
            print(f"\n{self.demon.name}: 'Excelente, me uniré a tu equipo'")

    

    def _give_duplicate_reward(self) -> None:
        """
        Define if the reward is Macca or Items.
        """

        print(f"\n{self.demon.name}: 'Ya viajamos juntos. Toma esto para el camino.'")
        
        # 50% Macca / 50% Item
        if self.rng.random() < 0.5:
            self._give_macca_reward()
        else:
            self._give_item_reward()
        

    def _give_macca_reward(self):
        """ 
        Scalar logic for Macca giving.
        """
        ranges = {
            Rarity.COMMON:    (10, 50),
            Rarity.UNCOMMON:  (50, 150),
            Rarity.RARE:      (150, 400),
            Rarity.EPIC:      (400, 1000),
            Rarity.LEGENDARY: (1000, 5000)
        }
        min_v, max_v = ranges.get(self.demon.rarity, (10, 50))
        amount = self.rng.randint(min_v, max_v)
        
        self.player.change_gold(amount)
        print(f"[Recompensa] ¡El demonio te dio {amount} Macca!")

    def _give_item_reward(self):
        """
        Scalar logic for items:
        - Common: 1x Common
        - Uncommon: 1x Uncommon O 2x Common
        - Rare: 1x Rare O 2x Uncommon O 4x Common
        """
       
        rarity_tiers = {
            Rarity.COMMON: 0, 
            Rarity.UNCOMMON: 1, 
            Rarity.RARE: 2, 
            Rarity.EPIC: 3, 
            Rarity.LEGENDARY: 4
        }
        
        demon_tier = rarity_tiers.get(self.demon.rarity, 0)
        
        # Let the demon choose which kind of item to give, depending on their rarity.
        target_item_tier = self.rng.randint(0, demon_tier)
        
        # Determine the quantity of items they'll give.
        quantity = 2 ** (demon_tier - target_item_tier)
        
        tier_to_rarity = {v: k for k, v in rarity_tiers.items()}
        target_rarity_enum = tier_to_rarity.get(target_item_tier, Rarity.COMMON)
        
        # Filter in the catalogue.
        candidates = [
            (pid, pdef) for pid, pdef in self.items_catalog.items()
            if pdef.rarity == target_rarity_enum]

        # Security fallback.
        if not candidates:
            target_rarity_enum = Rarity.COMMON
            candidates = [
                (pid, pdef) for pid, pdef in self.items_catalog.items()
                if pdef.rarity == Rarity.COMMON
            ]
            
        if candidates:
            chosen_id, chosen_def = self.rng.choice(candidates)
            self.player.add_item(chosen_id, quantity)
            # Usamos .name para mostrar "COMMON", "RARE", etc.
            print(f"[Reward] Recibiste {quantity}x {chosen_def.display_name} ({target_rarity_enum.name})!")
        else:
            print("[System] (El demonio no encontró nada útil...)")
            self._give_macca_reward()
    

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


