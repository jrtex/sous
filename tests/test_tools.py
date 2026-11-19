from pathlib import Path

import pytest

from sous.recipes import RecipeRepository
from sous.tools import convert_units, total_ingredient

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "q,src,dst,expected",
    [
        (1, "cup", "ml", 237),
        (3, "tsp", "tbsp", 1),
        (250, "ml", "cups", 1.06),
        (1, "lb", "g", 454),
        (100, "g", "oz", 3.53),
        (180, "C", "F", 356),
        (350, "°F", "°C", 177),
        (1.5, "hours", "minutes", 90),
        (2, "T", "t", 6),
    ],
)
def test_convert_same_dimension(q, src, dst, expected):
    r = convert_units(q, src, dst)
    assert r["ok"], r
    assert r["value"] == pytest.approx(expected, rel=0.01)


def test_convert_refuses_volume_to_weight():
    r = convert_units(1, "cup", "g")
    assert not r["ok"]
    assert "volume" in r["error"] and "weight" in r["error"]


def test_convert_unknown_unit():
    r = convert_units(1, "smidgen", "g")
    assert not r["ok"] and "Unknown unit" in r["error"]


def test_total_ingredient_sums_compatible_units():
    soup = RecipeRepository(FIXTURES).get("onion-soup")
    r = total_ingredient(soup, "butter")
    # 50 g + 2 tbsp: mass and volume can't be summed, so listed separately
    assert r["total"] == "50 g + 2 tbsp"
    assert [b["step"] for b in r["by_step"]] == [1, 3]


def test_total_ingredient_missing():
    soup = RecipeRepository(FIXTURES).get("onion-soup")
    assert not total_ingredient(soup, "garlic")["ok"]


def test_total_ingredient_whole_word_and_ambiguity():
    from sous.recipes import parse_cooklang

    r = parse_cooklang(
        "Melt @unsalted butter{2%tbsp} with @kosher salt{1/2%tsp}.\n\n"
        "Add @kosher salt{1/2%tsp}, @chicken thighs{2%lb} and @chicken broth{1/2%cup}.\n"
    )
    salt = total_ingredient(r, "salt")
    assert salt["ok"] and salt["total"] == "1 tsp"
    chicken = total_ingredient(r, "chicken")
    assert not chicken["ok"] and "chicken thighs" in chicken["error"]
    assert total_ingredient(r, "chicken broth")["total"] == "0.5 cup"
