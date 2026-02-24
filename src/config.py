from dataclasses import dataclass, field
from typing import List, Dict

# --- Constants ---
DEF_CONSTANT = 500  # Defense constant

# --- Data Models ---
@dataclass
class Skill:
    name: str
    damage: float
    cooldown: float
    mana_cost: float

@dataclass
class Character:
    level: int = 1
    stats: Dict[str, float] = field(default_factory=dict)
    skills: List[Skill] = field(default_factory=list)
    proficiency: str = "medium"  # "low", "medium", "high"
    inventory: Dict[str, int] = field(default_factory=dict)
    gold: int = 0

    def __post_init__(self):
        if not self.stats:
            self.stats = get_stat_by_level(self.level)

@dataclass
class Monster:
    name: str
    level: int
    stats: Dict[str, float] = field(default_factory=dict)
    skills: List[Skill] = field(default_factory=list)
    loot_table: Dict[str, float] = field(default_factory=dict)
    gold_drop: int = 0

    def __post_init__(self):
        if not self.stats:
            self.stats = get_stat_by_level(self.level)

@dataclass
class Item:
    name: str
    item_type: str  # "consumable", "equipment", "material"
    effect: Dict[str, float] = field(default_factory=dict)

@dataclass
class HuntingGround:
    name: str
    tier: int
    monster_types: List[Monster]
    roaming_time_range: tuple = (5, 15) # (min, max) seconds

# --- Game Data ---
# Pre-defined items
CONSUMABLES = {
    "Bread": Item(name="Bread", item_type="consumable", effect={"hp_restore": 200, "consume_time": 5})
}


# --- Game Logic Functions ---
def get_stat_by_level(level):
    """Calculates character/monster stats based on level using linear interpolation."""
    atk = 60 + (level - 1) * (948 - 60) / 59
    def_val = 120 + (level - 1) * (1696 - 120) / 59
    hp = 1500 + (level - 1) * (7400 - 1500) / 59
    mp = 200 + (level - 1) * (1000 - 200) / 59
    mp_regen = 5 + (level - 1) * (25 - 5) / 59
    aps = 1.0 + (level - 1) * (1.5 - 1.0) / 59 # Attacks per second
    exp = 20 + (level - 1) * (300 - 20) / 59  # EXP given by monster
    return {"atk": atk, "def": def_val, "hp": hp, "mp": mp, "mp_regen": mp_regen, "aps": aps, "exp": exp}

def get_exp_for_next_level(n):
    """Calculates the experience required to advance from level n to n+1."""
    if n >= 60:
        return float('inf')
    return int(1000 * (1.05) ** (n - 1))
