import json
from datetime import UTC, datetime
from functools import cache
from typing import Any

from opensyndrome.artifacts import get_schema_filepath


@cache
def _load_schema() -> dict[str, Any]:
    return json.loads(get_schema_filepath().read_text())


_DEFAULT_VALUES: dict[str, Any] = {
    "string": "",
    "array": [],
    "object": {},
    "integer": 0,
}


def _add_first_level_required_fields(
    schema: dict[str, Any], definition: dict[str, Any]
) -> dict[str, Any]:
    """Add missing top-level required fields with placeholder values.

    Prefers the field's schema-declared ``default`` when present (important
    for enum fields where an empty string would fail validation); otherwise
    falls back to an empty value matching the field's JSON type.
    """
    missing_fields = set(schema["required"]) - set(definition.keys())
    for field in missing_fields:
        field_schema = schema["properties"][field]
        if "default" in field_schema:
            definition[field] = field_schema["default"]
        else:
            definition[field] = _DEFAULT_VALUES.get(field_schema.get("type"))
    return definition


def fill_automatic_fields(
    machine_readable_definition: dict[str, Any],
    human_readable_definition: str,
) -> dict[str, Any]:
    """Stamp standard metadata onto a machine-readable definition.

    Adds the human-readable text, publication URL placeholder, current UTC
    timestamp, default publisher list, draft status, schema version, and an
    empty references entry. Then fills any first-level required schema fields
    that are still missing. Pre-existing values are preserved.
    """
    machine_readable_definition.setdefault(
        "human_readable_definition", human_readable_definition
    )
    machine_readable_definition.setdefault(
        "published_in", "https://opensyndrome.org/definitions/<replace-url>"
    )
    machine_readable_definition.setdefault(
        "published_at", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    machine_readable_definition.setdefault("published_by", [])
    machine_readable_definition.setdefault("status", "draft")
    machine_readable_definition.setdefault("open_syndrome_version", "1.0.0")
    machine_readable_definition.setdefault("references", [])

    return _add_first_level_required_fields(_load_schema(), machine_readable_definition)
