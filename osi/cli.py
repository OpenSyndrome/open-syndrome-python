import json
from pathlib import Path

from pygments import highlight, lexers, formatters
import jsonschema
import click

from osi.converters import generate_machine_readable_format, generate_human_readable_format
from osi.validators import validate_machine_readable_format


@click.group()
def cli():
    pass


def validate_machine_readable_format_with_style(json_or_file, schema_file=None):
    try:
        validate_machine_readable_format(json_or_file, schema_file)
        click.echo(click.style("✅ Validation successful!", fg="green"))
    except json.JSONDecodeError as e:
        click.echo(click.style(f"❌ Invalid JSON: {e}", fg="red"), err=True)
    except jsonschema.exceptions.ValidationError as e:
        click.echo(click.style(f"❌ Validation error: {e}", fg="red"), err=True)
    except Exception as e:
        click.echo(
            click.style(f"❌ An unexpected error occurred: {e}", fg="red"), err=True
        )


@cli.command("validate")
@click.argument("json_file", type=click.Path(exists=True))
@click.argument("schema_file", type=click.Path(exists=True), default="schema.json")
def validate_json(json_file, schema_file):
    """
    Validate a JSON file against a JSON Schema.

    JSON_FILE: Path to the JSON file to validate.
    SCHEMA_FILE: Path to the JSON Schema file.
    """
    validate_machine_readable_format_with_style(json_file, schema_file)


def color_json(json_definition: dict):
    formatted_json = json.dumps(json_definition, indent=4)
    return highlight(formatted_json, lexers.JsonLexer(), formatters.TerminalFormatter())


@cli.command("convert")
@click.option(
    "--validate", is_flag=True, help="Validate the JSON file against the schema."
)
@click.option(
    "--model",
    type=str,
    help="Model used to generate the JSON file.",
    default="llama3.2",
)
def convert_to_json(validate, model):
    """
    Convert human-readable definition to the Open Syndrome format.

    If the --validate flag is passed, the JSON file will be validated against the schema.
    """
    human_readable_definition = click.edit()
    machine_readable_definition = generate_machine_readable_format(
        human_readable_definition, model
    )
    click.echo(color_json(machine_readable_definition))

    if validate:
        validate_machine_readable_format_with_style(machine_readable_definition)


@cli.command("humanize")
@click.argument("json_file", type=click.Path(exists=True))
@click.option(
    "--model",
    type=str,
    help="Model used to generate the JSON file.",
    default="llama3.2",
)
@click.option(
    "--language",
    type=str,
    help="Language used to generate the human-readable definition.",
    default="American English",
)
def convert_to_text(json_file, model, language):
    machine_readable_definition = json.loads(Path(json_file).read_text())
    text = generate_human_readable_format(machine_readable_definition, model, language)
    click.echo(click.style(text, fg="green"))


def main():
    cli()


if __name__ == "__main__":
    main()
