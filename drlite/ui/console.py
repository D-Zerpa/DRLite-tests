import os
import sys
from typing import Optional, List
from drlite.models import Player, Demon, Rarity, Alignment

# ==============================================================================
#  CONSTANTS & STYLING
# ==============================================================================

COLORS = {
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
    "RED": "\033[91m",
    "GREEN": "\033[92m",
    "YELLOW": "\033[93m",
    "BLUE": "\033[94m",
    "MAGENTA": "\033[95m",
    "CYAN": "\033[96m",
    "WHITE": "\033[97m",
    "GREY": "\033[90m"
}

def _style(text: str, color_key: str) -> str:
    """Applies ANSI color code to text."""
    code = COLORS.get(color_key.upper(), "")
    return f"{code}{text}{COLORS['RESET']}"

def _rarity_label(rarity: Rarity) -> str:
    """Returns a colored string for the rarity."""
    # Handle both Enum object and string cases for safety
    r_name = rarity.name if hasattr(rarity, 'name') else str(rarity)
    
    # Translate and Colorize
    if r_name == "COMMON": return _style("COMÚN", "WHITE")
    if r_name == "UNCOMMON": return _style("POCO COMÚN", "GREEN")
    if r_name == "RARE": return _style("RARO", "BLUE")
    if r_name == "EPIC": return _style("ÉPICO", "MAGENTA")
    if r_name == "LEGENDARY": return _style("LEGENDARIO", "YELLOW")
    return r_name

# ==============================================================================
#  SYSTEM UTILS
# ==============================================================================

def clear_screen():
    """Clears the console screen based on OS."""
    os.system('cls' if os.name == 'nt' else 'clear')

def wait_enter(prompt: str = "(Presiona Enter para continuar)"):
    """Pauses execution until user presses Enter."""
    print(f"\n{_style(prompt, 'GREY')}")
    input()

def print_separator(char: str = "-", length: int = 60):
    """Prints a styled horizontal line."""
    print(_style(char * length, "GREY"))

# ==============================================================================
#  BANNERS & INPUTS
# ==============================================================================

def print_banner():
    """Prints the ASCII Logo."""
    clear_screen()
    logo = r"""
  _____  _____  _      _ _       
 |  __ \|  __ \| |    (_) |      
 | |  | | |__) | |     _| |_ ___ 
 | |  | |  _  /| |    | | __/ _ \
 | |__| | | \ \| |____| | ||  __/
 |_____/|_|  \_\______|_|\__\___|
    Demon Recruiter Lite
    """
    print(_style(logo, "RED"))
    print_separator()

def read_difficulty() -> str:
    """Reads initial difficulty setting (User-facing in Spanish)."""
    while True:
        print(f"\n{_style('SELECCIONA DIFICULTAD:', 'BOLD')}")
        print("1. Normal (Experiencia estándar)")
        print("2. Difícil (Menos turnos, personalidades estrictas)")
        choice = input("> ").strip()
        
        if choice == "1": return "NORMAL"
        if choice == "2": return "HARD"
        print(_style("Opción no válida.", "RED"))

def ask_yes_no(prompt: str) -> bool:
    """Generic Yes/No prompt in Spanish (s/n)."""
    while True:
        # Prompt: "Pregunta (s/n) > "
        choice = input(f"{prompt} (s/n) > ").lower().strip()
        if choice in ['s', 'si', 'sí', 'y', 'yes']: return True
        if choice in ['n', 'no']: return False

def ask_selection(options: List[str], prompt: str = "Selecciona opción") -> int:
    """
    Generic menu selection. Returns the index (0-based) of the choice.
    Returns -1 if cancel/back (if '0' is entered).
    """
    while True:
        try:
            choice = input(f"\n{prompt} > ").strip()
            if choice == '0': return -1
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return idx
        except ValueError:
            pass

# ==============================================================================
#  CARDS & HUD
# ==============================================================================

def print_dex_card(demon: Demon):
    """
    Displays a detailed card for a demon (Used in Compendium).
    """
    print_separator("=")
    r_lbl = _rarity_label(demon.rarity)
    p_lbl = _style(demon.personality.name, "CYAN")
    
    print(f" {demon.name.upper()}".ljust(40) + f"[{r_lbl}]")
    print(f" Personalidad: {p_lbl}")
    print_separator("-")
    print(f" Afinidad Necesaria: {demon.rapport_needed}")
    # Placeholder for future lore/stats
    print_separator("=")

def print_header(player: Player, demon: Optional[Demon] = None, round_no: int = 0, max_rounds: int = 0):
    """
    Main HUD (Heads Up Display).
    """
    # 1. Turn Info
    if max_rounds > 0:
        turn_str = f"Turno: {round_no}/{max_rounds}"
    else:
        turn_str = "PREPARACIÓN"

    # 2. Player Stats
    print_separator()
    name_txt = _style(f"{player.name} [Nv.{player.lvl}]", "BOLD")
    print(f" {name_txt}".ljust(40) + turn_str.rjust(30))
    
    # Color code HP (Red if critical < 30%)
    hp_color = "RED" if player.hp < player.max_hp * 0.3 else "GREEN"
    mp_color = "BLUE"
    
    hp_txt = _style(f"HP: {player.hp}/{player.max_hp}", hp_color)
    mp_txt = _style(f"MP: {player.mp}/{player.max_mp}", mp_color)
    gold_txt = _style(f"Macca: {player.gold}", "YELLOW")
    
    print(f" {hp_txt}  |  {mp_txt}  |  {gold_txt}")
    
    # XP Bar visualization (Optional but nice)
    if player.exp_next > 0:
        pct = int((player.exp / player.exp_next) * 100)
        print(f" EXP: {pct}%".rjust(60))
        
    print_separator()
    
    # 3. Demon Info (Target)
    if demon:
        r_lbl = _rarity_label(demon.rarity)
        print(f" VS  {_style(demon.name, 'RED')} ({r_lbl})".center(70))
        print_separator()

def print_rapport_bar(current: int, needed: int, length: int = 20):
    """
    Visual bar for negotiation progress.
    """
    if needed <= 0: needed = 1
    ratio = max(0.0, min(1.0, current / needed))
    filled = int(ratio * length)
    
    # Color logic based on success probability
    color = "RED"
    status = "NEUTRAL"
    
    if ratio < 0.3:
        status = "FRÍO"
        color = "BLUE"
    elif ratio > 0.4 and ratio < 0.8:
        status = "INTERESADO"
        color = "YELLOW"
    elif ratio >= 0.8:
        status = "CONFIANZA"
        color = "GREEN"
    
    bar_chars = "█" * filled + "░" * (length - filled)
    bar_colored = _style(bar_chars, color)
    
    print(f" AFINIDAD: [{bar_colored}] {current}/{needed} ({status})")
    print_separator()