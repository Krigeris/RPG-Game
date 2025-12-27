import os

from .utils import (
    BaselineAbilityDelay,
    DataFolder,
    EnemyQteBaselineAttack,
    EnemyQteShiftStrength,
    EnsureFolder,
    SaveJson,
)


def CreateDefaultData():
    EnsureFolder(DataFolder)

    entities_path = os.path.join(DataFolder, "Entities.json")
    abilities_path = os.path.join(DataFolder, "Abilities.json")
    items_path = os.path.join(DataFolder, "Items.json")
    areas_path = os.path.join(DataFolder, "Areas.json")
    encounters_path = os.path.join(DataFolder, "Encounters.json")
    balance_path = os.path.join(DataFolder, "Balance.json")

    if not os.path.exists(items_path):
        items = [
            {"Name": "Potion", "Value": 25, "Tier": 1, "Description": "Restores HP (uses QTE)."},
            {"Name": "Ether", "Value": 35, "Tier": 1, "Description": "Restores MP (uses QTE)."},
            {
                "Name": "Iron Sword",
                "Value": 120,
                "Tier": 2,
                "Description": "A basic blade. (placeholder for equipment later)",
            },
        ]
        SaveJson(items_path, items)

    if not os.path.exists(abilities_path):
        abilities = [
            {
                "Name": "Attack",
                "Kind": "Attack",
                "Targeting": "Enemy Single",
                "Base Delay": BaselineAbilityDelay,
                "Mult": 1.0,
                "Base MP Cost": 0,
                "Description": "Basic attack.",
            },
            {
                "Name": "Defend",
                "Kind": "Defend",
                "Targeting": "Self",
                "Base Delay": 2.0,
                "Mult": 1.0,
                "Base MP Cost": 0,
                "Description": "1-turn buff: -25% damage taken, x2 regen, +25% defense QTE window.",
            },
            {
                "Name": "Quick Jab",
                "Kind": "Attack",
                "Targeting": "Enemy Single",
                "Base Delay": 1.5,
                "Mult": 0.7,
                "Base MP Cost": 8,
                "Description": "Fast, weaker hit.",
            },
            {
                "Name": "Power Strike",
                "Kind": "Attack",
                "Targeting": "Enemy Single",
                "Base Delay": 2.5,
                "Mult": 1.45,
                "Base MP Cost": 12,
                "Description": "Stronger hit.",
            },
            {
                "Name": "Cure",
                "Kind": "Heal",
                "Targeting": "Ally Single",
                "Base Delay": 2.0,
                "Mult": 1.35,
                "Base MP Cost": 16,
                "Description": "Single-target heal.",
            },
            {
                "Name": "Regen",
                "Kind": "Buff",
                "Targeting": "Ally Single",
                "Base Delay": 2.0,
                "Mult": 1.0,
                "Base MP Cost": 12,
                "Description": "Heal over time.",
            },
            {
                "Name": "Rally",
                "Kind": "Buff",
                "Targeting": "Ally Single",
                "Base Delay": 2.0,
                "Mult": 1.0,
                "Base MP Cost": 14,
                "Description": "Power +20%.",
            },
            {
                "Name": "Focus",
                "Kind": "Buff",
                "Targeting": "Ally Single",
                "Base Delay": 2.0,
                "Mult": 1.0,
                "Base MP Cost": 12,
                "Description": "Precision +25%.",
            },
        ]
        SaveJson(abilities_path, abilities)

    if not os.path.exists(entities_path):
        entities = [
            {
                "Name": "Hero",
                "Level": 6,
                "Weights": {"Vitality": 1.1, "Power": 1.05, "Dexterity": 1.0, "Precision": 1.0},
                "Abilities": ["Attack", "Power Strike", "Regen", "Rally"],
                "Learnset": [],
                "Drop Table": [],
            },
            {
                "Name": "Rogue",
                "Level": 6,
                "Weights": {"Vitality": 0.95, "Power": 1.05, "Dexterity": 1.2, "Precision": 1.3},
                "Abilities": ["Attack", "Quick Jab", "Focus"],
                "Learnset": [],
                "Drop Table": [],
            },
            {
                "Name": "Green Slime",
                "Level": 5,
                "Weights": {"Vitality": 0.9, "Power": 0.6, "Dexterity": 0.5, "Precision": 0.4},
                "Abilities": ["Attack"],
                "Learnset": [],
                "Drop Table": [
                    {"Quantity": 1, "Item": "Potion", "Chance Numerator": 1, "Chance Denominator": 6},
                ],
            },
            {
                "Name": "Goblin",
                "Level": 6,
                "Weights": {"Vitality": 1.1, "Power": 0.9, "Dexterity": 1.1, "Precision": 1.1},
                "Abilities": ["Attack", "Power Strike"],
                "Learnset": [],
                "Drop Table": [
                    {"Quantity": 1, "Item": "Iron Sword", "Chance Numerator": 1, "Chance Denominator": 10},
                    {"Quantity": 1, "Item": "Ether", "Chance Numerator": 1, "Chance Denominator": 8},
                ],
            },
        ]
        SaveJson(entities_path, entities)

    if not os.path.exists(areas_path):
        areas = [
            {
                "Name": "Starter Field",
                "Description": "A simple test area.",
                "Encounters": ["Field Encounter 1", "Field Encounter 2"],
            }
        ]
        SaveJson(areas_path, areas)

    if not os.path.exists(encounters_path):
        encounters = [
            {"Name": "Field Encounter 1", "Area": "Starter Field", "Enemy Party": ["Green Slime", "Green Slime"]},
            {"Name": "Field Encounter 2", "Area": "Starter Field", "Enemy Party": ["Goblin", "Green Slime"]},
        ]
        SaveJson(encounters_path, encounters)

    if not os.path.exists(balance_path):
        balance = {
            "Enemy QTE Baseline Attack": EnemyQteBaselineAttack,
            "Enemy QTE Shift Strength": EnemyQteShiftStrength,
            "Precision Ratio Clamp Min": 0.60,
            "Precision Ratio Clamp Max": 1.60,
            "QTE Ring Speed": 420.0,
            "QTE Vital Zone Min Width": 10.0,
            "QTE Crit Zone Min Width": 18.0,
        }
        SaveJson(balance_path, balance)
