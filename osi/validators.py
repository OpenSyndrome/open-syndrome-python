import json
from pathlib import Path

import jsonschema
from dotenv import load_dotenv

from osi.filtering import get_schema_filepath

load_dotenv()


def validate_machine_readable_format(machine_readable_definition, schema_file=None):
    if not schema_file:
        schema_file = get_schema_filepath()
    if not isinstance(machine_readable_definition, dict):
        try:
            json_data = json.loads(Path(machine_readable_definition).read_text())
        except OSError:
            json_data = json.loads(machine_readable_definition)
    else:
        json_data = machine_readable_definition
    schema_data = json.loads(Path(schema_file).read_text())

    jsonschema.validate(json_data, schema_data)
