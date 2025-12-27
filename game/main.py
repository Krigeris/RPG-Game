import json
import os
import random
from typing import Dict, List, Optional, Tuple

import pygame

from .data_loader import CreateDefaultData
from .entities import Ability, BattleEntity, FloatingNumber, Item, StatusEffect
from .ui import Button, Tooltip
from .utils import *


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("QTE ATB Battle v2")
        self.Screen = pygame.display.set_mode((ScreenWidth, ScreenHeight))
        self.Clock = pygame.time.Clock()

        self.FontSmall = pygame.font.Font(FontName, 16)
        self.Font = pygame.font.Font(FontName, 20)
        self.FontBig = pygame.font.Font(FontName, 28)
        self.FontHuge = pygame.font.Font(FontName, 40)

        CreateDefaultData()

        self.QteSpeed = 420.0  # needed before LoadDatabase
        self.LoadDatabase()

        self.Tooltip = Tooltip()

        self.Mode = "Title"  # "Title" | "Battle" | "Dev"
        self.SubMode = ""

        self.ActiveSave: Optional[Dict] = None

        self.TitleButtons = [
            Button(pygame.Rect(520, 250, 240, 48), "Load Slot 1"),
            Button(pygame.Rect(520, 310, 240, 48), "New Slot 1"),
            Button(pygame.Rect(520, 370, 240, 48), "Start Battle"),
        ]

        self.DevButton = Button(pygame.Rect(ScreenWidth-110, 10, 100, 36), "DEV")

        # Battle runtime
        self.BattleTime = 0.0
        self.BattleFrozen = False
        self.PlayerParty: List[BattleEntity] = []
        self.EnemyParty: List[BattleEntity] = []
        self.FloatingNumbers: List[FloatingNumber] = []
        self.BattleRewards: Dict = {}

        # Selection/inspect
        self.InspectSelection: Optional[Tuple[str, int]] = None  # (Team, Index)
        self.HoveredStatusTooltip: bool = False

        # Turn
        self.ActiveTeam: str = "Player"
        self.ActiveEntityIndex: int = 0

        # Action state
        self.SelectedAbility: Optional[Ability] = None
        self.TargetTeam: str = "Enemy"
        self.SelectedTargetIndex: int = 0

        # QTE runtime
        self.QteMode: Optional[str] = None
        self.QteResult: Optional[str] = None
        self.QtePressed = False
        self.QteRadius = 0.0
        self.QteRadii = {}

        # Inventory scrolling
        self.InventoryScroll = 0

        # Dev Menu
        self.DevTab = "Entities"
        self.DevSelectedName = ""
        self.DevScroll = 0

    # ---------------- Database ----------------

    def LoadDatabase(self):
        self.EntitiesDb = LoadJson(os.path.join(DataFolder, "Entities.json"), [])
        self.AbilitiesDb = LoadJson(os.path.join(DataFolder, "Abilities.json"), [])
        self.ItemsDb = LoadJson(os.path.join(DataFolder, "Items.json"), [])
        self.AreasDb = LoadJson(os.path.join(DataFolder, "Areas.json"), [])
        self.EncountersDb = LoadJson(os.path.join(DataFolder, "Encounters.json"), [])
        self.BalanceDb = LoadJson(os.path.join(DataFolder, "Balance.json"), {})

        self.EntitiesByName = {E["Name"]: E for E in self.EntitiesDb}
        self.AbilitiesByName = {A["Name"]: A for A in self.AbilitiesDb}
        self.ItemsByName = {I["Name"]: I for I in self.ItemsDb}
        self.EncountersByName = {C["Name"]: C for C in self.EncountersDb}
        self.AreasByName = {A["Name"]: A for A in self.AreasDb}

        self.QteSpeed = float(self.BalanceDb.get("QTE Ring Speed", self.QteSpeed))

    def SaveDatabase(self):
        SaveJson(os.path.join(DataFolder, "Entities.json"), self.EntitiesDb)
        SaveJson(os.path.join(DataFolder, "Abilities.json"), self.AbilitiesDb)
        SaveJson(os.path.join(DataFolder, "Items.json"), self.ItemsDb)
        SaveJson(os.path.join(DataFolder, "Areas.json"), self.AreasDb)
        SaveJson(os.path.join(DataFolder, "Encounters.json"), self.EncountersDb)
        SaveJson(os.path.join(DataFolder, "Balance.json"), self.BalanceDb)
        self.LoadDatabase()

    # ---------------- Saves ----------------

    def SavePath(self, SlotName: str) -> str:
        return os.path.join(SavesFolder, SlotName, "Save.json")

    def LoadSave(self, SlotName: str) -> Optional[Dict]:
        Path = self.SavePath(SlotName)
        if not os.path.exists(Path):
            return None
        return LoadJson(Path, None)

    def CreateNewSave(self, SlotName: str):
        EnsureFolder(os.path.join(SavesFolder, SlotName))
        Save = {
            "Slot": SlotName,
            "Gold": 0,
            "Party": [
                {"Name": "Hero", "Level": 6, "Xp": 0},
                {"Name": "Rogue", "Level": 6, "Xp": 0},
            ],
            "Inventory": [
                {"Name": "Potion", "Amount": 2},
                {"Name": "Ether", "Amount": 1},
            ],
            "Area": "Starter Field",
            "Options": {"Difficulty": "Normal"}
        }
        SaveJson(self.SavePath(SlotName), Save)
        self.ActiveSave = Save

    def PersistSave(self):
        if not self.ActiveSave:
            return
        EnsureFolder(os.path.join(SavesFolder, self.ActiveSave["Slot"]))
        SaveJson(self.SavePath(self.ActiveSave["Slot"]), self.ActiveSave)

    # ============================================================
    # Battle Setup
    # ============================================================

    def MakeBattleEntity(self, EntityName: str, Team: str, OverrideLevel: Optional[int]=None) -> BattleEntity:
        T = self.EntitiesByName[EntityName]
        Level = int(OverrideLevel if OverrideLevel is not None else T.get("Level", 1))
        Weights = dict(T.get("Weights", {}))
        AbilityNames = list(T.get("Abilities", []))
        DropTable = list(T.get("Drop Table", []))
        E = BattleEntity(
            Name=T["Name"],
            Level=Level,
            Weights=Weights,
            AbilityNames=AbilityNames,
            DropTable=DropTable,
            Team=Team,
        )
        E.CurrentHp = E.MaxHp()
        E.CurrentMp = E.MaxMp()
        E.LagHp = E.CurrentHp
        E.LagMp = E.CurrentMp
        return E

    def StartBattleFromArea(self):
        if not self.ActiveSave:
            S = self.LoadSave("Slot 1")
            if not S:
                self.CreateNewSave("Slot 1")
            else:
                self.ActiveSave = S

        AreaName = self.ActiveSave.get("Area", "Starter Field")
        Area = self.AreasByName.get(AreaName, None)
        EncounterNames = Area.get("Encounters", []) if Area else []
        if not EncounterNames:
            EncounterNames = ["Field Encounter 1"]
        EncounterName = random.choice(EncounterNames)
        Encounter = self.EncountersByName.get(EncounterName)

        self.PlayerParty = []
        for P in self.ActiveSave["Party"]:
            Name = P["Name"]
            Level = int(P.get("Level", self.EntitiesByName[Name].get("Level", 1)))
            self.PlayerParty.append(self.MakeBattleEntity(Name, "Player", OverrideLevel=Level))

        self.EnemyParty = []
        for EnemyName in Encounter["Enemy Party"]:
            self.EnemyParty.append(self.MakeBattleEntity(EnemyName, "Enemy"))

        self.BattleTime = 0.0
        self.BattleFrozen = False
        self.FloatingNumbers = []
        self.BattleRewards = {}
        self.InventoryScroll = 0

        # Default inspect selection
        self.InspectSelection = ("Player", 0)

        # Initialize starting next-action times using dex bias
        All = self.PlayerParty + self.EnemyParty
        AvgDex = sum(e.Stat("Dexterity") for e in All) / max(1, len(All))
        for E in All:
            DexRatio = PowRatio(E.Stat("Dexterity"), AvgDex)
            StartDelay = RoundTenths(max(0.5, 5.0 / max(0.15, DexRatio)))
            E.NextActionTime = StartDelay

        self.Mode = "Battle"
        self.SubMode = "Free"
        self.SelectedAbility = None
        self.SelectedTargetIndex = 0
        self.TargetTeam = "Enemy"

    # ============================================================
    # Abilities / Costs / Effects
    # ============================================================

    def GetAbility(self, AbilityName: str) -> Ability:
        A = self.AbilitiesByName[AbilityName]
        return Ability(
            Name=A["Name"],
            Kind=A["Kind"],
            Targeting=A["Targeting"],
            BaseDelay=float(A["Base Delay"]),
            Mult=float(A["Mult"]),
            BaseMpCost=float(A["Base MP Cost"]),
            Description=A.get("Description", "")
        )

    def ComputeMpCost(self, Caster: BattleEntity, AbilityObj: Ability) -> int:
        Base = float(AbilityObj.BaseMpCost)
        if Base <= 0:
            return 0
        Vit = max(1.0, Caster.Stat("Vitality"))
        Scaled = Base * ((Vit / MpVitalityScale) ** MpVitalityExponent)
        return int(round(max(1.0, Scaled)))

    def AddOrExtendStatusTurns(self, EntityObj: BattleEntity, StatusName: str, Turns: int, Description: str=""):
        for S in EntityObj.Statuses:
            if S.Name == StatusName and S.DurationMaxSeconds <= 0:
                S.RemainingTurns += Turns
                return
        EntityObj.Statuses.append(StatusEffect(Name=StatusName, RemainingTurns=Turns, Description=Description))

    def AddTimedBuff(self, EntityObj: BattleEntity, BuffName: str, DurationSeconds: float, Description: str=""):
        # stack duration of same exact kind
        for S in EntityObj.Statuses:
            if S.Name == BuffName and S.DurationMaxSeconds > 0:
                # extend both remaining and max so % stays consistent for display simplicity
                S.DurationSeconds += DurationSeconds
                S.DurationMaxSeconds += DurationSeconds
                return
        EntityObj.Statuses.append(StatusEffect(Name=BuffName,
                                              RemainingTurns=0,
                                              DurationSeconds=DurationSeconds,
                                              DurationMaxSeconds=DurationSeconds,
                                              Description=Description))

    def TickTimedBuffs(self, Dt: float):
        for E in self.PlayerParty + self.EnemyParty:
            NewStatuses = []
            for S in E.Statuses:
                if S.DurationMaxSeconds > 0:
                    S.DurationSeconds = max(0.0, S.DurationSeconds - Dt)
                    if S.DurationSeconds <= 0.0:
                        continue
                NewStatuses.append(S)
            E.Statuses = NewStatuses

    def EffectiveStat(self, E: BattleEntity, StatName: str) -> float:
        Base = E.Stat(StatName)
        for S in E.Statuses:
            if S.Name == "Rally (Power +20%)" and StatName == "Power":
                Base *= 1.20
            if S.Name == "Focus (Precision +25%)" and StatName == "Precision":
                Base *= 1.25
        return Base

    def SpawnFloatOnEntity(self, EntityObj: BattleEntity, Text: str, Color: Tuple[int,int,int], Size: int):
        TeamList = self.PlayerParty if EntityObj.Team == "Player" else self.EnemyParty
        Index = TeamList.index(EntityObj)
        R = self.EntityRect(EntityObj.Team, Index)
        self.FloatingNumbers.append(FloatingNumber(
            X=R.centerx, Y=R.y - 10, Text=Text, Color=Color, Size=Size
        ))

    def ApplyAbility(self, Caster: BattleEntity, Target: BattleEntity, AbilityObj: Ability, QteOutcome: str):
        if AbilityObj.Kind == "Passive":
            return

        MpCost = self.ComputeMpCost(Caster, AbilityObj)
        if MpCost > 0 and not Caster.SpendMp(MpCost):
            self.FloatingNumbers.append(FloatingNumber(
                X=640, Y=60, Text="Not enough MP!", Color=(255,120,120), Size=22, Life=0.9
            ))
            return

        QteMult = QteMultipliersAttack.get(QteOutcome, 1.0)

        if AbilityObj.Kind == "Attack":
            Base = self.EffectiveStat(Caster, "Power") / 5.0
            Ratio = PowRatio(self.EffectiveStat(Caster, "Power"), self.EffectiveStat(Target, "Power"))
            Damage = Base * Ratio * QteMult * AbilityObj.Mult
            if AddMpCostToOutput:
                Damage += MpCost
            Damage = max(0.0, round(Damage))
            Target.TakeDamage(Damage)

            Color = (240,240,240)
            Size = 22
            if QteOutcome == "Crit":
                Color = (255, 235, 80)
                Size = 28
            elif QteOutcome == "Vital":
                Color = (255, 80, 80)
                Size = 36
            elif QteOutcome == "Miss":
                Color = (200,200,200)
                Size = 20
            self.SpawnFloatOnEntity(Target, f"{FormatNumber(Damage)}", Color, Size)

        elif AbilityObj.Kind == "Heal":
            Base = self.EffectiveStat(Caster, "Power") / 5.0
            Ratio = PowRatio(self.EffectiveStat(Caster, "Vitality"), self.EffectiveStat(Target, "Vitality"))
            Heal = Base * Ratio * QteMult * AbilityObj.Mult
            if AddMpCostToOutput:
                Heal += MpCost
            Heal = max(0.0, round(Heal))
            Target.HealHp(Heal)
            self.SpawnFloatOnEntity(Target, f"+{FormatNumber(Heal)}", (70,255,110), 28 if QteOutcome != "Miss" else 20)

        elif AbilityObj.Kind == "Defend":
            self.AddOrExtendStatusTurns(
                Caster,
                "Defend",
                1,
                Description="1 turn: -25% damage taken, x2 regen, +25% defense QTE window."
            )

        elif AbilityObj.Kind == "Buff":
            BaseDuration = 6.0
            DurRatio = PowRatio(self.EffectiveStat(Caster, "Vitality"), self.EffectiveStat(Target, "Vitality"))
            Duration = RoundTenths(BaseDuration * DurRatio * QteMult)

            if AbilityObj.Name == "Rally":
                self.AddTimedBuff(Target, "Rally (Power +20%)", Duration, Description="Power +20%.")
            elif AbilityObj.Name == "Focus":
                self.AddTimedBuff(Target, "Focus (Precision +25%)", Duration, Description="Precision +25%.")
            else:
                self.AddTimedBuff(Target, f"{AbilityObj.Name} (Buff)", Duration, Description=AbilityObj.Description)

    # ============================================================
    # QTE (Ring)
    # ============================================================

    def BeginQte(self, Attacker: BattleEntity, Defender: BattleEntity):
        self.QteMode = "Attack"
        self.QteResult = None
        self.QtePressed = False

        CenterRadius = 18.0
        OuterRadius = 120.0

        PrecRatioRaw = PowRatio(self.EffectiveStat(Attacker, "Precision"), self.EffectiveStat(Defender, "Precision"))
        PrecMin = float(self.BalanceDb.get("Precision Ratio Clamp Min", 0.60))
        PrecMax = float(self.BalanceDb.get("Precision Ratio Clamp Max", 1.60))
        PrecRatio = Clamp(PrecRatioRaw, PrecMin, PrecMax)

        WindowMult = PrecRatio

        VitalMin = float(self.BalanceDb.get("QTE Vital Zone Min Width", 10.0))
        CritMin = float(self.BalanceDb.get("QTE Crit Zone Min Width", 18.0))

        VitalWidth = max(VitalMin, 14.0 * WindowMult)
        CritWidth = max(CritMin, 24.0 * WindowMult)

        VitalOuter = CenterRadius + VitalWidth
        CritOuter = VitalOuter + CritWidth
        HitOuter = OuterRadius

        self.QteRadii = {
            "Center": CenterRadius,
            "VitalOuter": VitalOuter,
            "CritOuter": CritOuter,
            "HitOuter": HitOuter
        }
        self.QteRadius = HitOuter + 30.0  # start outside hit ring

    def ResolveQtePress(self) -> str:
        R = self.QteRadius
        HitOuter = self.QteRadii["HitOuter"]
        CritOuter = self.QteRadii["CritOuter"]
        VitalOuter = self.QteRadii["VitalOuter"]
        Center = self.QteRadii["Center"]

        # Your rule:
        # - undershoot (before entering hit): Miss
        # - overshoot (after vital): regular Hit
        if R > HitOuter:
            return "Miss"
        if R <= Center:
            return "Hit"
        if R <= VitalOuter:
            return "Vital"
        if R <= CritOuter:
            return "Crit"
        return "Hit"

    def TickQte(self, Dt: float):
        if not self.QteMode:
            return
        self.QteRadius -= self.QteSpeed * Dt
        if self.QteRadius <= 0 and not self.QtePressed:
            self.QteResult = "Hit"
            self.QtePressed = True

    # ============================================================
    # Enemy Virtual QTE
    # ============================================================

    def ChooseFromProbabilities(self, ProbDict: Dict[str, float]) -> str:
        Roll = random.random()
        Acc = 0.0
        for K, V in ProbDict.items():
            Acc += V
            if Roll <= Acc:
                return K
        return list(ProbDict.keys())[-1]

    def EnemyVirtualQteAttack(self, Attacker: BattleEntity, Defender: BattleEntity) -> str:
        Strength = float(self.BalanceDb.get("Enemy QTE Shift Strength", EnemyQteShiftStrength))
        Base = dict(self.BalanceDb.get("Enemy QTE Baseline Attack", EnemyQteBaselineAttack))
        PrecRatio = PowRatio(self.EffectiveStat(Attacker, "Precision"), self.EffectiveStat(Defender, "Precision"))
        Shift = Clamp((PrecRatio - 1.0) * Strength, -0.45, 0.45)

        HitTake = min(Base["Hit"], abs(Shift))
        if Shift > 0:
            Base["Hit"] -= HitTake
            Base["Crit"] += HitTake * 0.70
            Base["Vital"] += HitTake * 0.30
        else:
            Base["Hit"] -= HitTake
            Base["Miss"] += HitTake

        Total = sum(max(0.0, v) for v in Base.values())
        if Total <= 0:
            return "Hit"
        Norm = {k: max(0.0, v) / Total for k, v in Base.items()}
        return self.ChooseFromProbabilities(Norm)

    # ============================================================
    # Turn Flow
    # ============================================================

    def GetEntityByTeamIndex(self, Team: str, Index: int) -> Optional[BattleEntity]:
        if Team == "Player":
            if 0 <= Index < len(self.PlayerParty):
                return self.PlayerParty[Index]
        if Team == "Enemy":
            if 0 <= Index < len(self.EnemyParty):
                return self.EnemyParty[Index]
        return None

    def GetNextActor(self) -> Optional[Tuple[str, int, BattleEntity]]:
        Candidates = []
        for i, e in enumerate(self.PlayerParty):
            if e.Alive:
                Candidates.append(("Player", i, e))
        for i, e in enumerate(self.EnemyParty):
            if e.Alive:
                Candidates.append(("Enemy", i, e))
        if not Candidates:
            return None
        Candidates.sort(key=lambda t: t[2].NextActionTime)
        Team, Index, E = Candidates[0]
        if E.NextActionTime <= self.BattleTime + 1e-6:
            return (Team, Index, E)
        return None

    def FreezeForTurn(self, Team: str, Index: int):
        self.BattleFrozen = True
        self.ActiveTeam = Team
        self.ActiveEntityIndex = Index

        Actor = self.GetEntityByTeamIndex(Team, Index)
        if Actor and Actor.Alive:
            Actor.ApplyTurnRegen()

        # default inspect follows active
        self.InspectSelection = (Team, Index)

        if Team == "Player":
            self.SubMode = "Choose Action"
            self.SelectedAbility = None
            self.SelectedTargetIndex = 0
            self.TargetTeam = "Enemy"
        else:
            self.SubMode = "Enemy Act"

    def DetermineTargetTeam(self, AbilityObj: Ability) -> str:
        if AbilityObj.Targeting == "Enemy Single":
            return "Enemy"
        if AbilityObj.Targeting == "Ally Single":
            return "Player"
        if AbilityObj.Targeting == "Self":
            return "Player"
        return "Enemy"

    def GetTargetList(self) -> List[Tuple[BattleEntity, pygame.Rect]]:
        Targets = []
        if self.TargetTeam == "Enemy":
            for i, E in enumerate(self.EnemyParty):
                if E.Alive:
                    Targets.append((E, self.EntityRect("Enemy", i)))
        else:
            for i, E in enumerate(self.PlayerParty):
                if E.Alive:
                    Targets.append((E, self.EntityRect("Player", i)))
        return Targets

    def GetSelectedTarget(self) -> Optional[BattleEntity]:
        Targets = self.GetTargetList()
        if not Targets:
            return None
        self.SelectedTargetIndex = int(Clamp(self.SelectedTargetIndex, 0, len(Targets)-1))
        return Targets[self.SelectedTargetIndex][0]

    def CompleteActionAndScheduleNext(self, Actor: BattleEntity, Target: BattleEntity, AbilityObj: Ability):
        DexRatio = PowRatio(self.EffectiveStat(Actor, "Dexterity"), self.EffectiveStat(Target, "Dexterity"))
        Delay = RoundTenths(AbilityObj.BaseDelay / max(0.15, DexRatio))
        Actor.NextActionTime = RoundTenths(self.BattleTime + Delay)

        # Decrement 1-turn statuses like Defend at end of actor's turn
        NewStatuses = []
        for S in Actor.Statuses:
            if S.DurationMaxSeconds <= 0 and S.RemainingTurns > 0:
                if S.Name == "Defend":
                    S.RemainingTurns -= 1
                if S.RemainingTurns > 0:
                    NewStatuses.append(S)
            else:
                NewStatuses.append(S)
        Actor.Statuses = NewStatuses

    # ============================================================
    # Rewards / Drops / XP
    # ============================================================

    def XpForEnemy(self, EnemyLevel: int) -> int:
        return int(round((5 + EnemyLevel) ** 1.5))

    def GoldForEnemy(self, EnemyLevel: int) -> int:
        return self.XpForEnemy(EnemyLevel)

    def RollDropTable(self, Enemy: BattleEntity) -> List[Tuple[str, int]]:
        Drops = []
        for Entry in Enemy.DropTable:
            Qty = int(Entry["Quantity"])
            ItemName = Entry["Item"]
            Num = int(Entry["Chance Numerator"])
            Den = int(Entry["Chance Denominator"])
            if Den <= 0:
                continue
            if random.random() <= (Num / Den):
                Drops.append((ItemName, Qty))
        return Drops

    def GiveItemToInventory(self, ItemName: str, Amount: int):
        Inv = self.ActiveSave["Inventory"]
        for It in Inv:
            if It["Name"] == ItemName:
                It["Amount"] += Amount
                return
        Inv.append({"Name": ItemName, "Amount": Amount})

    def EndBattle(self, PlayerWon: bool):
        self.SubMode = "Battle End"
        self.BattleFrozen = True

        TotalXp = 0
        TotalGold = 0
        LootDrops: List[Tuple[str,int]] = []

        if PlayerWon and self.ActiveSave:
            for E in self.EnemyParty:
                TotalXp += self.XpForEnemy(E.Level)
                TotalGold += self.GoldForEnemy(E.Level)
                LootDrops.extend(self.RollDropTable(E))

            self.ActiveSave["Gold"] += TotalGold
            for P in self.ActiveSave["Party"]:
                P["Xp"] = int(P.get("Xp", 0) + TotalXp)

            for Name, Qty in LootDrops:
                self.GiveItemToInventory(Name, Qty)

            self.PersistSave()

        self.BattleRewards = {
            "PlayerWon": PlayerWon,
            "TotalXp": TotalXp,
            "TotalGold": TotalGold,
            "Loot": LootDrops
        }

    # ============================================================
    # Layout / Rects
    # ============================================================

    def EntityRect(self, Team: str, Index: int) -> pygame.Rect:
        # shifted left; no player/enemy labels
        Size = 96
        Gap = 18
        X0 = 20
        if Team == "Enemy":
            Y0 = 105
            return pygame.Rect(X0 + Index*(Size+Gap), Y0, Size, Size)
        return pygame.Rect(X0 + Index*(Size+Gap), 445, Size, Size)

    def InspectPanelRect(self) -> pygame.Rect:
        # below inventory panel
        return pygame.Rect(850, 430, 380, 270)

    # ============================================================
    # Inventory UI
    # ============================================================

    def GetInventorySorted(self) -> List[Dict]:
        if not self.ActiveSave:
            return []
        Inv = list(self.ActiveSave.get("Inventory", []))
        Inv.sort(key=lambda it: int(self.ItemsByName.get(it["Name"], {"Value": 0})["Value"]) * it["Amount"], reverse=True)
        return Inv

    # ============================================================
    # Tooltips
    # ============================================================

    def EntityTooltipLines(self, E: BattleEntity) -> List[str]:
        Lines = [
            f"{E.Name} (Level {E.Level})",
            f"HP: {FormatNumber(int(E.CurrentHp))}/{FormatNumber(int(E.MaxHp()))}",
            f"MP: {FormatNumber(int(E.CurrentMp))}/{FormatNumber(int(E.MaxMp()))}",
            f"Vitality: {FormatNumber(int(self.EffectiveStat(E,'Vitality')))}",
            f"Power: {FormatNumber(int(self.EffectiveStat(E,'Power')))}",
            f"Dexterity: {FormatNumber(int(self.EffectiveStat(E,'Dexterity')))}",
            f"Precision: {FormatNumber(int(self.EffectiveStat(E,'Precision')))}",
        ]
        if E.Statuses:
            Lines.append("Statuses:")
            for S in E.Statuses:
                if S.DurationMaxSeconds > 0:
                    Lines.append(f" • {S.Name} ({S.DurationSeconds:.1f}s)")
                else:
                    Lines.append(f" • {S.Name} (Turns: {S.RemainingTurns})")
        return Lines

    def ItemTooltipLines(self, Name: str, Amount: int) -> List[str]:
        ItemObj = self.ItemsByName.get(Name, None)
        Value = int(ItemObj["Value"]) if ItemObj else 0
        Tier = int(ItemObj["Tier"]) if ItemObj else 0
        Desc = ItemObj["Description"] if ItemObj else ""
        StackValue = Amount * Value
        return [
            f"{Name}",
            f"Amount: {FormatNumber(Amount)}",
            f"Value: {FormatNumber(Value)}",
            f"Stack Value: {FormatNumber(StackValue)}",
            f"Tier: {Tier}",
            f"{Desc}",
        ]

    def AbilityTooltipLines(self, Actor: BattleEntity, AbilityObj: Ability, DisabledReason: str="") -> List[str]:
        Lines = [
            f"{AbilityObj.Name}",
            f"{AbilityObj.Kind} • {AbilityObj.Targeting}",
            f"Delay: {AbilityObj.BaseDelay:.1f}s",
        ]
        Cost = self.ComputeMpCost(Actor, AbilityObj)
        Lines.append(f"MP Cost: {FormatNumber(Cost)}")
        if AbilityObj.Description:
            Lines.append("")
            Lines.append(AbilityObj.Description)
        if AbilityObj.Kind == "Passive":
            Lines.append("")
            Lines.append("(Passive)")
        if DisabledReason:
            Lines.append("")
            Lines.append(DisabledReason)
        return Lines

    # ============================================================
    # Dev Menu helpers
    # ============================================================

    def DevTabs(self) -> List[str]:
        return ["Entities", "Abilities", "Items", "Areas", "Balance"]

    def DevTabRect(self, TabName: str, Index: int) -> pygame.Rect:
        X0 = 20
        Y0 = 62
        W = 120
        H = 36
        Gap = 10
        return pygame.Rect(X0 + Index*(W+Gap), Y0, W, H)

    def DevSaveRect(self) -> pygame.Rect:
        return pygame.Rect(ScreenWidth-150, 62, 130, 36)

    # ============================================================
    # Main Loop
    # ============================================================

    def Run(self):
        Running = True
        while Running:
            Dt = self.Clock.tick(FramesPerSecond) / 1000.0
            for Event in pygame.event.get():
                if Event.type == pygame.QUIT:
                    Running = False
                self.HandleEvent(Event)

            self.Tick(Dt)
            self.Draw()

        pygame.quit()

    # ============================================================
    # Events
    # ============================================================

    def HandleEvent(self, Event):
        MousePos = pygame.mouse.get_pos()

        if self.Mode == "Title":
            if Event.type == pygame.MOUSEMOTION:
                for B in self.TitleButtons:
                    B.HandleMotion(MousePos)
            if Event.type == pygame.MOUSEBUTTONDOWN and Event.button == 1:
                for B in self.TitleButtons:
                    if B.HandleClick(MousePos):
                        if B.Text == "Load Slot 1":
                            S = self.LoadSave("Slot 1")
                            if S:
                                self.ActiveSave = S
                        elif B.Text == "New Slot 1":
                            self.CreateNewSave("Slot 1")
                            self.PersistSave()
                        elif B.Text == "Start Battle":
                            self.StartBattleFromArea()

        elif self.Mode == "Battle":
            if Event.type == pygame.MOUSEMOTION:
                self.DevButton.HandleMotion(MousePos)

            if Event.type == pygame.MOUSEBUTTONDOWN and Event.button == 1:
                # DEV
                if self.DevButton.HandleClick(MousePos):
                    self.Mode = "Dev"
                    self.DevTab = "Entities"
                    self.DevSelectedName = ""
                    self.DevScroll = 0
                    return

                # Target selection click
                if self.SubMode == "Choose Target":
                    if self.ClickTargetAt(MousePos):
                        self.BeginPlayerQte()
                        return

                # Select inspect entity by clicking boxes (after target selection attempts)
                Clicked = self.ClickEntitySelect(MousePos)
                if Clicked:
                    return

                # Ability click in inspect panel if player turn
                if self.SubMode == "Choose Action":
                    if self.ClickInspectAbility(MousePos):
                        return

            if Event.type == pygame.MOUSEWHEEL:
                # inventory scroll when hovering inventory
                inv_panel = pygame.Rect(850, 60, 380, 360)
                if inv_panel.collidepoint(MousePos):
                    self.InventoryScroll = max(0, self.InventoryScroll - int(Event.y * 30))

                # dev scroll handled in dev mode

            if Event.type == pygame.KEYDOWN:
                if self.SubMode == "Choose Target":
                    if Event.key == pygame.K_LEFT:
                        self.SelectedTargetIndex = max(0, self.SelectedTargetIndex - 1)
                    if Event.key == pygame.K_RIGHT:
                        self.SelectedTargetIndex += 1
                    if Event.key == pygame.K_RETURN:
                        self.BeginPlayerQte()
                    if Event.key == pygame.K_ESCAPE:
                        self.SubMode = "Choose Action"
                        self.SelectedAbility = None

                elif self.SubMode == "QTE":
                    if Event.key == pygame.K_SPACE and not self.QtePressed:
                        self.QtePressed = True
                        self.QteResult = self.ResolveQtePress()

                elif self.SubMode == "Battle End":
                    if Event.key in (pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_SPACE):
                        self.Mode = "Title"

        elif self.Mode == "Dev":
            if Event.type == pygame.KEYDOWN and Event.key == pygame.K_ESCAPE:
                self.Mode = "Battle"
                return

            if Event.type == pygame.MOUSEBUTTONDOWN and Event.button == 1:
                self.DevHandleClick(MousePos)

            if Event.type == pygame.MOUSEWHEEL:
                self.DevScroll = int(self.DevScroll - Event.y * 30)

    # ---------------- battle click helpers ----------------

    def ClickEntitySelect(self, MousePos) -> bool:
        # Click entities
        for i, E in enumerate(self.EnemyParty):
            if self.EntityRect("Enemy", i).collidepoint(MousePos):
                self.InspectSelection = ("Enemy", i)
                return True
        for i, E in enumerate(self.PlayerParty):
            if self.EntityRect("Player", i).collidepoint(MousePos):
                self.InspectSelection = ("Player", i)
                return True
        return False

    def ClickTargetAt(self, MousePos) -> bool:
        Targets = self.GetTargetList()
        if not Targets:
            return False
        for i, (_, Rect) in enumerate(Targets):
            if Rect.collidepoint(MousePos):
                self.SelectedTargetIndex = i
                return True
        return False

    # Inspect panel ability clicking
    def ClickInspectAbility(self, MousePos) -> bool:
        sel = self.InspectSelection
        if not sel:
            return False
        Team, Index = sel
        if Team != "Player":
            return False
        if self.ActiveTeam != "Player" or self.ActiveEntityIndex != Index:
            return False

        Actor = self.PlayerParty[Index]
        Panel = self.InspectPanelRect()
        if not Panel.collidepoint(MousePos):
            return False

        # abilities list rects
        rects = self.GetInspectAbilityRects(Actor, Panel)
        for (AbilityName, Rect) in rects:
            if Rect.collidepoint(MousePos):
                AObj = self.GetAbility(AbilityName)
                # passive abilities are non-clickable
                if AObj.Kind == "Passive":
                    return True
                # mp requirement
                cost = self.ComputeMpCost(Actor, AObj)
                if cost > 0 and Actor.CurrentMp < cost:
                    return True
                self.SelectedAbility = AObj
                self.TargetTeam = self.DetermineTargetTeam(AObj)
                self.SelectedTargetIndex = 0
                self.SubMode = "Choose Target" if AObj.Targeting != "Self" else "QTE"
                if self.SubMode == "QTE":
                    self.BeginPlayerQte()
                return True
        return False

    # ============================================================
    # Tick
    # ============================================================

    def Tick(self, Dt: float):
        if self.Mode != "Battle":
            return

        self.Tooltip.Hide()

        # Update bars and floats always
        for E in self.PlayerParty + self.EnemyParty:
            E.TickVisualBars(Dt)

        new_f = []
        for F in self.FloatingNumbers:
            F.Tick(Dt)
            if F.IsAlive():
                new_f.append(F)
        self.FloatingNumbers = new_f

        # Hover tooltips
        self.BattleHoverTooltips()

        if self.SubMode == "Free":
            # FIX: DO NOT round here. Rounding here stalls time at 0.0.
            self.BattleTime += Dt
            self.BattleTime = max(0.0, self.BattleTime)

            # timed buffs tick only while free
            self.TickTimedBuffs(Dt)

            nxt = self.GetNextActor()
            if nxt:
                Team, Index, _ = nxt
                self.FreezeForTurn(Team, Index)

            # end checks
            if all(not e.Alive for e in self.EnemyParty):
                self.EndBattle(PlayerWon=True)
            if all(not e.Alive for e in self.PlayerParty):
                self.EndBattle(PlayerWon=False)

        elif self.SubMode == "Enemy Act":
            Enemy = self.EnemyParty[self.ActiveEntityIndex]
            if not Enemy.Alive:
                self.SubMode = "Free"
                self.BattleFrozen = False
                return

            targets = [p for p in self.PlayerParty if p.Alive]
            if not targets:
                self.EndBattle(PlayerWon=False)
                return
            target = random.choice(targets)

            ability_name = random.choice(Enemy.AbilityNames)
            AObj = self.GetAbility(ability_name)

            cost = self.ComputeMpCost(Enemy, AObj)
            if cost > 0 and Enemy.CurrentMp < cost:
                AObj = self.GetAbility("Attack")

            if AObj.Targeting == "Self":
                target = Enemy
            elif AObj.Targeting == "Ally Single":
                allies = [e for e in self.EnemyParty if e.Alive]
                target = random.choice(allies)
            else:
                target = random.choice([p for p in self.PlayerParty if p.Alive])

            outcome = self.EnemyVirtualQteAttack(Enemy, target)
            self.ApplyAbility(Enemy, target, AObj, outcome)
            self.CompleteActionAndScheduleNext(Enemy, target, AObj)

            self.SubMode = "Free"
            self.BattleFrozen = False

        elif self.SubMode == "QTE":
            self.TickQte(Dt)
            if self.QtePressed and self.QteResult:
                actor = self.PlayerParty[self.ActiveEntityIndex]
                ability = self.SelectedAbility
                target = self.GetSelectedTarget() if ability and ability.Targeting != "Self" else actor
                if actor and ability and target:
                    self.ApplyAbility(actor, target, ability, self.QteResult)
                    self.CompleteActionAndScheduleNext(actor, target, ability)

                self.SelectedAbility = None
                self.SubMode = "Free"
                self.BattleFrozen = False

                if all(not e.Alive for e in self.EnemyParty):
                    self.EndBattle(PlayerWon=True)
                if all(not e.Alive for e in self.PlayerParty):
                    self.EndBattle(PlayerWon=False)

    # ============================================================
    # Player QTE start
    # ============================================================

    def BeginPlayerQte(self):
        actor = self.PlayerParty[self.ActiveEntityIndex]
        if not self.SelectedAbility:
            return
        if self.SelectedAbility.Targeting == "Self":
            target = actor
        else:
            target = self.GetSelectedTarget()
            if not target:
                return
        self.BeginQte(actor, target)
        self.SubMode = "QTE"

    # ============================================================
    # Hover Tooltips
    # ============================================================

    def BattleHoverTooltips(self):
        mp = pygame.mouse.get_pos()

        # Entities
        for i, E in enumerate(self.EnemyParty):
            r = self.EntityRect("Enemy", i)
            if r.collidepoint(mp):
                self.Tooltip.Show(mp, self.EntityTooltipLines(E))
                return
        for i, E in enumerate(self.PlayerParty):
            r = self.EntityRect("Player", i)
            if r.collidepoint(mp):
                self.Tooltip.Show(mp, self.EntityTooltipLines(E))
                return

        # Inventory items
        inv_panel = pygame.Rect(850, 60, 380, 360)
        if inv_panel.collidepoint(mp) and self.ActiveSave:
            items = self.GetInventorySorted()
            item_rects = self.InventoryItemRects(inv_panel, items)
            for (name, amount, rect) in item_rects:
                if rect.collidepoint(mp):
                    self.Tooltip.Show(mp, self.ItemTooltipLines(name, amount))
                    return

        # Inspect abilities hover
        sel = self.InspectSelection
        if sel:
            team, idx = sel
            panel = self.InspectPanelRect()
            if panel.collidepoint(mp):
                if team in ("Player", "Enemy"):
                    actor = self.GetEntityByTeamIndex(team, idx)
                    if actor:
                        # abilities hover
                        rects = self.GetInspectAbilityRects(actor, panel)
                        for (ability_name, rect) in rects:
                            if rect.collidepoint(mp):
                                ab = self.GetAbility(ability_name)
                                disabled = ""
                                if ab.Kind == "Passive":
                                    disabled = "(Passive)"
                                else:
                                    if self.SubMode == "Choose Action" and team == "Player" and self.ActiveEntityIndex == idx:
                                        cost = self.ComputeMpCost(actor, ab)
                                        if cost > 0 and actor.CurrentMp < cost:
                                            disabled = "Not enough MP"
                                    else:
                                        # not your turn
                                        if team == "Player":
                                            disabled = "Not your turn"
                                self.Tooltip.Show(mp, self.AbilityTooltipLines(actor, ab, DisabledReason=("" if disabled in ("(Passive)", "") else disabled)))
                                return

        # Status hover under bars
        for team, party in (("Enemy", self.EnemyParty), ("Player", self.PlayerParty)):
            for i, E in enumerate(party):
                if not E.Alive:
                    continue
                base = self.EntityRect(team, i)
                status_rects = self.StatusRectsForEntity(E, base)
                for (status_obj, rect) in status_rects:
                    if rect.collidepoint(mp):
                        lines = [status_obj.Name]
                        if status_obj.Description:
                            lines.append(status_obj.Description)
                        if status_obj.DurationMaxSeconds > 0:
                            lines.append(f"Remaining: {status_obj.DurationSeconds:.1f}s")
                        else:
                            lines.append(f"Turns: {status_obj.RemainingTurns}")
                        self.Tooltip.Show(mp, lines)
                        return

    # ============================================================
    # Inventory rects
    # ============================================================

    def InventoryItemRects(self, Panel: pygame.Rect, Items: List[Dict]) -> List[Tuple[str, int, pygame.Rect]]:
        # simple grid 3 columns
        pad = 12
        box = 78
        gap = 10
        cols = 3
        out = []
        start_y = Panel.y + 54 - self.InventoryScroll
        for idx, it in enumerate(Items):
            r = idx // cols
            c = idx % cols
            x = Panel.x + pad + c * (box + gap)
            y = start_y + r * (box + gap)
            rect = pygame.Rect(x, y, box, box)
            out.append((it["Name"], int(it["Amount"]), rect))
        return out

    # ============================================================
    # Inspect panel ability list rects
    # ============================================================

    def GetInspectAbilityRects(self, Actor: BattleEntity, Panel: pygame.Rect) -> List[Tuple[str, pygame.Rect]]:
        # ability list shown in rows
        left = Panel.x + 12
        top = Panel.y + 120
        w = Panel.width - 24
        h = 28
        gap = 6

        names = list(Actor.AbilityNames)
        rects = []
        for i, n in enumerate(names):
            rects.append((n, pygame.Rect(left, top + i * (h + gap), w, h)))
        return rects

    # ============================================================
    # Status rects under bars
    # ============================================================

    def StatusRectsForEntity(self, E: BattleEntity, R: pygame.Rect) -> List[Tuple[StatusEffect, pygame.Rect]]:
        out = []
        if not E.Statuses:
            return out
        x = R.x
        y = R.bottom + 40  # after hp/mp bars
        w = R.width
        h = 18
        gap = 4
        for i, s in enumerate(E.Statuses[:5]):  # show first 5 for now
            out.append((s, pygame.Rect(x, y + i * (h + gap), w, h)))
        return out

    # ============================================================
    # Drawing
    # ============================================================

    def Draw(self):
        self.Screen.fill((8, 8, 10))

        if self.Mode == "Title":
            self.DrawTitle()
        elif self.Mode == "Battle":
            self.DrawBattle()
        elif self.Mode == "Dev":
            self.DrawDev()

        self.Tooltip.Draw(self.Screen, self.FontSmall)
        pygame.display.flip()

    def DrawTitle(self):
        title = self.FontHuge.render("QTE ATB Battle v2", True, (240, 240, 240))
        self.Screen.blit(title, title.get_rect(center=(ScreenWidth // 2, 150)))

        hint = self.Font.render("Keyboard: SPACE for QTE, ENTER to confirm target", True, (200, 200, 200))
        self.Screen.blit(hint, hint.get_rect(center=(ScreenWidth // 2, 200)))

        for b in self.TitleButtons:
            b.Draw(self.Screen, self.Font)

        if self.ActiveSave:
            s = self.ActiveSave
            txt = self.FontSmall.render(f"Loaded: {s['Slot']}   Gold: {FormatNumber(s.get('Gold',0))}", True, (200,200,200))
            self.Screen.blit(txt, (20, ScreenHeight - 30))

    def DrawBattle(self):
        # Top time display (round only on display)
        t = self.FontSmall.render(f"Battle Time: {self.BattleTime:.1f}s", True, (220,220,220))
        self.Screen.blit(t, (20, 10))

        # DEV button
        self.DevButton.Draw(self.Screen, self.FontSmall)

        # Parties
        self.DrawParty("Enemy", self.EnemyParty)
        self.DrawParty("Player", self.PlayerParty)

        # Inventory panel
        self.DrawInventoryPanel()

        # Inspect panel
        self.DrawInspectPanel()

        # Floating numbers
        for f in self.FloatingNumbers:
            font = pygame.font.Font(FontName, f.Size)
            s = font.render(f.Text, True, f.Color)
            self.Screen.blit(s, s.get_rect(center=(int(f.X), int(f.Y))))

        # QTE overlay
        if self.SubMode == "QTE":
            self.DrawQte()

        # Battle end rewards
        if self.SubMode == "Battle End":
            self.DrawBattleEnd()

    def DrawParty(self, Team: str, Party: List[BattleEntity]):
        for i, E in enumerate(Party):
            R = self.EntityRect(Team, i)

            # highlight if active actor
            is_active = (self.BattleFrozen and self.ActiveTeam == Team and self.ActiveEntityIndex == i and self.SubMode in ("Choose Action","Choose Target","QTE","Enemy Act"))
            border_col = (220, 220, 120) if is_active else (110, 110, 125)

            # target highlight during target selection
            if self.SubMode == "Choose Target":
                targets = self.GetTargetList()
                if targets:
                    sel_t = self.GetSelectedTarget()
                    if sel_t is E:
                        border_col = (140, 220, 255)

            # entity box
            pygame.draw.rect(self.Screen, (36, 36, 44), R, border_radius=12)
            pygame.draw.rect(self.Screen, border_col, R, width=3, border_radius=12)

            # name (top)
            name = self.FontSmall.render(E.Name, True, (240,240,240))
            self.Screen.blit(name, name.get_rect(center=(R.centerx, R.y + 22)))

            # XP bar (players only) bottom of name box
            if Team == "Player" and self.ActiveSave:
                party_entry = None
                for P in self.ActiveSave.get("Party", []):
                    if P["Name"] == E.Name:
                        party_entry = P
                        break
                if party_entry:
                    level = int(party_entry.get("Level", E.Level))
                    xp = int(party_entry.get("Xp", 0))
                    need = self.XpToNextLevel(level)
                    frac = Clamp(xp / max(1, need), 0.0, 1.0)
                    bar = pygame.Rect(R.x + 10, R.y + R.height - 16, R.width - 20, 8)
                    pygame.draw.rect(self.Screen, (20,20,22), bar, border_radius=6)
                    pygame.draw.rect(self.Screen, (200,170,60), pygame.Rect(bar.x, bar.y, int(bar.w * frac), bar.h), border_radius=6)

            # ATB bar (top small)
            atb_w = R.width - 16
            atb_rect = pygame.Rect(R.x + 8, R.y - 16, atb_w, 8)
            pygame.draw.rect(self.Screen, (20,20,22), atb_rect, border_radius=6)

            # show as /100 based on time until action (0 ready => 100)
            # when frozen, show current readiness
            remain = max(0.0, E.NextActionTime - self.BattleTime)
            # map remain to readiness. If remain >= 5 => 0, if 0 => 100
            readiness = int(Clamp(100.0 * (1.0 - Clamp(remain / 5.0, 0.0, 1.0)), 0.0, 100.0))
            pygame.draw.rect(self.Screen, (90, 200, 120), pygame.Rect(atb_rect.x, atb_rect.y, int(atb_rect.w * readiness / 100.0), atb_rect.h), border_radius=6)
            atb_txt = self.FontSmall.render(f"{readiness}/100", True, (240,240,240))
            self.Screen.blit(atb_txt, atb_txt.get_rect(center=(R.centerx, atb_rect.centery)))

            # bars under box
            self.DrawBars(E, R)

            # status list under bars
            self.DrawStatuses(E, R)

            # dead overlay
            if not E.Alive:
                s = self.FontBig.render("KO", True, (255,90,90))
                self.Screen.blit(s, s.get_rect(center=R.center))

    def DrawBars(self, E: BattleEntity, R: pygame.Rect):
        barw = R.width
        hp_y = R.bottom + 8
        mp_y = R.bottom + 24
        hp = pygame.Rect(R.x, hp_y, barw, 10)
        mp = pygame.Rect(R.x, mp_y, barw, 10)

        pygame.draw.rect(self.Screen, (28,28,34), hp, border_radius=6)
        pygame.draw.rect(self.Screen, (28,28,34), mp, border_radius=6)

        hp_max = max(1.0, E.MaxHp())
        hp_lag = Clamp(E.LagHp / hp_max, 0.0, 1.0)
        hp_cur = Clamp(E.CurrentHp / hp_max, 0.0, 1.0)

        # lag (damaged/healed region highlight)
        pygame.draw.rect(self.Screen, (110,40,40), pygame.Rect(hp.x, hp.y, int(hp.w * hp_lag), hp.h), border_radius=6)
        pygame.draw.rect(self.Screen, (210,70,70), pygame.Rect(hp.x, hp.y, int(hp.w * hp_cur), hp.h), border_radius=6)

        mp_max = max(1.0, E.MaxMp())
        mp_lag = Clamp(E.LagMp / mp_max, 0.0, 1.0)
        mp_cur = Clamp(E.CurrentMp / mp_max, 0.0, 1.0)

        pygame.draw.rect(self.Screen, (35,50,120), pygame.Rect(mp.x, mp.y, int(mp.w * mp_lag), mp.h), border_radius=6)
        pygame.draw.rect(self.Screen, (65,120,255), pygame.Rect(mp.x, mp.y, int(mp.w * mp_cur), mp.h), border_radius=6)

        # numbers on bars (centered)
        hp_txt = self.FontSmall.render(f"{FormatNumber(int(E.CurrentHp))}/{FormatNumber(int(hp_max))}", True, (245,245,245))
        mp_txt = self.FontSmall.render(f"{FormatNumber(int(E.CurrentMp))}/{FormatNumber(int(mp_max))}", True, (245,245,245))
        self.Screen.blit(hp_txt, hp_txt.get_rect(center=hp.center))
        self.Screen.blit(mp_txt, mp_txt.get_rect(center=mp.center))

    def DrawStatuses(self, E: BattleEntity, R: pygame.Rect):
        rects = self.StatusRectsForEntity(E, R)
        for s, rr in rects:
            # background bar behind timed statuses
            pygame.draw.rect(self.Screen, (18,18,20), rr, border_radius=6)
            if s.DurationMaxSeconds > 0:
                frac = Clamp(s.DurationSeconds / max(0.01, s.DurationMaxSeconds), 0.0, 1.0)
                pygame.draw.rect(self.Screen, (70,70,90), pygame.Rect(rr.x, rr.y, int(rr.w * frac), rr.h), border_radius=6)

            label = s.Name
            if s.DurationMaxSeconds > 0:
                label = f"{s.Name} ({s.DurationSeconds:.1f}s)"
            else:
                label = f"{s.Name} ({s.RemainingTurns}t)"
            txt = self.FontSmall.render(label, True, (235,235,235))
            self.Screen.blit(txt, txt.get_rect(midleft=(rr.x + 6, rr.centery)))

    def DrawInventoryPanel(self):
        panel = pygame.Rect(850, 60, 380, 360)
        pygame.draw.rect(self.Screen, (18,18,22), panel, border_radius=14)
        pygame.draw.rect(self.Screen, (120,120,140), panel, width=2, border_radius=14)

        gold = self.ActiveSave.get("Gold", 0) if self.ActiveSave else 0
        title = self.Font.render(f"Inventory   Gold: {FormatNumber(gold)}", True, (240,240,240))
        self.Screen.blit(title, (panel.x + 14, panel.y + 12))

        if not self.ActiveSave:
            return

        items = self.GetInventorySorted()
        rects = self.InventoryItemRects(panel, items)
        for name, amount, r in rects:
            # clip draw to panel
            if r.bottom < panel.y + 50 or r.y > panel.bottom - 10:
                continue

            pygame.draw.rect(self.Screen, (40,40,48), r, border_radius=12)
            pygame.draw.rect(self.Screen, (110,110,130), r, width=2, border_radius=12)

            # item name centered
            nm = self.FontSmall.render(name, True, (240,240,240))
            self.Screen.blit(nm, nm.get_rect(center=r.center))

            # amount upper-right
            amt = self.FontSmall.render(str(amount), True, (240,240,240))
            self.Screen.blit(amt, amt.get_rect(topright=(r.right - 6, r.top + 4)))

    def DrawInspectPanel(self):
        panel = self.InspectPanelRect()
        pygame.draw.rect(self.Screen, (18,18,22), panel, border_radius=14)
        pygame.draw.rect(self.Screen, (120,120,140), panel, width=2, border_radius=14)

        header = self.Font.render("Inspect", True, (240,240,240))
        self.Screen.blit(header, (panel.x + 14, panel.y + 10))

        if not self.InspectSelection:
            return
        team, idx = self.InspectSelection
        ent = self.GetEntityByTeamIndex(team, idx)
        if not ent:
            return

        # Basic info
        y = panel.y + 44
        lines = [
            f"{ent.Name}  (Level {ent.Level})",
            f"Vitality: {FormatNumber(int(self.EffectiveStat(ent,'Vitality')))}",
            f"Power: {FormatNumber(int(self.EffectiveStat(ent,'Power')))}",
            f"Dexterity: {FormatNumber(int(self.EffectiveStat(ent,'Dexterity')))}",
            f"Precision: {FormatNumber(int(self.EffectiveStat(ent,'Precision')))}",
        ]
        for L in lines:
            s = self.FontSmall.render(L, True, (220,220,220))
            self.Screen.blit(s, (panel.x + 14, y))
            y += 18

        # Abilities section
        y += 4
        s = self.Font.render("Abilities", True, (240,240,240))
        self.Screen.blit(s, (panel.x + 14, y))
        y += 26

        # Abilities list (clickable if player and their turn)
        rects = self.GetInspectAbilityRects(ent, panel)
        for ability_name, rr in rects:
            if rr.bottom > panel.bottom - 10:
                break
            ab = self.GetAbility(ability_name)
            can_click = True
            disabled_reason = ""

            if ab.Kind == "Passive":
                can_click = False
                disabled_reason = "(Passive)"
            if team == "Player":
                if not (self.SubMode == "Choose Action" and self.ActiveTeam == "Player" and self.ActiveEntityIndex == idx):
                    can_click = False
                else:
                    cost = self.ComputeMpCost(ent, ab)
                    if cost > 0 and ent.CurrentMp < cost:
                        can_click = False
                        disabled_reason = "Not enough MP"

            col_bg = (34,34,40) if can_click else (24,24,28)
            col_border = (120,120,140) if can_click else (80,80,90)
            pygame.draw.rect(self.Screen, col_bg, rr, border_radius=10)
            pygame.draw.rect(self.Screen, col_border, rr, width=2, border_radius=10)

            label = ability_name
            cost = self.ComputeMpCost(ent, ab)
            if cost > 0:
                label = f"{ability_name}  ({FormatNumber(cost)} MP)"
            txt = self.FontSmall.render(label, True, (240,240,240) if can_click else (150,150,160))
            self.Screen.blit(txt, txt.get_rect(midleft=(rr.x + 8, rr.centery)))

            if disabled_reason and disabled_reason != "(Passive)":
                tag = self.FontSmall.render(disabled_reason, True, (255,170,120))
                self.Screen.blit(tag, tag.get_rect(midright=(rr.right - 8, rr.centery)))

        # Drop table for enemies
        if team == "Enemy":
            y2 = panel.y + 44
            drop_y = panel.y + panel.height - 70
            s2 = self.Font.render("Drop Table", True, (240,240,240))
            self.Screen.blit(s2, (panel.x + 14, drop_y))
            dy = drop_y + 24
            for entry in ent.DropTable[:3]:
                qty = entry["Quantity"]
                item = entry["Item"]
                num = entry["Chance Numerator"]
                den = entry["Chance Denominator"]
                line = f"{qty}x {item}  ({num}/{den})"
                ss = self.FontSmall.render(line, True, (220,220,220))
                self.Screen.blit(ss, (panel.x + 14, dy))
                dy += 18

    def DrawQte(self):
        # dim background
        overlay = pygame.Surface((ScreenWidth, ScreenHeight), pygame.SRCALPHA)
        overlay.fill((0,0,0,150))
        self.Screen.blit(overlay, (0,0))

        cx, cy = ScreenWidth // 2, ScreenHeight // 2 + 10

        # ring zones
        center = self.QteRadii["Center"]
        vital = self.QteRadii["VitalOuter"]
        crit = self.QteRadii["CritOuter"]
        hit = self.QteRadii["HitOuter"]

        # draw static rings
        pygame.draw.circle(self.Screen, (90,90,100), (cx,cy), int(hit), width=3)
        pygame.draw.circle(self.Screen, (120,120,140), (cx,cy), int(crit), width=3)
        pygame.draw.circle(self.Screen, (150,140,80), (cx,cy), int(vital), width=3)
        pygame.draw.circle(self.Screen, (120,120,120), (cx,cy), int(center), width=3)

        # labels
        self.Screen.blit(self.FontSmall.render("HIT", True, (220,220,220)), (cx + hit + 10, cy - 8))
        self.Screen.blit(self.FontSmall.render("CRIT", True, (255,235,80)), (cx + crit + 10, cy - 8))
        self.Screen.blit(self.FontSmall.render("VITAL", True, (255,80,80)), (cx + vital + 10, cy - 8))

        # moving ring
        rr = int(max(1, self.QteRadius))
        pygame.draw.circle(self.Screen, (240,240,240), (cx,cy), rr, width=6)

        tip = self.Font.render("Press SPACE on the ring timing", True, (240,240,240))
        self.Screen.blit(tip, tip.get_rect(center=(cx, cy - hit - 50)))

        if self.QtePressed and self.QteResult:
            res = self.FontHuge.render(self.QteResult, True, (255,80,80) if self.QteResult=="Vital" else (255,235,80) if self.QteResult=="Crit" else (240,240,240))
            self.Screen.blit(res, res.get_rect(center=(cx, cy + hit + 55)))

    def DrawBattleEnd(self):
        overlay = pygame.Surface((ScreenWidth, ScreenHeight), pygame.SRCALPHA)
        overlay.fill((0,0,0,170))
        self.Screen.blit(overlay, (0,0))

        won = self.BattleRewards.get("PlayerWon", False)
        title = self.FontHuge.render("Victory!" if won else "Defeat...", True, (240,240,240))
        self.Screen.blit(title, title.get_rect(center=(ScreenWidth//2, 160)))

        if won:
            xp = self.BattleRewards.get("TotalXp", 0)
            gold = self.BattleRewards.get("TotalGold", 0)
            loot = self.BattleRewards.get("Loot", [])

            lines = [
                f"XP Gained: {FormatNumber(xp)} (each party member)",
                f"Gold Gained: {FormatNumber(gold)}",
                "Loot:",
                ]
        confirm = self.Font.render("Press ENTER to return to Title", True, (240,240,240))
        self.Screen.blit(confirm, confirm.get_rect(center=(ScreenWidth//2, 560)))
        
    # ============================================================
    # Leveling
    # ============================================================

    def XpToNextLevel(self, Level: int) -> int:
        # starts at 1000 and doubles every 10 levels
        base = 1000
        tier = Level // 10
        return int(base * (2 ** tier))

    # ============================================================
    # Dev Menu
    # ============================================================

    def DevHandleClick(self, MousePos):
        # Tab clicks
        for i, tab in enumerate(self.DevTabs()):
            if self.DevTabRect(tab, i).collidepoint(MousePos):
                self.DevTab = tab
                self.DevSelectedName = ""
                self.DevScroll = 0
                return

        # Save db button
        if self.DevSaveRect().collidepoint(MousePos):
            self.SaveDatabase()
            return

        # Left list selection area
        list_rect = pygame.Rect(20, 110, 300, 580)
        if list_rect.collidepoint(MousePos):
            names = self.DevCurrentNames()
            y0 = list_rect.y + 10 - self.DevScroll
            h = 26
            # FIX: correct selection mapping (no +1 bug)
            idx = int((MousePos[1] - y0) // h)
            if 0 <= idx < len(names):
                self.DevSelectedName = names[idx]
            return

    def DevCurrentNames(self) -> List[str]:
        if self.DevTab == "Entities":
            return [e["Name"] for e in self.EntitiesDb]
        if self.DevTab == "Abilities":
            return [a["Name"] for a in self.AbilitiesDb]
        if self.DevTab == "Items":
            return [i["Name"] for i in self.ItemsDb]
        if self.DevTab == "Areas":
            return [a["Name"] for a in self.AreasDb]
        if self.DevTab == "Balance":
            return sorted(list(self.BalanceDb.keys()))
        return []

    def DrawDev(self):
        self.Screen.fill((10,10,12))
        title = self.FontHuge.render("DEV MENU", True, (240,240,240))
        self.Screen.blit(title, (20, 10))

        # Tabs
        for i, tab in enumerate(self.DevTabs()):
            r = self.DevTabRect(tab, i)
            active = (tab == self.DevTab)
            pygame.draw.rect(self.Screen, (40,40,50) if active else (28,28,34), r, border_radius=10)
            pygame.draw.rect(self.Screen, (160,160,190) if active else (90,90,110), r, width=2, border_radius=10)
            t = self.FontSmall.render(tab, True, (240,240,240))
            self.Screen.blit(t, t.get_rect(center=r.center))

        # Save button
        sb = self.DevSaveRect()
        pygame.draw.rect(self.Screen, (40,40,50), sb, border_radius=10)
        pygame.draw.rect(self.Screen, (160,160,190), sb, width=2, border_radius=10)
        st = self.FontSmall.render("SAVE DB", True, (240,240,240))
        self.Screen.blit(st, st.get_rect(center=sb.center))

        # Left list
        list_rect = pygame.Rect(20, 110, 300, 580)
        pygame.draw.rect(self.Screen, (18,18,22), list_rect, border_radius=14)
        pygame.draw.rect(self.Screen, (120,120,140), list_rect, width=2, border_radius=14)

        names = self.DevCurrentNames()
        y = list_rect.y + 10 - self.DevScroll
        for n in names:
            rr = pygame.Rect(list_rect.x + 10, y, list_rect.w - 20, 24)
            if rr.bottom >= list_rect.y and rr.top <= list_rect.bottom:
                sel = (n == self.DevSelectedName)
                pygame.draw.rect(self.Screen, (40,40,50) if sel else (26,26,30), rr, border_radius=8)
                txt = self.FontSmall.render(n, True, (240,240,240))
                self.Screen.blit(txt, txt.get_rect(midleft=(rr.x + 8, rr.centery)))
            y += 26

        # Right editor area (placeholder but functional tab switching)
        editor = pygame.Rect(340, 110, 920, 580)
        pygame.draw.rect(self.Screen, (18,18,22), editor, border_radius=14)
        pygame.draw.rect(self.Screen, (120,120,140), editor, width=2, border_radius=14)

        hdr = self.Font.render(f"{self.DevTab} Editor", True, (240,240,240))
        self.Screen.blit(hdr, (editor.x + 14, editor.y + 12))

        # Basic content view so you can verify tabs work
        y = editor.y + 54
        if self.DevTab != "Balance":
            if self.DevSelectedName:
                data = None
                if self.DevTab == "Entities":
                    data = self.EntitiesByName.get(self.DevSelectedName)
                elif self.DevTab == "Abilities":
                    data = self.AbilitiesByName.get(self.DevSelectedName)
                elif self.DevTab == "Items":
                    data = self.ItemsByName.get(self.DevSelectedName)
                elif self.DevTab == "Areas":
                    data = self.AreasByName.get(self.DevSelectedName)
                if data:
                    lines = json.dumps(data, indent=2, ensure_ascii=False).splitlines()
                    # moved up so bottom doesn't overflow as much
                    for line in lines[:26]:
                        s = self.FontSmall.render(line[:120], True, (220,220,220))
                        self.Screen.blit(s, (editor.x + 14, y))
                        y += 18
        else:
            # Balance keys list
            for k in sorted(self.BalanceDb.keys()):
                s = self.FontSmall.render(f"{k}: {self.BalanceDb[k]}", True, (220,220,220))
                self.Screen.blit(s, (editor.x + 14, y))
                y += 18
                if y > editor.bottom - 20:
                    break

# ============================================================
# Launch
# ============================================================


def main():
    EnsureFolder(SavesFolder)
    Game().Run()


if __name__ == "__main__":
    main()

