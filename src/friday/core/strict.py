"""Structured-output schemas as Anthropic's API (and OpenAI's strict mode) take them (10 Nov: with an API key, every
"Ask the AI" was refused because its schema left an object open; Claude Code doesn't check, so it only showed then)."""

from typing import Any


def strict_problems(schema: Any, where: str = "schema") -> list[str]:
    """What Anthropic's structured output (and OpenAI's strict mode) would refuse in `schema`: every object must say
    `additionalProperties: false` (10 Nov: "Ask the AI" was refused for every API key). Empty when it's fine."""
    found: list[str] = []
    if isinstance(schema, dict):
        if schema.get("type") == "object" and schema.get("additionalProperties") is not False:
            found.append(f"{where}: an object without additionalProperties: false")
        for key, part in schema.items():
            if key == "properties" and isinstance(part, dict):
                for name, sub in part.items():
                    found += strict_problems(sub, f"{where}.{name}")
            elif key in ("items", "anyOf", "oneOf", "allOf", "$defs", "definitions"):
                # a list's items is one schema (or a list of them); $defs names its schemas
                named = key in ("$defs", "definitions") and isinstance(part, dict)
                parts = list(part.values()) if named else part if isinstance(part, list) else [part]
                for n, sub in enumerate(parts):
                    found += strict_problems(sub, f"{where}.{key}[{n}]")
    return found
