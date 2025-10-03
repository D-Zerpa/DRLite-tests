from __future__ import annotations
import json, random
from typing import Optional

RAPPORT_MIN, RAPPORT_MAX = -3, 3
AXIS_MIN, AXIS_MAX       = -5, 5
TOL_MIN, TOL_MAX         = 1, 5
RNG_SEED: Optional[int]  = None
ROUND_DELAY_SEC          = 0
SAVE_PATH                = "saves/slot1.json"

def load_config(path: str = "config.json") -> None:
    """Load global limits/seed/UI from JSON; keep behavior identical to your current version."""
    global RAPPORT_MIN, RAPPORT_MAX, AXIS_MIN, AXIS_MAX
    global TOL_MIN, TOL_MAX, RNG_SEED, ROUND_DELAY_SEC
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        print(f"[config] {path} not found. Using defaults.")
        return

    def g(d, keys, default=None):
        cur = d
        for k in keys:
            if not isinstance(cur, dict) or k not in cur: return default
            cur = cur[k]
        return cur

    rmin = g(cfg, ["rapport","min"], RAPPORT_MIN); rmax = g(cfg, ["rapport","max"], RAPPORT_MAX)
    amin = g(cfg, ["alignment","min"], AXIS_MIN);  amax = g(cfg, ["alignment","max"], AXIS_MAX)
    tmin = g(cfg, ["tolerance","min"], TOL_MIN);   tmax = g(cfg, ["tolerance","max"], TOL_MAX)
    seed = cfg.get("rng_seed", RNG_SEED)
    delay = g(cfg, ["ui","round_delay_seconds"], ROUND_DELAY_SEC)

    if rmin >= rmax: raise ValueError("rapport.min must be < rapport.max")
    if amin >= amax: raise ValueError("alignment.min must be < alignment.max")
    if tmin >= tmax: raise ValueError("tolerance.min must be < tolerance.max")

    RAPPORT_MIN, RAPPORT_MAX = int(rmin), int(rmax)
    AXIS_MIN, AXIS_MAX       = int(amin), int(amax)
    TOL_MIN, TOL_MAX         = int(tmin), int(tmax)
    ROUND_DELAY_SEC          = int(delay or 0)
    RNG_SEED                 = int(seed) if seed is not None else None

    if RNG_SEED is not None:
        random.seed(RNG_SEED)
        print(f"[config] RNG seeded with {RNG_SEED}")

    print(f"[config] Loaded. Rapport {RAPPORT_MIN}..{RAPPORT_MAX}, "
          f"Alignment {AXIS_MIN}..{AXIS_MAX}, Tolerance {TOL_MIN}..{TOL_MAX}, "
          f"Delay {ROUND_DELAY_SEC}s.")
