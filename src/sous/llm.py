"""Prompt assembly and the provider-agnostic tool-calling loop (via LiteLLM)."""

from __future__ import annotations

import json
from functools import cache

from sous import config, tools
from sous.recipes import Recipe


@cache
def skill_prompt() -> str:
    return (config.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")


@cache
def tool_schemas() -> list[dict]:
    return json.loads((config.SKILL_DIR / "tools.json").read_text(encoding="utf-8"))


def render_recipe(recipe: Recipe) -> str:
    """Plain-text rendering of the parsed recipe for the system prompt.

    Kept independent of the current step so the system prompt is a stable,
    cacheable prefix for the whole cooking session.
    """
    lines = [f"RECIPE: {recipe.title}"]
    meta = {k: v for k, v in recipe.metadata.items() if k != "title"}
    if meta:
        lines.append("Info: " + "; ".join(f"{k}: {v}" for k, v in meta.items()))
    lines.append("")
    lines.append("INGREDIENTS (in order of use):")
    for s in recipe.steps:
        for i in s.ingredients:
            lines.append(f"- {i.describe()}  [step {s.number}]")
    if recipe.cookware:
        lines.append("")
        lines.append("COOKWARE: " + ", ".join(recipe.cookware))
    lines.append("")
    lines.append("STEPS:")
    section = None
    for s in recipe.steps:
        if s.section != section and s.section:
            lines.append(f"[{s.section}]")
        section = s.section
        lines.append(f"{s.number}. {s.text}")
        if s.ingredients:
            lines.append("   uses: " + "; ".join(i.describe() for i in s.ingredients))
        if s.timers:
            lines.append("   timers: " + "; ".join(
                f"{t.name + ' ' if t.name else ''}{t.amount}" for t in s.timers))
    return "\n".join(lines)


def build_messages(recipe: Recipe, step: int, history: list[dict], question: str) -> list[dict]:
    step = max(1, min(step, len(recipe.steps)))
    current = recipe.steps[step - 1].text if recipe.steps else ""
    system = f"{skill_prompt()}\n\n---\n\n{render_recipe(recipe)}"
    user = f"[I'm on step {step} of {len(recipe.steps)}: \"{current}\"]\n{question.strip()}"
    return [{"role": "system", "content": system}, *history, {"role": "user", "content": user}]


def _run_tool(recipe: Recipe, name: str, raw_args: str) -> dict:
    try:
        args = json.loads(raw_args or "{}")
        if name == "convert_units":
            return tools.convert_units(float(args["quantity"]), str(args["from_unit"]), str(args["to_unit"]))
        if name == "total_ingredient":
            return tools.total_ingredient(recipe, str(args["name"]))
        return {"ok": False, "error": f"Unknown tool {name}"}
    except Exception as e:  # report bad arguments back to the model instead of crashing
        return {"ok": False, "error": f"Bad tool call: {e}"}


def answer(recipe: Recipe, step: int, history: list[dict], question: str, model: str | None = None) -> str:
    """Answer one cook question. `history` is prior {role, content} user/assistant turns."""
    import litellm

    messages = build_messages(recipe, step, history, question)
    model = model or config.model()
    for _ in range(config.MAX_TOOL_ROUNDS + 1):
        resp = litellm.completion(
            model=model,
            messages=messages,
            tools=tool_schemas(),
            max_tokens=config.MAX_TOKENS,
            temperature=0.2,
            drop_params=True,
        )
        msg = resp.choices[0].message
        calls = getattr(msg, "tool_calls", None) or []
        if not calls:
            return (msg.content or "").strip()
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in calls
            ],
        })
        for c in calls:
            result = _run_tool(recipe, c.function.name, c.function.arguments)
            messages.append({"role": "tool", "tool_call_id": c.id, "content": json.dumps(result)})
    return "Sorry, I couldn't work that out. Check the recipe step."
