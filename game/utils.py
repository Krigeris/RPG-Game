import json
import math
import os
from typing import Any

# ============================================================
# Global Settings (Easy to change later)
# ============================================================

ScreenWidth = 1280
ScreenHeight = 720
FramesPerSecond = 60

DataFolder = "Data"
SavesFolder = "Saves"

FontName = None  # default pygame font

# Visual timing: Full-bar drain takes 1.5s (visual only)
FullBarDrainSeconds = 1.5

# Baseline delays
BaselineAbilityDelay = 2.5

# Regen per turn (turn begins): 1%
TurnRegenPercent = 0.01

# Defend buff
DefendDamageTakenMultiplier = 0.75
DefendRegenMultiplier = 2.0
DefendDefenseQteWindowMultiplier = 1.25

# QTE multipliers (tunable)
QteMultipliersAttack = {
    "Miss": 0.0,
    "Hit": 1.0,
    "Crit": 1.35,
    "Vital": 1.85,
}

# Enemy "virtual QTE" baseline distribution at precision ratio ~ 1.0
EnemyQteBaselineAttack = {"Miss": 0.10, "Hit": 0.75, "Crit": 0.12, "Vital": 0.03}

# Precision ratio influence strength (tunable)
EnemyQteShiftStrength = 0.22  # higher makes ratio matter more

# MP cost scaling: BaseMpCost * (CasterVitality/Scale)^Exponent
MpVitalityScale = 10000.0
MpVitalityExponent = 0.50

# Add MP cost to damage/heal (your rule)
AddMpCostToOutput = True

# ============================================================
# Helpers
# ============================================================

def EnsureFolder(path: str):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def LoadJson(path: str, default_value: Any):
    if not os.path.exists(path):
        return default_value
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def SaveJson(path: str, data: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def Clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


def FormatNumber(value: float) -> str:
    # Display numbers in K/M/B/T once >= 1000
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value < 1000:
        if float(value).is_integer():
            return f"{sign}{int(value)}"
        return f"{sign}{value:.1f}"
    units = [("T", 1_000_000_000_000), ("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)]
    for suffix, scale in units:
        if value >= scale:
            out = value / scale
            if out >= 100:
                return f"{sign}{out:.0f}{suffix}"
            if out >= 10:
                return f"{sign}{out:.1f}{suffix}"
            return f"{sign}{out:.2f}{suffix}"
    return f"{sign}{value}"


def PowRatio(attacker_stat: float, defender_stat: float) -> float:
    if defender_stat <= 0:
        return 1.0
    return (attacker_stat / defender_stat) ** 0.75


def RoundTenths(x: float) -> float:
    return round(x * 10.0) / 10.0
