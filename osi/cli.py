import json
from pygments import highlight, lexers, formatters
import jsonschema
import click

from osi.converters import generate_human_readable_format
from osi.validators import validate_machine_readable_format


@click.group()
def cli():
    pass


@cli.command("validate")
@click.argument("json_file", type=click.Path(exists=True))
@click.argument("schema_file", type=click.Path(exists=True), default="schema.json")
def validate_json(json_file, schema_file):
    """
    Validate a JSON file against a JSON Schema.

    JSON_FILE: Path to the JSON file to validate.
    SCHEMA_FILE: Path to the JSON Schema file.
    """

    try:
        validate_machine_readable_format(json_file, schema_file)
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
