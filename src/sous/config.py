import os
from pathlib import Path

try:  # python-dotenv ships with uvicorn[standard]
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env")
SKILL_DIR = Path(os.environ.get("SOUS_SKILL_DIR", PROJECT_ROOT / "skill"))
RECIPES_DIR = Path(os.environ.get("SOUS_RECIPES_DIR", PROJECT_ROOT / "recipes"))


def model() -> str:
    m = os.environ.get("SOUS_MODEL")
    if not m:
        raise RuntimeError("Set SOUS_MODEL (a LiteLLM model string, e.g. anthropic/claude-haiku-5-5). See .env.example.")
    return m


HISTORY_TURNS = int(os.environ.get("SOUS_HISTORY_TURNS", "10"))
MAX_TOOL_ROUNDS = 4
# Generous: reasoning models spend tokens before answering. Brevity is enforced by SKILL.md + evals.
MAX_TOKENS = int(os.environ.get("SOUS_MAX_TOKENS", "1024"))
