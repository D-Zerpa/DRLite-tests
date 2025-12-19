from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Any, Callable
import random

from drlite.data.types import ItemDef
from drlite.config import RAPPORT_MIN, RAPPORT_MAX
from drlite.models import Player, Demon, Question, ReactionFeedback, EventResult, Rarity, Personality
from drlite.ui.console import clear_screen
from drlite.utils import tone_from_delta, flavor_cue, ensure_list_of_str

# Constants
RNG_SEED = None 

@dataclass
class NegotiationSession:

    player: Player
    demon: Demon
    question_pool: List[Question]
    items_catalog: Dict[str, Any] # Changed to Any to handle potential dicts/ItemDefs
    events_registry: Dict[str, Any]

    # State
    rapport: int = 0 
    turns_left: int = field(init=False)
    in_progress: bool = True
    recruited: bool = False
    fled: bool = False
    round_no: int = 1
    rng: Optional[random.Random] = None

    # Patience and tolerance
    max_rounds: int = field(init=False)
    current_tolerance: int = field(init=False)

    # Avoid repeating questions within the session
    last_feedback: Optional[ReactionFeedback] = field(default=None, repr=False)
    _used_question_ids: Set[str] = field(default_factory = set, repr = False)

    def __post_init__(self):
        """Initialize values that depend on demon at runtime."""
        self.max_rounds = getattr(self.demon, "patience", 5)
        self.turns_left = self.max_rounds
        self.current_tolerance = getattr(self.demon, "tolerance", 3)
        
        if self.rng is None:
            try:
                self.rng = random.Random(RNG_SEED) if RNG_SEED is not None else random.Random()
            except NameError:
                self.rng = random.Random()

    # --- SAFE HELPERS (Para evitar el error 'dict object has no attribute rarity') ---
    def _get_item_rarity_name(self, item_data: Any) -> str:
        """Safely extracts rarity name from ItemDef object or dict."""
        val = None
        if isinstance(item_data, dict):
            val = item_data.get("rarity", "COMMON")
        else:
            val = getattr(item_data, "rarity", "COMMON")
        return val.name if hasattr(val, "name") else str(val)

    def _get_item_display(self, item_data: Any) -> str:
        if isinstance(item_data, dict):
            return item_data.get("display_name", "Unknown Item")
        return getattr(item_data, "display_name", "Unknown Item")
    
    def _is_item_rarity(self, item_data: Any, target_rarity_name: str) -> bool:
        r_name = self._get_item_rarity_name(item_data)
        return r_name.upper() == target_rarity_name.upper()
    # -------------------------------------------------------------------------------

    def pick_question(self) -> Optional[Question]:
        if not self.question_pool:
            return None
            
        # Identify Target Tags based on Personality
        preferred_tags = []
        p_name = self.demon.personality.name if hasattr(self.demon.personality, "name") else str(self.demon.personality)
        p_name = p_name.upper()
        
        if "IRRITABLE" in p_name: preferred_tags = ["AGGRESSIVE", "POWER", "DIRECT"]
        elif "TIMID" in p_name: preferred_tags = ["GENTLE", "SCARED", "SAFETY"]
        elif "UPBEAT" in p_name: preferred_tags = ["FUN", "SOCIAL", "HOBBY"]
        elif "GLOOMY" in p_name: preferred_tags = ["DEATH", "SADNESS", "MEANING"]
        elif "CUNNING" in p_name: preferred_tags = ["TRICK", "VALUE", "SMART"]
        elif "PLAYFUL" in p_name: preferred_tags = ["FUN", "JOKE", "GAME"]
        elif "PROUD" in p_name: preferred_tags = ["HONOR", "POWER", "RESPECT"]
            
        candidates = []
        for q in self.question_pool:
            if q.id in self._used_question_ids:
                continue
            if any(tag in q.tags for tag in preferred_tags):
                candidates.append(q)
        
        if not candidates:
            candidates = [q for q in self.question_pool if q.id not in self._used_question_ids]
            
        if not candidates:
            return None 

        selected = self.rng.choice(candidates)
        self._used_question_ids.add(selected.id)
        return selected

    def _get_demand_multiplier(self) -> float:
        multipliers = { "COMMON": 1.0, "UNCOMMON": 1.5, "RARE": 3.0, "EPIC": 5.0, "LEGENDARY": 10.0 }
        r_name = self.demon.rarity.name if hasattr(self.demon.rarity, "name") else str(self.demon.rarity)
        return multipliers.get(r_name.upper(), 1.0)

    def _resolve_text(self, content: Any) -> str:
        if isinstance(content, str): return content
        if isinstance(content, dict):
            p_name = self.demon.personality.name if hasattr(self.demon.personality, "name") else str(self.demon.personality)
            return content.get(p_name.upper(), content.get("DEFAULT", "..."))
        return "..."

    def process_event(self, whim_trigger: Dict[str, Any], ask_yes_no: Callable, ask_pay: Callable, ask_give_item: Callable) -> EventResult:
        """Executes a random event (Whim)."""
        event_id = whim_trigger.get("id")
        event_data = self.events_registry.get(event_id, whim_trigger)
        
        w_type = event_data.get("type")
        if w_type == "ask_gold": w_type = "ask_pay" 

        multiplier = self._get_demand_multiplier()
        msg_success = self._resolve_text(event_data.get("success_msg", "¡Bien!"))
        msg_fail = self._resolve_text(event_data.get("fail_msg", "Mal..."))
        
        target_item_id = event_data.get("item_id")
        target_item_name = "Objeto"
        
        if w_type == "ask_item":
            req_rarity = event_data.get("target_rarity")
            if req_rarity == "DYNAMIC":
                r_name = self.demon.rarity.name if hasattr(self.demon.rarity, "name") else str(self.demon.rarity)
                req_rarity = r_name
            
            if req_rarity:
                # Priority: Inventory -> Fallback: Catalog
                owned_candidates = [inv_id for inv_id in self.player.inventory.keys() 
                                    if self.items_catalog.get(inv_id) and self._is_item_rarity(self.items_catalog[inv_id], req_rarity)]
                
                if owned_candidates:
                    target_item_id = self.rng.choice(owned_candidates)
                else:
                    all_candidates = [cat_id for cat_id, cat_def in self.items_catalog.items() 
                                      if self._is_item_rarity(cat_def, req_rarity)]
                    target_item_id = self.rng.choice(all_candidates) if all_candidates else "life_stone"

            if target_item_id and target_item_id in self.items_catalog:
                target_item_name = self._get_item_display(self.items_catalog[target_item_id])

        raw_text = self._resolve_text(event_data.get("text", "..."))
        final_text = raw_text.replace("{item}", target_item_name)
        print(f"\n[{self.demon.name}]: {final_text}")

        # HANDLERS
        if w_type == "ask_pay":
            amount = max(10, int(event_data.get("amount", 100) * multiplier))
            if ask_pay(amount, self.player.gold):
                if self.player.gold >= amount:
                    self.player.change_gold(-amount)
                    d_rap = event_data.get("reward_rapport", 10)
                    self.rapport += d_rap
                    return EventResult(True, msg_success, d_rap, "HAPPY")
                return EventResult(False, "No tienes suficiente Macca.", event_data.get("penalty_rapport", -5), "ANGRY")
            return EventResult(False, msg_fail, event_data.get("penalty_rapport", -2), "ANGRY")

        elif w_type == "ask_item":
            qty = max(1, int(event_data.get("amount", 1)))
            has_it = self.player.has_item(target_item_id, qty)
            if ask_give_item(target_item_name, qty, self.player.inventory.get(target_item_id, 0)):
                if has_it:
                    self.player.remove_item(target_item_id, qty)
                    d_rap = event_data.get("reward_rapport", 15)
                    self.rapport += d_rap
                    return EventResult(True, msg_success, d_rap, "HAPPY")
                return EventResult(False, f"No tienes {target_item_name}.", event_data.get("penalty_rapport", -5), "ANGRY")
            return EventResult(False, msg_fail, event_data.get("penalty_rapport", -5), "ANGRY")

        elif w_type == "ask_hp":
            cost = int(event_data.get("amount", 10) * multiplier)
            if ask_yes_no(f"¿Sacrificar {cost} HP?"):
                if self.player.hp > cost:
                    self.player.change_hp(-cost)
                    d_rap = event_data.get("reward_rapport", 15)
                    self.rapport += d_rap
                    return EventResult(True, msg_success, d_rap, "HAPPY")
                return EventResult(False, "Morirías si hicieras eso.", 0, "NEUTRAL")
            return EventResult(False, msg_fail, event_data.get("penalty_rapport", -5), "ANGRY")

        elif w_type == "ask_mp":
            cost = int(event_data.get("amount", 5) * multiplier)
            if ask_yes_no(f"¿Drenar {cost} MP?"):
                if self.player.mp >= cost:
                    self.player.change_mp(-cost)
                    d_rap = event_data.get("reward_rapport", 15)
                    self.rapport += d_rap
                    return EventResult(True, msg_success, d_rap, "HAPPY")
                return EventResult(False, "No tienes suficiente MP.", event_data.get("penalty_rapport", -5), "BORED")
            return EventResult(False, msg_fail, event_data.get("penalty_rapport", -5), "ANGRY")

        elif w_type == "gamble":
            cost = int(event_data.get("amount", 100) * multiplier)
            if ask_pay(cost, self.player.gold):
                if self.player.gold >= cost:
                    self.player.change_gold(-cost)
                    if self.rng.random() > 0.5:
                        d_rap = event_data.get("reward_rapport", 10)
                        self.rapport += d_rap
                        return EventResult(True, msg_success, d_rap, "HAPPY")
                    d_rap = event_data.get("penalty_rapport", -5)
                    self.rapport += d_rap
                    return EventResult(False, msg_fail, d_rap, "HAPPY")
                return EventResult(False, "No tienes suficiente dinero.", 0, "BORED")
            return EventResult(False, "Decidiste no apostar.", 0, "NEUTRAL")

        return EventResult(True, "Evento desconocido.")

    # --- PROCESS ANSWER: EL NÚCLEO HÍBRIDO ---
    def process_answer(
        self, 
        question: Question,
        choice_idx: int,
        personality_cues: Dict[str, Dict[str, str]],
        personality_weights: Dict[str, Dict[str, float]]) -> ReactionFeedback:
        """
        Calculates Score using a Hybrid System:
        1. Base Value: Uses 'dRapport' from the question JSON (Essential for existing data).
        2. Alignment Bonus: +3 if player moves towards Demon's ideology.
        3. Personality Bonus: Extra points if tags match weights.
        """
        if choice_idx < 0 or choice_idx >= len(question.responses):
            return ReactionFeedback("NEUTRAL", "...", 0, 0, [], [], ["Invalid choice"])

        resp_text, effect = question.responses[choice_idx]

        # 1. State
        stance = self.player.stance_alignment
        demon_align = self.demon.alignment
        dist_before = stance.manhattan_distance(demon_align)

        # 2. Stance Shift
        d_lc = int(effect.get("dLC", 0))
        d_ld = int(effect.get("dLD", 0))
        stance.law_chaos += d_lc
        stance.light_dark += d_ld
        stance.law_chaos = max(-10, min(10, stance.law_chaos))
        stance.light_dark = max(-10, min(10, stance.light_dark))

        # 3. SCORE CALCULATION (THE FIX)
        # Start with the base value from JSON (e.g., 10, 15)
        d_rep = int(effect.get("dRapport", 0))
        
        # A. Alignment Factor (Intention)
        if (demon_align.law_chaos < 0 and d_lc < 0) or (demon_align.law_chaos > 0 and d_lc > 0):
            d_rep += 3
        if (demon_align.light_dark < 0 and d_ld < 0) or (demon_align.light_dark > 0 and d_ld > 0):
            d_rep += 3
            
        # B. Personality Factor (Tags)
        tags = ensure_list_of_str(effect.get("tags", []))
        if question.tags: tags.extend(question.tags)
        
        liked, disliked = [], []
        p_name = self.demon.personality.name if hasattr(self.demon.personality, "name") else str(self.demon.personality)
        current_weights = personality_weights.get(p_name.upper(), personality_weights.get("DEFAULT", {}))

        for tag in tags:
            weight = current_weights.get(tag.upper(), 0.0)
            if weight != 0:
                points = int(5 * weight)
                d_rep += points
                (liked if weight > 0 else disliked).append(tag)

        # C. Variance
        if self.rng: d_rep += self.rng.randint(-1, 2)
        
        # 4. Update
        self.rapport = max(RAPPORT_MIN, min(RAPPORT_MAX, self.rapport + int(d_rep)))
        self.turns_left -= 1

        # 5. Metrics
        dist_after = stance.manhattan_distance(demon_align)
        tone = tone_from_delta(int(d_rep))
        
        if tone == "ANGRY": self.current_tolerance -= 1

        try:
            cue = flavor_cue(self.demon.personality, tone, personality_cues, default="...")
        except Exception: cue = "…"

        fb = ReactionFeedback(
            tone=tone, cue=cue, delta_rapport=int(d_rep), 
            delta_distance=int(dist_after - dist_before),
            liked_tags=liked, disliked_tags=disliked, 
            notes=[f"Total Score: {d_rep} (Base JSON: {effect.get('dRapport',0)})"]
        )
        self.last_feedback = fb  
        return fb

    def difficulty(self, level: int) -> None:
        drop = self.rng.randint(0, max(0, level // 2))
        self.rapport = max(RAPPORT_MIN, self.rapport - drop)
        if self.rng.random() < (level / 10.0):
            axis = self.rng.choice(("law_chaos", "light_dark"))
            s = getattr(self.player.stance_alignment, axis)
            d = getattr(self.demon.alignment, axis)
            if s < d: setattr(self.player.stance_alignment, axis, s - 1)
            elif s > d: setattr(self.player.stance_alignment, axis, s + 1)
            self.player.stance_alignment.clamp()

    def check_union(self) -> None:
        if not self.in_progress: return
        
        # Stance Check (Optional: strict distance vs tolerance)
        stance_ok = (self.player.stance_alignment.manhattan_distance(self.demon.alignment) <= 5)
        rapport_ok = (self.rapport >= self.demon.rapport_needed)

        if rapport_ok and stance_ok:
            if any(d.id == self.demon.id for d in self.player.roster):
                self.in_progress = False
                self.recruited = False 
                print(f"\n[Info] {self.demon.name} ya está en tu equipo. Se marcha satisfecho.") 
                self._give_duplicate_reward()
            else:
                self.recruited = True
                self.in_progress = False
                self.finish_union()
            return
            
        if self.current_tolerance <= 0:
            self.in_progress = False
            self.turns_left = 0
            print(f"\n[{self.demon.name}]: ¡Se acabó mi paciencia con tus estupideces! (Tolerancia agotada)")
        elif self.turns_left <= 0:
            self.in_progress = False
            self.fled = True 
            print(f"\n[{self.demon.name}]: Me aburrí. Me largo.")

    def attempt_bribe(self) -> str:
        multiplier = self._get_demand_multiplier()
        cost = int(100 * multiplier)
        if self.player.gold < cost: return f"Necesitas {cost} Macca."

        self.player.change_gold(-cost)
        base_chance = 0.30 + (self.rapport * 0.05)
        
        p_str = str(self.demon.personality).upper()
        p_mod = 0.20 if "CUNNING" in p_str else (0.10 if "IRRITABLE" in p_str else (-0.10 if "UPBEAT" in p_str else 0))
        
        r_str = str(self.demon.rarity).upper()
        r_pen = 0.4 if "LEGENDARY" in r_str else (0.2 if "EPIC" in r_str else (0.1 if "RARE" in r_str else 0))

        if self.rng.random() < (base_chance + p_mod - r_pen):
            self.recruited = True
            self.finish_union()
            self.in_progress = False
            return f"Le diste {cost} Macca. {self.demon.name} aprueba."
        
        self.fled = True
        self.in_progress = False
        return f"Pagaste {cost} Macca, pero {self.demon.name} huyó con el dinero."

    def attempt_flee(self) -> str:
        self.fled = True
        self.in_progress = False
        hit_chance = 0.3
        p_str = str(self.demon.personality).upper()
        if "IRRITABLE" in p_str: hit_chance = 0.8
        elif "TIMID" in p_str: hit_chance = 0.1
        
        if self.rng.random() < hit_chance:
            self.player.change_hp(-15)
            return f"Huiste, pero {self.demon.name} te atacó."
        return "Escapaste."

    def finish_union(self) -> None:
        self.player.relax_posture()
        clear_screen()
        print("\n" + "="*40 + "\n ¡NEGOCIACIÓN EXITOSA! \n" + "="*40)
        xp = int(20 * self._get_demand_multiplier())
        
        if hasattr(self.player, "gain_exp"): lvl_up = self.player.gain_exp(xp)
        else: self.player.exp += xp; lvl_up = False
        
        print(f"\n[Progreso] ¡Ganaste {xp} XP!")
        if lvl_up: print(f"[!!!] ¡LEVEL UP! -> Nivel {self.player.lvl}")
        
        print(f"\n{self.demon.name}: 'Excelente, me uniré a tu equipo'")
        self.player.roster.append(self.demon)
        print(f"[Compendio] {self.demon.name} registrado.")

    def _give_duplicate_reward(self) -> None:
        print(f"\n{self.demon.name}: 'Ya viajamos juntos. Toma esto.'")
        if self.rng.random() < 0.5: self._give_macca_reward()
        else: self._give_item_reward()

    def _give_macca_reward(self):
        ranges = {"COMMON": (10,50), "UNCOMMON": (50,150), "RARE": (150,400), "EPIC": (400,1000), "LEGENDARY": (1000,5000)}
        r_name = self._get_item_rarity_name(self.demon).upper()
        amt = self.rng.randint(*ranges.get(r_name, (10,50)))
        self.player.change_gold(amt)
        print(f"[Recompensa] ¡{amt} Macca!")

    def _give_item_reward(self):
        r_tiers = {"COMMON": 0, "UNCOMMON": 1, "RARE": 2, "EPIC": 3, "LEGENDARY": 4}
        d_tier = r_tiers.get(self._get_item_rarity_name(self.demon).upper(), 0)
        t_tier = self.rng.randint(0, d_tier)
        qty = 2 ** (d_tier - t_tier)
        t_rarity = {v: k for k, v in r_tiers.items()}.get(t_tier, "COMMON")
        
        cands = [k for k, v in self.items_catalog.items() if self._is_item_rarity(v, t_rarity)]
        if not cands: cands = [k for k, v in self.items_catalog.items() if self._is_item_rarity(v, "COMMON")]
        
        if cands:
            cid = self.rng.choice(cands)
            self.player.add_item(cid, qty)
            print(f"[Recompensa] {qty}x {self._get_item_display(self.items_catalog[cid])} ({t_rarity})!")
        else: self._give_macca_reward()

    def trigger_whim(self, whims_templates: List[dict], whim_config: Dict[str, Any]) -> Optional[str]:
        if not whims_templates: return None
        base = float(whim_config.get("base_chance", 0.0))
        p_name = self.demon.personality.name if hasattr(self.demon.personality, "name") else str(self.demon.personality)
        mod = float(whim_config.get("personality_mod", {}).get(p_name.upper(), 0.0))
        
        if self.rng.random() > (base + mod): return None
        return self.rng.choices(whims_templates, weights=[w.get("weight", 1) for w in whims_templates], k=1)[0].get("id")

    def finish_fled(self) -> None:
        if self.fled: self.in_progress = False