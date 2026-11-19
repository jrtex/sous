"""FastAPI app: recipe list, step-by-step cook view, and the ask endpoint."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from sous import config, llm
from sous.recipes import RecipeRepository
from sous.sessions import SessionStore

log = logging.getLogger("sous")
HERE = Path(__file__).parent

app = FastAPI(title="Sous")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
repo = RecipeRepository(config.RECIPES_DIR)
sessions = SessionStore()


def _recipe(recipe_id: str):
    try:
        return repo.get(recipe_id)
    except KeyError:
        raise HTTPException(404, "Recipe not found")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"recipes": repo.list()})


@app.get("/cook/{recipe_id}")
def start(recipe_id: str):
    _recipe(recipe_id)
    s = sessions.create(recipe_id)
    return RedirectResponse(f"/s/{s.id}", status_code=303)


@app.get("/s/{session_id}", response_class=HTMLResponse)
def cook(request: Request, session_id: str):
    s = sessions.get(session_id)
    if not s:  # server restarted; sessions are in memory
        return RedirectResponse("/", status_code=303)
    recipe = _recipe(s.recipe_id)
    steps = [
        {
            "number": st.number,
            "section": st.section,
            "text": st.text,
            "ingredients": [i.describe() for i in st.ingredients],
            "timers": [
                {"label": f"{t.name + ' ' if t.name else ''}{t.amount}", "seconds": t.seconds}
                for t in st.timers
                if t.seconds
            ],
        }
        for st in recipe.steps
    ]
    return templates.TemplateResponse(
        request, "cook.html",
        {"recipe": recipe, "steps": steps, "session_id": s.id, "history": list(s.history)},
    )


class AskIn(BaseModel):
    step: int = Field(ge=1)
    question: str = Field(min_length=1, max_length=500)


@app.post("/api/s/{session_id}/ask")
async def ask(session_id: str, body: AskIn):
    s = sessions.get(session_id)
    if not s:
        raise HTTPException(404, "Session expired. Reload the recipe.")
    recipe = _recipe(s.recipe_id)
    try:
        text = await run_in_threadpool(llm.answer, recipe, body.step, list(s.history), body.question)
    except Exception:
        log.exception("LLM call failed")
        raise HTTPException(502, "The assistant is unavailable right now.")
    s.add_turn(body.question, text)
    return {"answer": text}
