from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .utils import (
    Clamp,
    DefendDamageTakenMultiplier,
    DefendRegenMultiplier,
    FullBarDrainSeconds,
    TurnRegenPercent,
)


@dataclass
class StatusEffect:
    Name: str
    RemainingTurns: int = 0  # for turn-based statuses (e.g. Defend)
    DurationSeconds: float = 0.0  # for timed buffs
    DurationMaxSeconds: float = 0.0
    Description: str = ""

    def IsTimed(self) -> bool:
        return self.DurationMaxSeconds > 0.0


@dataclass
class Ability:
    Name: str
    Kind: str  # "Attack" | "Defend" | "Heal" | "Buff" | "Passive"
    Targeting: str  # "Enemy Single" | "Ally Single" | "Self"
    BaseDelay: float
    Mult: float
    BaseMpCost: float
    Description: str = ""


@dataclass
class Item:
    Name: str
    Value: int
    Tier: int
    Description: str


@dataclass
class BattleEntity:
    Name: str
    Level: int
    Weights: Dict[str, float]
    AbilityNames: List[str]
    DropTable: List[Dict]
    Team: str  # "Player" | "Enemy"

    CurrentHp: float = 1.0
    CurrentMp: float = 1.0
    Atp: float = 0.0
    AtpRate: float = 0.0
    NextActionTime: float = 0.0
    Statuses: List[StatusEffect] = field(default_factory=list)

    # Animated bars (visual only)
    LagHp: float = 1.0
    LagMp: float = 1.0

    LagHpFrom: float = 1.0
    LagHpTo: float = 1.0
    LagHpTimer: float = 0.0
    LagHpDuration: float = 0.0

    LagMpFrom: float = 1.0
    LagMpTo: float = 1.0
    LagMpTimer: float = 0.0
    LagMpDuration: float = 0.0

    Alive: bool = True

    def Stat(self, stat_name: str) -> float:
        level = float(self.Level)
        weight = float(self.Weights.get(stat_name, 0.0))
        return (level * (1.0 + weight)) ** 2

    def MaxHp(self) -> float:
        return self.Stat("Vitality")

    def MaxMp(self) -> float:
        return self.Stat("Vitality")

    def HasStatus(self, status_name: str) -> bool:
        return any(
            s.Name == status_name and (s.RemainingTurns > 0 or s.DurationSeconds > 0)
            for s in self.Statuses
        )

    def GetDefendMultipliers(self) -> Tuple[float, float]:
        if self.HasStatus("Defend"):
            return (
                DefendDamageTakenMultiplier,
                DefendRegenMultiplier,
            )
        return (1.0, 1.0)

    def ApplyTurnRegen(self):
        if not self.Alive:
            return
        _, regen_mult = self.GetDefendMultipliers()
        hp_gain = self.MaxHp() * TurnRegenPercent * regen_mult
        mp_gain = self.MaxMp() * TurnRegenPercent * regen_mult
        self.HealHp(hp_gain)
        self.RestoreMp(mp_gain)

    def BeginLagHp(self, new_value: float):
        old = float(self.LagHp)
        delta = abs(new_value - old)
        den = max(1.0, self.MaxHp())
        percent = Clamp(delta / den, 0.0, 1.0)
        duration = max(0.05, percent * FullBarDrainSeconds)
        self.LagHpFrom = old
        self.LagHpTo = new_value
        self.LagHpTimer = 0.0
        self.LagHpDuration = duration

    def BeginLagMp(self, new_value: float):
        old = float(self.LagMp)
        delta = abs(new_value - old)
        den = max(1.0, self.MaxMp())
        percent = Clamp(delta / den, 0.0, 1.0)
        duration = max(0.05, percent * FullBarDrainSeconds)
        self.LagMpFrom = old
        self.LagMpTo = new_value
        self.LagMpTimer = 0.0
        self.LagMpDuration = duration

    def TakeDamage(self, amount: float):
        if not self.Alive:
            return
        damage_taken_mult, _ = self.GetDefendMultipliers()
        amount = max(0.0, amount) * damage_taken_mult
        self.CurrentHp = max(0.0, self.CurrentHp - amount)
        self.BeginLagHp(self.CurrentHp)
        if self.CurrentHp <= 0:
            self.Alive = False

    def HealHp(self, amount: float):
        if not self.Alive:
            return
        amount = max(0.0, amount)
        self.CurrentHp = min(self.MaxHp(), self.CurrentHp + amount)
        self.BeginLagHp(self.CurrentHp)

    def SpendMp(self, amount: float) -> bool:
        amount = max(0.0, amount)
        if self.CurrentMp < amount:
            return False
        self.CurrentMp -= amount
        self.BeginLagMp(self.CurrentMp)
        return True

    def RestoreMp(self, amount: float):
        if not self.Alive:
            return
        amount = max(0.0, amount)
        self.CurrentMp = min(self.MaxMp(), self.CurrentMp + amount)
        self.BeginLagMp(self.CurrentMp)

    def TickVisualBars(self, dt: float):
        if self.LagHpDuration > 0:
            self.LagHpTimer += dt
            t = Clamp(self.LagHpTimer / self.LagHpDuration, 0.0, 1.0)
            t = 1 - (1 - t) * (1 - t)
            self.LagHp = self.LagHpFrom + (self.LagHpTo - self.LagHpFrom) * t
            if self.LagHpTimer >= self.LagHpDuration:
                self.LagHp = self.LagHpTo
                self.LagHpDuration = 0.0
        else:
            self.LagHp = self.CurrentHp

        if self.LagMpDuration > 0:
            self.LagMpTimer += dt
            t = Clamp(self.LagMpTimer / self.LagMpDuration, 0.0, 1.0)
            t = 1 - (1 - t) * (1 - t)
            self.LagMp = self.LagMpFrom + (self.LagMpTo - self.LagMpFrom) * t
            if self.LagMpTimer >= self.LagMpDuration:
                self.LagMp = self.LagMpTo
                self.LagMpDuration = 0.0
        else:
            self.LagMp = self.CurrentMp


@dataclass
class FloatingNumber:
    X: float
    Y: float
    Text: str
    Color: Tuple[int, int, int]
    Size: int
    Life: float = 0.8
    Age: float = 0.0

    def Tick(self, dt: float):
        self.Age += dt
        self.Y -= 35 * dt

    def IsAlive(self) -> bool:
        return self.Age < self.Life
