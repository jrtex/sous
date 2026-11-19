# Sous

A self-hosted kitchen assistant. Pick a recipe on your phone, follow it step by step, and ask short
questions ("how long do I stir this?", "how many onions?", "what's 250 ml in cups?"). An LLM answers
in a sentence or two, grounded in the recipe, with deterministic tools for every unit conversion.

## Run

```sh
cp .env.example .env        # set SOUS_MODEL and the provider API key
uv sync
uv run uvicorn sous.app:app --host 0.0.0.0 --port 8000
```

Open `http://<your-machine>:8000` on a phone or tablet on the same network.

CLI smoke test:

```sh
uv run python -m sous.ask <recipe-id> <step> "how long do I stir this?"
```

## Switching models

`SOUS_MODEL` is any [LiteLLM](https://docs.litellm.ai/docs/providers) model string, e.g.
`anthropic/claude-haiku-5-5`, `anthropic/claude-sonnet-5-5`, `openai/<model>`, `ollama/<model>`.
Set the matching API key env var. Tool calling must be supported by the model.

### Local model (llama.cpp or any OpenAI-compatible server)

```sh
SOUS_MODEL=openai/<model id from curl localhost:8080/v1/models>
OPENAI_API_BASE=http://localhost:8080/v1
OPENAI_API_KEY=local   # dummy unless llama-server was started with --api-key
```

llama-server must return structured tool calls (`--jinja` on builds where it isn't the default).

## Tests and evals

```sh
uv run pytest                                     # unit tests (no LLM)
SOUS_MODEL=... uv run pytest -m eval -s           # skill evals against a real model
SOUS_JUDGE_MODEL=... SOUS_MODEL=... uv run pytest -m eval -s   # + LLM-judge pass
```

Eval cases live in `tests/evals/cases.yaml`: each is (recipe, step, question) plus checks for
required facts, forbidden content, word count (≤30), and the "Not in the recipe" label.

## The skill

`skill/SKILL.md` is the system prompt (brevity, grounding, labelling and safety rules) and
`skill/tools.json` the provider-neutral tool schemas. Edit them, then re-run the evals.

## Writing recipes (Cooklang)

Recipes are `.cook` files in `recipes/`; the filename is the recipe id. Your recipes there are
gitignored (kept local); only `recipes/example-*.cook` is committed. Steps are paragraphs
separated by blank lines.

```
---
title: French Onion Soup
servings: 4
---
= Base =
Slice @onions{4%large} thinly. Melt @butter{50%g} in a #large pot{} over medium heat.

Stir for ~{10%minutes} until soft. Add @salt{1/2%tsp}.

= Finish =
Add @beef stock{1.5%l} and @thyme{some}(fresh). Simmer for ~simmer{30%minutes}.
```

| Syntax | Meaning |
|---|---|
| `@salt` | one-word ingredient, no amount |
| `@olive oil{2%tbsp}` | multi-word ingredient with quantity and unit |
| `@eggs{3}` | quantity, no unit |
| `@thyme{some}(fresh)` | text quantity, with a note |
| `#pan` / `#large pot{}` | cookware |
| `~{10%minutes}` / `~rest{1%hour}` | timer (tap-to-start in the UI) |
| `= Section =` | section heading |
| `-- comment` / `[- comment -]` | comments |
| `--- yaml ---` or `>> key: value` | metadata |

Unit conversion is same-dimension only (volume↔volume, weight↔weight, temperature, time).
Cups/pints/quarts are US customary.
