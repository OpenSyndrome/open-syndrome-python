import json
from pathlib import Path

import jsonschema
import click


@click.command()
@click.argument("json_file", type=click.Path(exists=True))
@click.argument("schema_file", type=click.Path(exists=True), default="schema.json")
def validate_json(json_file, schema_file):
    """
    Validate a JSON file against a JSON Schema.

    JSON_FILE: Path to the JSON file to validate.
    SCHEMA_FILE: Path to the JSON Schema file.
    """
    json_data = json.loads(Path(json_file).read_text())
    schema_data = json.loads(Path(schema_file).read_text())

    try:
        jsonschema.validate(json_data, schema_data)
        click.echo(click.style("✅ Validation successful!", fg="green"))
    except json.JSONDecodeError as e:
        click.echo(click.style(f"❌ Invalid JSON: {e}", fg="red"), err=True)
    except jsonschema.exceptions.ValidationError as e:
        click.echo(click.style(f"❌ Validation error: {e}", fg="red"), err=True)
    except Exception as e:
        click.echo(click.style(f"❌ An unexpected error occurred: {e}", fg="red"), err=True)


def main():
    validate_json()


if __name__ == "__main__":
    main()
