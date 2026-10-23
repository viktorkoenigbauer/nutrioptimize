import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

NUTRIENT_UNITS = {
    "energy_kcal": "kcal",
    "protein_g": "g",
    "carbohydrate_g": "g",
    "fat_g": "g",
    "saturated_fat_g": "g",
    "monounsaturated_fat_g": "g",
    "polyunsaturated_fat_g": "g",
    "trans_fat_g": "g",
    "cholesterol_mg": "mg",
    "fiber_g": "g",
    "sugar_g": "g",
    "added_sugar_g": "g",
    "salt_g": "g",
    "sodium_mg": "mg",
    "water_g": "g",
    "alcohol_g": "g",
    "vitamin_a_ug": "ug",
    "vitamin_b1_mg": "mg",
    "vitamin_b2_mg": "mg",
    "vitamin_b3_mg": "mg",
    "vitamin_b5_mg": "mg",
    "vitamin_b6_mg": "mg",
    "vitamin_b7_ug": "ug",
    "folate_ug": "ug",
    "vitamin_b12_ug": "ug",
    "vitamin_c_mg": "mg",
    "vitamin_d_ug": "ug",
    "vitamin_e_mg": "mg",
    "vitamin_k_ug": "ug",
    "potassium_mg": "mg",
    "calcium_mg": "mg",
    "iron_mg": "mg",
    "magnesium_mg": "mg",
    "phosphorus_mg": "mg",
    "zinc_mg": "mg",
    "copper_mg": "mg",
    "manganese_mg": "mg",
    "selenium_ug": "ug",
    "iodine_ug": "ug",
    "chloride_mg": "mg",
    "sulfur_mg": "mg",
    "fluoride_mg": "mg",
    "fluorine_mg": "mg",
    "biotin_ug": "ug",
    "choline_mg": "mg",
    "chromium_ug": "ug",
    "cobalt_ug": "ug",
    "molybdenum_ug": "ug",
    "boron_mg": "mg",
    "silicon_mg": "mg",
    "arsenic_ug": "ug",
    "rubidium_ug": "ug",
    "tin_mg": "mg",
    "vanadium_ug": "ug",
}


@dataclass(frozen=True)
class Nutrient:
    code: str
    amount: Decimal
    unit: str


@dataclass(frozen=True)
class NormalizedFoodEntry:
    source: str
    external_id: str
    consumed_at: datetime
    local_date: date
    timezone: str
    meal: str
    food_name: str
    quantity: Decimal | None
    unit: str | None
    nutrients: list[Nutrient]
    raw_payload: Mapping[str, Any]
    payload_hash: str


@dataclass(frozen=True)
class NormalizedDailyGoal:
    """One source's targets for a local calendar day.

    ``effective`` is the target YAZIO currently applies, while ``unmodified``
    is YAZIO's calculated value before a manual override.  Activity energy is
    kept separate because adding it to the target is a user preference rather
    than a universally valid nutrition rule.
    """

    source: str
    local_date: date
    timezone: str
    effective: list[Nutrient]
    unmodified: list[Nutrient]
    activity_energy_kcal: Decimal | None
    consume_activity_energy: bool | None
    raw_payload: Mapping[str, Any]
    payload_hash: str


def canonical_payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_fixture_entry(
    payload: Mapping[str, Any], timezone_name: str
) -> NormalizedFoodEntry:
    timezone = ZoneInfo(timezone_name)
    consumed_at = datetime.fromisoformat(str(payload["consumed_at"]))
    if consumed_at.tzinfo is None:
        raise ValueError("consumed_at must include an explicit UTC offset")
    local_date = consumed_at.astimezone(timezone).date()

    nutrients = []
    for code, raw_amount in dict(payload.get("nutrients", {})).items():
        if code not in NUTRIENT_UNITS:
            raise ValueError(f"Unknown nutrient code: {code}")
        nutrients.append(
            Nutrient(
                code=code, amount=Decimal(str(raw_amount)), unit=NUTRIENT_UNITS[code]
            )
        )

    return NormalizedFoodEntry(
        source="fixture",
        external_id=str(payload["id"]),
        consumed_at=consumed_at,
        local_date=local_date,
        timezone=timezone_name,
        meal=str(payload["meal"]),
        food_name=str(payload["food_name"]),
        quantity=Decimal(str(payload["quantity"]))
        if payload.get("quantity") is not None
        else None,
        unit=str(payload["unit"]) if payload.get("unit") is not None else None,
        nutrients=nutrients,
        raw_payload=payload,
        payload_hash=canonical_payload_hash(payload),
    )


def aggregate_nutrients(
    entries: Iterable[NormalizedFoodEntry],
) -> dict[str, dict[str, Any]]:
    totals = {}
    for entry in entries:
        for nutrient in entry.nutrients:
            current = totals.setdefault(
                nutrient.code, {"amount": Decimal(0), "unit": nutrient.unit}
            )
            if current["unit"] != nutrient.unit:
                raise ValueError(f"Unit mismatch for nutrient {nutrient.code}")
            current["amount"] += nutrient.amount
    return totals
