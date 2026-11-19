from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sous import app as app_module
from sous.recipes import RecipeRepository

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app_module, "repo", RecipeRepository(FIXTURES))
    return TestClient(app_module.app)


def test_index_lists_recipes(client):
    r = client.get("/")
    assert r.status_code == 200 and "Test Onion Soup" in r.text


def test_cook_flow_and_ask(client, monkeypatch):
    seen = {}

    def fake_answer(recipe, step, history, question):
        seen.update(step=step, history=history, question=question)
        return "10 minutes, until soft."

    monkeypatch.setattr(app_module.llm, "answer", fake_answer)
    r = client.get("/cook/onion-soup", follow_redirects=False)
    assert r.status_code == 303
    sid_path = r.headers["location"]
    page = client.get(sid_path)
    assert page.status_code == 200 and '"seconds": 600.0' in page.text

    sid = sid_path.rsplit("/", 1)[1]
    r = client.post(f"/api/s/{sid}/ask", json={"step": 2, "question": "how long?"})
    assert r.json() == {"answer": "10 minutes, until soft."}
    assert seen["step"] == 2 and seen["history"] == []

    client.post(f"/api/s/{sid}/ask", json={"step": 2, "question": "and then?"})
    assert len(seen["history"]) == 2  # previous turn passed as context


def test_unknown_recipe_and_session(client):
    assert client.get("/cook/nope").status_code == 404
    assert client.post("/api/s/bogus/ask", json={"step": 1, "question": "hi"}).status_code == 404


def test_prompt_marks_current_step():
    from sous import llm

    recipe = RecipeRepository(FIXTURES).get("onion-soup")
    msgs = llm.build_messages(recipe, 2, [], "how long?")
    assert "4. Pour in beef stock" in msgs[0]["content"]
    assert "timers: 10 minutes" in msgs[0]["content"]
    assert msgs[-1]["content"].startswith("[I'm on step 2 of 5:")
    # system prompt must not depend on the step (stable cacheable prefix)
    assert llm.build_messages(recipe, 4, [], "x")[0] == msgs[0]
