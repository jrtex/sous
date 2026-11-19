"""CLI smoke test: uv run python -m sous.ask <recipe-id> <step> "<question>" """

import sys

from sous import config, llm
from sous.recipes import RecipeRepository


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    recipe_id, step, question = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    recipe = RecipeRepository(config.RECIPES_DIR).get(recipe_id)
    print(llm.answer(recipe, step, [], question))


if __name__ == "__main__":
    main()
