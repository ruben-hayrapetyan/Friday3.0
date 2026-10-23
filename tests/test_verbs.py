"""The CLI's command list and the web app's OpenAPI copy match the registry and the server's routes."""

from friday.api.verbs import VERBS
from scripts.make_verbs import OPENAPI, openapi, verbs

REGENERATE = "regenerate: PYTHONPATH=src:. uv run python -m scripts.make_verbs && pnpm --dir web gen:api"


def test_the_verb_list_is_up_to_date() -> None:
    assert verbs() == VERBS, REGENERATE


def test_the_web_openapi_copy_is_up_to_date() -> None:
    assert OPENAPI.read_text() == openapi(), REGENERATE
