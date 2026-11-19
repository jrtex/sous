"""Minimal Cooklang parser and recipe repository.

Supports the parts of the Cooklang spec (https://cooklang.org/docs/spec/) we need:
  - YAML front matter (--- ... ---) and legacy `>> key: value` metadata
  - comments: `-- line` and `[- block -]`
  - sections: lines like `= Dough =`
  - ingredients: `@salt`, `@olive oil{2%tbsp}`, `@eggs{3}`, optional `(note)` suffix
  - cookware: `#pan`, `#large pot{}`
  - timers: `~{10%minutes}`, `~rest{1%hour}`
Steps are paragraphs separated by blank lines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import yaml

_NAME_STOP = r"\s@#~{}.,;:!?()\[\]"
_INGREDIENT = re.compile(
    r"@(?:(?P<long>[^@#~{}\n]+?)\{(?P<amt>[^}]*)\}|(?P<short>[^" + _NAME_STOP + r"]+))"
    r"(?:\((?P<note>[^)]*)\))?"
)
_COOKWARE = re.compile(
    r"#(?:(?P<long>[^@#~{}\n]+?)\{(?P<amt>[^}]*)\}|(?P<short>[^" + _NAME_STOP + r"]+))"
)
_TIMER = re.compile(r"~(?P<name>[^@#~{}\n]*?)\{(?P<amt>[^}]*)\}")
_BLOCK_COMMENT = re.compile(r"\[-.*?-\]", re.S)
_LINE_COMMENT = re.compile(r"--.*$", re.M)
_SECTION = re.compile(r"^=+\s*(.*?)\s*=*\s*$")
_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


@dataclass
class Amount:
    raw: str = ""  # quantity exactly as written, e.g. "1/2", "some"
    unit: str = ""

    @property
    def value(self) -> float | None:
        """Numeric quantity, or None for things like 'some', ranges, or empty."""
        return parse_number(self.raw)

    @property
    def range(self) -> tuple[float, float] | None:
        """(low, high) for a single number or a range like '6-8'; None otherwise."""
        return parse_range(self.raw)

    def __str__(self) -> str:
        return " ".join(p for p in (self.raw, self.unit) if p)


@dataclass
class Ingredient:
    name: str
    amount: Amount = field(default_factory=Amount)
    note: str = ""

    def describe(self) -> str:
        s = f"{self.name}: {self.amount}" if str(self.amount) else self.name
        return f"{s} ({self.note})" if self.note else s


@dataclass
class Timer:
    name: str
    amount: Amount

    @property
    def seconds(self) -> float | None:
        from sous.tools import to_seconds

        return to_seconds(self.amount)


@dataclass
class Step:
    number: int  # 1-based, across the whole recipe
    text: str  # human-readable text with markup removed
    section: str = ""
    ingredients: list[Ingredient] = field(default_factory=list)
    cookware: list[str] = field(default_factory=list)
    timers: list[Timer] = field(default_factory=list)


@dataclass
class Recipe:
    id: str
    title: str
    metadata: dict
    steps: list[Step]

    @property
    def ingredients(self) -> list[Ingredient]:
        return [i for s in self.steps for i in s.ingredients]

    @property
    def cookware(self) -> list[str]:
        seen: dict[str, None] = {}
        for s in self.steps:
            seen.update(dict.fromkeys(s.cookware))
        return list(seen)


def parse_number(raw: str) -> float | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        # "1 1/2" -> 1.5
        return float(sum(Fraction(p) for p in raw.split()))
    except (ValueError, ZeroDivisionError):
        return None


_RANGE_SEP = re.compile(r"\s*(?:-|–|—|\bto\b)\s*")


def parse_range(raw: str) -> tuple[float, float] | None:
    if (v := parse_number(raw)) is not None:
        return (v, v)
    parts = _RANGE_SEP.split(raw.strip())
    if len(parts) == 2:
        lo, hi = parse_number(parts[0]), parse_number(parts[1])
        if lo is not None and hi is not None and lo <= hi:
            return (lo, hi)
    return None


def _parse_amount(amt: str | None) -> Amount:
    if not amt:
        return Amount()
    qty, _, unit = amt.partition("%")
    return Amount(raw=qty.strip(), unit=unit.strip())


def _parse_step(number: int, raw: str, section: str) -> Step:
    step = Step(number=number, text="", section=section)

    def ing(m: re.Match) -> str:
        name = (m["long"] or m["short"]).strip()
        step.ingredients.append(
            Ingredient(name=name, amount=_parse_amount(m["amt"]), note=(m["note"] or "").strip())
        )
        return name

    def cw(m: re.Match) -> str:
        name = (m["long"] or m["short"]).strip()
        step.cookware.append(name)
        return name

    def tm(m: re.Match) -> str:
        t = Timer(name=m["name"].strip(), amount=_parse_amount(m["amt"]))
        step.timers.append(t)
        return str(t.amount)

    text = _TIMER.sub(tm, raw)
    text = _INGREDIENT.sub(ing, text)
    text = _COOKWARE.sub(cw, text)
    step.text = re.sub(r"\s+", " ", text).strip()
    return step


def parse_cooklang(source: str, recipe_id: str = "recipe") -> Recipe:
    metadata: dict = {}
    if m := _FRONT_MATTER.match(source):
        metadata = yaml.safe_load(m.group(1)) or {}
        source = source[m.end():]

    source = _BLOCK_COMMENT.sub("", source)
    steps: list[Step] = []
    section = ""
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            steps.append(_parse_step(len(steps) + 1, " ".join(paragraph), section))
            paragraph.clear()

    for line in source.splitlines():
        if line.lstrip().startswith(">>"):
            key, _, val = line.lstrip()[2:].partition(":")
            metadata[key.strip()] = val.strip()
            continue
        line = _LINE_COMMENT.sub("", line).strip()
        if not line:
            flush()
            continue
        if line.startswith("=") and (sm := _SECTION.match(line)):
            flush()
            section = sm.group(1)
            continue
        paragraph.append(line)
    flush()

    title = str(metadata.get("title") or recipe_id.replace("-", " ").replace("_", " ").title())
    return Recipe(id=recipe_id, title=title, metadata=metadata, steps=steps)


class RecipeRepository:
    """Loads *.cook files from a folder; re-parses a file when its mtime changes."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self._cache: dict[str, tuple[float, Recipe]] = {}

    def ids(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.cook"))

    def list(self) -> list[Recipe]:
        return [self.get(i) for i in self.ids()]

    def get(self, recipe_id: str) -> Recipe:
        if "/" in recipe_id or "\\" in recipe_id or recipe_id.startswith("."):
            raise KeyError(recipe_id)
        path = self.root / f"{recipe_id}.cook"
        if not path.is_file():
            raise KeyError(recipe_id)
        mtime = path.stat().st_mtime
        cached = self._cache.get(recipe_id)
        if cached and cached[0] == mtime:
            return cached[1]
        recipe = parse_cooklang(path.read_text(encoding="utf-8"), recipe_id)
        self._cache[recipe_id] = (mtime, recipe)
        return recipe
