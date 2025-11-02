import json
from functools import wraps
from pathlib import Path

from pygments import highlight, lexers, formatters
import jsonschema
import click
import ollama
from ollama._types import ResponseError

from opensyndrome.converters import (
    generate_machine_readable_format,
    generate_human_readable_format,
)
from opensyndrome.filtering import get_schema_filepath, get_definition_dir
from opensyndrome.validators import validate_machine_readable_format


@click.group()
def cli():
    pass


def validate_machine_readable_format_with_style(json_or_file, schema_file=None):
    try:
        validate_machine_readable_format(json_or_file, schema_file)
        click.echo(click.style("✅ Validation successful!", fg="green"))
    except (json.JSONDecodeError, json.decoder.JSONDecodeError) as e:
        click.echo(click.style(f"❌ Invalid JSON: {e}", fg="red"), err=True)
    except jsonschema.exceptions.ValidationError as e:
        click.echo(click.style(f"❌ Validation error: {e}", fg="red"), err=True)
    except Exception as e:
        click.echo(
            click.style(f"❌ An unexpected error occurred: {e}", fg="red"), err=True
        )


@cli.command("validate")
@click.argument("json_file", type=click.Path(exists=True))
@click.option("--schema-file", type=click.Path(exists=True))
def validate_json(json_file, schema_file):
    """
    Validate a JSON file against a JSON Schema.

    JSON_FILE: Path to the JSON file to validate.
    SCHEMA_FILE: Path to the JSON Schema file. If not passed, it will use
    the downloaded schema from GitHub repo.
    """
    validate_machine_readable_format_with_style(json_file, schema_file)


def color_json(json_definition: dict):
    formatted_json = json.dumps(json_definition, indent=4)
    return highlight(formatted_json, lexers.JsonLexer(), formatters.TerminalFormatter())


def is_ollama_available():
    try:
        ollama.list()
        return True
    except (ConnectionError, ResponseError):
        return False


def check_ollama(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not is_ollama_available():
            click.echo(
                click.style("Ollama service is missing or unavailable.", fg="red"),
                err=True,
            )
            return
        else:
            return func(*args, **kwargs)

    return wrapper


@cli.command("convert")
@click.option(
    "--validate", is_flag=True, help="Validate the JSON file against the schema."
)
@click.option(
    "--model",
    type=str,
    help="Model used to generate the JSON file.",
    default="mistral",
)
@click.option(
    "--language",
    type=str,
    help="Language used to generate the machine-readable definition.",
    default="American English",
)
@click.option(
    "--edit",
    is_flag=True,
    help="Open editor after generation.",
)
@click.option(
    "-hr",
    "--human-readable-definition",
    type=str,
    help="Human-readable definition. If not provided, an editor will open to input the definition.",
)
@check_ollama
def convert_to_json(validate, model, language, edit, human_readable_definition):
    """
    Convert human-readable definition (TEXT) to the machine-readable format (JSON).

    If the --validate flag is passed, the JSON file will be validated against the schema.
    """
    if not human_readable_definition:
        human_readable_definition = click.edit(extension=".json")
    machine_readable_definition = generate_machine_readable_format(
        human_readable_definition, model, language
    )

    if edit:
        machine_readable_definition_edited = click.edit(
            text=json.dumps(machine_readable_definition, indent=4), extension=".json"
        )
        if machine_readable_definition_edited:
            machine_readable_definition = json.loads(machine_readable_definition_edited)

    click.echo(color_json(machine_readable_definition))

    if validate:
        validate_machine_readable_format_with_style(machine_readable_definition)


@cli.command("humanize")
@click.argument("json_file", type=click.Path(exists=True))
@click.option(
    "--model",
    type=str,
    help="Model used to generate the JSON file.",
    default="mistral",
)
@click.option(
    "--language",
    type=str,
    help="Language used to generate the human-readable definition.",
    default="American English",
)
@check_ollama
def convert_to_text(json_file, model, language):
    """Convert a machine-readable format (JSON) to a human-readable format (TEXT)."""
    machine_readable_definition = json.loads(Path(json_file).read_text())
    text = generate_human_readable_format(machine_readable_definition, model, language)
    click.echo(click.style(text, fg="green"))


@cli.command("download", help="Download an entity from OSI.")
@click.argument("entity")
def download_entity(entity):
    match entity:
        case "schema":
            result = get_schema_filepath()
        case "definitions":
            result = get_definition_dir()
        case _:
            result = None

    if not result:
        click.echo(
            click.style(
                f"Invalid entity: {entity}. Expected: `schema` or `definitions`.",
                fg="red",
            )
        )
    else:
        click.echo(click.style(f"{entity} available at: {result}", fg="green"))


def main():
    cli()


if __name__ == "__main__":
    main()
