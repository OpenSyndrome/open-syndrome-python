import json
from pathlib import Path

import jsonschema


def validate_machine_readable_format(machine_readable_definition, schema_file="schema.json"):
    try:
        json_data = json.loads(Path(machine_readable_definition).read_text())
    except OSError:
        json_data = json.loads(machine_readable_definition)
    schema_data = json.loads(Path(schema_file).read_text())

    jsonschema.validate(json_data, schema_data)
