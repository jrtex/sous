from pathlib import Path

import pytest

from sous.recipes import RecipeRepository, parse_cooklang, parse_number

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def soup():
    return RecipeRepository(FIXTURES).get("onion-soup")


def test_metadata_and_title(soup):
    assert soup.title == "Test Onion Soup"
    assert soup.metadata["servings"] == 4


def test_steps_and_sections(soup):
    assert len(soup.steps) == 5
    assert [s.section for s in soup.steps] == ["Base"] * 3 + ["Finish"] * 2
    assert soup.steps[0].text == "Slice onions thinly. Melt butter in a large pot over medium heat."


def test_ingredients(soup):
    first = soup.steps[0].ingredients
    assert [(i.name, i.amount.raw, i.amount.unit) for i in first] == [
        ("onions", "4", "large"),
        ("butter", "50", "g"),
    ]
    stock, thyme = soup.steps[3].ingredients
    assert stock.name == "beef stock" and stock.amount.value == 1.5
    assert thyme.amount.raw == "some" and thyme.amount.value is None
    assert thyme.note == "fresh, leaves only"
    pepper = soup.steps[4].ingredients[0]
    assert pepper.name == "pepper" and str(pepper.amount) == ""


def test_cookware(soup):
    assert soup.cookware == ["large pot"]


def test_timers(soup):
    t = soup.steps[1].timers[0]
    assert t.seconds == 600
    named = soup.steps[2].timers[0]
    assert named.name == "caramelise" and named.seconds == 2400
    assert soup.steps[3].timers[0].seconds == 1800
    assert "10 minutes" in soup.steps[1].text


def test_comments_stripped(soup):
    assert all("fixture" not in s.text for s in soup.steps)


def test_legacy_metadata_and_block_comment():
    r = parse_cooklang(">> servings: 2\nBoil @water{1%l}. [- hidden -] Done.\n", "x")
    assert r.metadata == {"servings": "2"}
    assert r.steps[0].text == "Boil water. Done."
    assert r.title == "X"


@pytest.mark.parametrize("raw,val", [("1/2", 0.5), ("1 1/2", 1.5), ("2", 2.0), ("", None), ("few", None)])
def test_parse_number(raw, val):
    assert parse_number(raw) == val


def test_repository_rejects_traversal():
    repo = RecipeRepository(FIXTURES)
    with pytest.raises(KeyError):
        repo.get("../onion-soup")
    assert repo.ids() == ["onion-soup"]


@pytest.mark.parametrize("raw,rng", [("6-8", (6, 8)), ("6 to 8", (6, 8)), ("1/2", (0.5, 0.5)), ("8-6", None), ("some", None)])
def test_parse_range(raw, rng):
    from sous.recipes import parse_range

    assert parse_range(raw) == rng


def test_range_timer_uses_lower_bound():
    r = parse_cooklang("Sear ~sear{6-8%minutes} per side.\n")
    t = r.steps[0].timers[0]
    assert t.seconds == 360 and str(t.amount) == "6-8 minutes"
    assert r.steps[0].text == "Sear 6-8 minutes per side."


def test_repo_recipes_parse():
    """Every real recipe in recipes/ parses into steps with ingredients."""
    from sous import config

    repo = RecipeRepository(config.RECIPES_DIR)
    for rid in repo.ids():
        r = repo.get(rid)
        assert r.steps and r.ingredients, rid
