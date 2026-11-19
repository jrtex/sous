"""Deterministic tools the LLM calls for anything numeric.

Unit conversion is same-dimension only (volume<->volume, mass<->mass,
temperature, time). Volume<->weight is deliberately refused: it depends on
ingredient density and we don't guess.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pint

if TYPE_CHECKING:
    from sous.recipes import Amount, Recipe

ureg = pint.UnitRegistry()

# Cooking spellings -> pint unit names. Cups/pints/quarts are US customary.
_ALIASES = {
    "t": "teaspoon", "tsp": "teaspoon", "tsps": "teaspoon", "teaspoon": "teaspoon", "teaspoons": "teaspoon",
    "tbsp": "tablespoon", "tbsps": "tablespoon", "tbs": "tablespoon", "tablespoon": "tablespoon",
    "tablespoons": "tablespoon",
    "c": "cup", "cup": "cup", "cups": "cup",
    "fl oz": "fluid_ounce", "floz": "fluid_ounce", "fluid ounce": "fluid_ounce", "fluid ounces": "fluid_ounce",
    "pt": "pint", "pint": "pint", "pints": "pint",
    "qt": "quart", "quart": "quart", "quarts": "quart",
    "gal": "gallon", "gallon": "gallon", "gallons": "gallon",
    "ml": "milliliter", "milliliter": "milliliter", "milliliters": "milliliter", "millilitre": "milliliter",
    "millilitres": "milliliter",
    "cl": "centiliter", "dl": "deciliter",
    "l": "liter", "liter": "liter", "liters": "liter", "litre": "liter", "litres": "liter",
    "g": "gram", "gr": "gram", "gram": "gram", "grams": "gram", "gramme": "gram", "grammes": "gram",
    "kg": "kilogram", "kilo": "kilogram", "kilos": "kilogram", "kilogram": "kilogram", "kilograms": "kilogram",
    "mg": "milligram",
    "oz": "ounce", "ounce": "ounce", "ounces": "ounce",
    "lb": "pound", "lbs": "pound", "pound": "pound", "pounds": "pound",
    "°c": "degC", "degc": "degC", "celsius": "degC", "centigrade": "degC",
    "°f": "degF", "degf": "degF", "fahrenheit": "degF", "f": "degF",
    "s": "second", "sec": "second", "secs": "second", "second": "second", "seconds": "second",
    "min": "minute", "mins": "minute", "minute": "minute", "minutes": "minute",
    "h": "hour", "hr": "hour", "hrs": "hour", "hour": "hour", "hours": "hour",
}
# "C" alone is ambiguous with cup; treat uppercase C as Celsius, lowercase c as cup.
_CASE_SENSITIVE = {"C": "degC", "F": "degF", "T": "tablespoon"}

_DIMENSION_NAMES = {
    "[length] ** 3": "volume",
    "[mass]": "weight",
    "[temperature]": "temperature",
    "[time]": "time",
}


class ConversionError(ValueError):
    pass


def normalize_unit(unit: str) -> str:
    u = unit.strip().rstrip(".")
    if u in _CASE_SENSITIVE:
        return _CASE_SENSITIVE[u]
    key = u.lower()
    if key in _ALIASES:
        return _ALIASES[key]
    try:
        ureg.parse_units(u)
        return u
    except Exception as e:  # pint raises several error types
        raise ConversionError(f"Unknown unit: {unit!r}") from e


def _dimension(unit_name: str) -> str:
    dim = str(ureg.Quantity(1, unit_name).dimensionality)
    return _DIMENSION_NAMES.get(dim, dim)


def _round(value: float) -> float:
    if value == 0:
        return 0.0
    # 3 significant figures is plenty in a kitchen.
    from math import floor, log10

    return round(value, max(0, 2 - floor(log10(abs(value)))))


def convert_units(quantity: float, from_unit: str, to_unit: str) -> dict:
    """Convert a quantity between units of the same dimension.

    Returns {"ok": True, "value", "unit", "display"} or {"ok": False, "error"}.
    """
    try:
        src, dst = normalize_unit(from_unit), normalize_unit(to_unit)
    except ConversionError as e:
        return {"ok": False, "error": str(e)}

    src_dim, dst_dim = _dimension(src), _dimension(dst)
    if src_dim != dst_dim:
        return {
            "ok": False,
            "error": (
                f"Cannot convert {src_dim} to {dst_dim}: it depends on the ingredient's density, "
                "so no precise conversion is possible."
            ),
        }

    value = ureg.Quantity(float(quantity), src).to(dst).magnitude
    value = _round(value)
    return {"ok": True, "value": value, "unit": to_unit, "display": f"{value:g} {to_unit}"}


def to_seconds(amount: "Amount") -> float | None:
    """Timer length in seconds. For a range like '6-8 minutes', the lower bound (check early)."""
    rng = amount.range
    if rng is None or not amount.unit:
        return None
    value = rng[0]
    try:
        unit = normalize_unit(amount.unit)
        q = ureg.Quantity(value, unit)
        if _dimension(unit) != "time":
            return None
        return float(q.to("second").magnitude)
    except ConversionError:
        return None


def total_ingredient(recipe: "Recipe", name: str) -> dict:
    """Sum an ingredient across every step it appears in.

    Quantities in compatible units are added (expressed in the first unit seen);
    incompatible or non-numeric ones are listed separately.
    """
    needle = name.strip().lower()
    all_hits = [(s.number, i) for s in recipe.steps for i in s.ingredients]
    hits = [h for h in all_hits if h[1].name.lower() == needle]
    if not hits:  # whole-word match: "salt" finds "kosher salt" but not "unsalted butter"
        pattern = re.compile(rf"\b{re.escape(needle)}s?\b")
        hits = [h for h in all_hits if pattern.search(h[1].name.lower())]
    if not hits:
        return {"ok": False, "error": f"No ingredient matching {name!r} in this recipe."}
    names = list(dict.fromkeys(i.name for _, i in hits))
    if len(names) > 1:
        return {"ok": False, "error": f"{name!r} matches several ingredients; ask again with one of: {names}"}

    totals: list[list] = []  # [unit_str, pint_unit_or_None, value]
    other: list[str] = []
    for _, ing in hits:
        amt = ing.amount
        value = amt.value
        if value is None:
            other.append(str(amt) or "unspecified amount")
            continue
        try:
            pu = normalize_unit(amt.unit) if amt.unit else None
        except ConversionError:
            pu = None
        for t in totals:
            if pu is None and t[1] is None and t[0] == amt.unit:
                t[2] += value
                break
            if pu and t[1] and _dimension(pu) == _dimension(t[1]):
                t[2] += ureg.Quantity(value, pu).to(t[1]).magnitude
                break
        else:
            totals.append([amt.unit, pu, value])

    parts = [f"{_round(v):g} {u}".strip() for u, _, v in totals] + other
    return {
        "ok": True,
        "ingredient": hits[0][1].name,
        "total": " + ".join(parts),
        "by_step": [{"step": n, "amount": str(i.amount) or "unspecified"} for n, i in hits],
    }
