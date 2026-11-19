"""Optional LLM-as-judge for tone/helpfulness. Enabled when SOUS_JUDGE_MODEL is set."""

from __future__ import annotations

import json
import os

RUBRIC = """You grade replies from a kitchen assistant to a cook mid-recipe.
Score 1-5 on each: concise (no filler, answer first), helpful (actually answers what a cook needs),
grounded (doesn't invent recipe facts). Reply ONLY with JSON: {"concise": n, "helpful": n, "grounded": n, "note": "..."}"""


def judge_model() -> str | None:
    return os.environ.get("SOUS_JUDGE_MODEL")


def judge(recipe_text: str, step: int, question: str, answer: str) -> dict:
    import litellm

    resp = litellm.completion(
        model=judge_model(),
        messages=[
            {"role": "system", "content": RUBRIC},
            {"role": "user", "content": f"{recipe_text}\n\nCook is on step {step}.\nQuestion: {question}\nReply: {answer}"},
        ],
        max_tokens=200,
        temperature=0,
        drop_params=True,
    )
    text = resp.choices[0].message.content or ""
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])
