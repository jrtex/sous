"""Skill evals against a real model. Run: SOUS_MODEL=... uv run pytest -m eval
Optional: SOUS_JUDGE_MODEL=... adds an LLM-judge pass (min score 3 on each axis)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from sous import config, llm
from sous.recipes import RecipeRepository

HERE = Path(__file__).parent
SPEC = yaml.safe_load((HERE / "cases.yaml").read_text())
DEFAULTS = SPEC.get("defaults", {})
LABEL = "not in the recipe"

pytestmark = pytest.mark.eval


def _repo(case) -> RecipeRepository:
    if case.get("recipes_dir") == "fixtures":
        return RecipeRepository(HERE.parent / "fixtures")
    return RecipeRepository(config.RECIPES_DIR)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().replace(" ", " "))


@pytest.fixture(scope="session")
def model():
    try:
        return config.model()
    except RuntimeError as e:
        pytest.skip(str(e))


@pytest.mark.parametrize("case", SPEC["cases"], ids=[c["id"] for c in SPEC["cases"]])
def test_case(case, model):
    try:
        recipe = _repo(case).get(case["recipe"])
    except KeyError:  # personal recipes are gitignored; skip their cases on a fresh clone
        pytest.skip(f"recipe {case['recipe']!r} not present")
    answer = llm.answer(recipe, case["step"], [], case["question"], model=model)
    a = _norm(answer)
    print(f"\n[{case['id']}] {answer}")

    words = len(answer.split())
    assert words <= case.get("max_words", DEFAULTS.get("max_words", 30)), f"too long ({words} words): {answer}"

    for item in case.get("must_contain", []):
        options = item if isinstance(item, list) else [item]
        assert any(_norm(o) in a for o in options), f"missing {options}: {answer}"
    for bad in case.get("must_not_contain", []):
        assert _norm(bad) not in a, f"should not contain {bad!r}: {answer}"

    if case.get("label") == "required":
        assert LABEL in a, f"off-recipe answer not labelled: {answer}"
    elif case.get("label") == "forbidden":
        assert LABEL not in a, f"recipe answer wrongly labelled: {answer}"

    from judge import judge, judge_model

    if judge_model():
        scores = judge(llm.render_recipe(recipe), case["step"], case["question"], answer)
        print(f"  judge: {scores}")
        for axis in ("concise", "helpful", "grounded"):
            assert scores[axis] >= 3, f"judge {axis}={scores[axis]}: {scores.get('note')}"
