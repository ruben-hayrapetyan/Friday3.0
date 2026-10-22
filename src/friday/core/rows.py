"""Items as database rows and back (DESIGN §7). Pure: the modules that own each table run the SQL."""

import json
from dataclasses import asdict
from typing import Any

from friday.core.items import ITEM_FIELDS, Item

JSON_FIELDS = ("tags", "estimate_detail")
BOOL_FIELDS = ("blocks_time", "detached")


def item_to_row(item: Item) -> dict[str, Any]:
    row = asdict(item)
    row["when_kind"] = row.pop("when")
    for name in JSON_FIELDS:
        row[name] = json.dumps(row[name]) if row[name] is not None else None
    for name in BOOL_FIELDS:
        row[name] = int(row[name])
    if row["tags"] is None:
        row["tags"] = "[]"
    return row


def item_from_row(row: dict[str, Any]) -> Item:
    values = {k: v for k, v in row.items() if k in ITEM_FIELDS or k == "when_kind"}
    values["when"] = values.pop("when_kind")
    for name in JSON_FIELDS:
        values[name] = json.loads(values[name]) if values.get(name) is not None else None
    values["tags"] = values["tags"] or []
    for name in BOOL_FIELDS:
        values[name] = bool(values[name])
    return Item(**values)
