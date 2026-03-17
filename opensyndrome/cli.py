import json
from functools import wraps
from pathlib import Path

from pygments import highlight, lexers, formatters
import jsonschema
import click
from instructor.core.exceptions import InstructorRetryException

from opensyndrome.converters import (
    generate_machine_readable_format,
    generate_human_readable_format,
)
from opensyndrome.ontology import enrich_definition
from opensyndrome.artifacts import get_schema_filepath, get_definition_dir
from opensyndrome.validators import validate_machine_readable_format
from opensyndrome.providers import (
    build_model_string,
    check_provider_available,
    DEFAULT_PROVIDER,
    SUPPORTED_PROVIDERS,
)


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


def _show_llm_error(exception: Exception, provider: str, model: str) -> None:
    click.echo(
        click.style(
            f"❌ Request to LLM failed for {provider} {model} after {exception.n_attempts} attempts:\n"
            f"Details: {exception.args[0].message}",
            fg="red",
        ),
        err=True,
    )


def check_provider(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        provider = kwargs.get("provider", DEFAULT_PROVIDER)
        model = kwargs.get("model", "mistral")
        available, message = check_provider_available(provider, model)
        if not available:
            click.echo(click.style(message, fg="red"), err=True)
            raise click.Abort()
        return func(*args, **kwargs)

    return wrapper


@cli.command("convert")
@click.option(
    "--validate", is_flag=True, help="Validate the JSON file against the schema."
)
@click.option(
    "--model",
    type=str,
    help="Model to use. Defaults per provider: ollama=mistral, openai=gpt-4o, anthropic=claude-3-haiku-20240307, mistral=mistral-large-latest, deepseek=deepseek-chat, gemini=gemini-1.5-flash.",
    default=None,
    envvar="OPENSYNDROME_MODEL",
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
    "--enrich-ontology / --no-enrich-ontology",
    default=False,
    help="Post-process output to populate ontology IDs via EBI OLS4.",
)
@click.option(
    "-hr",
    "--human-readable-definition",
    type=str,
    help="Human-readable definition. If not provided, an editor will open to input the definition.",
)
@click.option(
    "-hf",
    "--human-readable-definition-file",
    type=click.Path(exists=True),
    help="Path to a TXT file containing the human-readable definition.",
)
@click.option(
    "--provider",
    type=click.Choice(SUPPORTED_PROVIDERS),
    default=DEFAULT_PROVIDER,
    envvar="OPENSYNDROME_PROVIDER",
    help="LLM provider to use.",
)
@check_provider
def convert_to_json(
    validate,
    model,
    language,
    edit,
    enrich_ontology,
    human_readable_definition,
    human_readable_definition_file,
    provider,
):
    """
    Convert human-readable definition (TEXT) to the machine-readable format (JSON).

    If the --validate flag is passed, the JSON file will be validated against the schema.
    """
    if human_readable_definition and human_readable_definition_file:
        raise click.UsageError("Cannot use -hr and -hf at the same time.")
    if human_readable_definition_file:
        human_readable_definition = Path(human_readable_definition_file).read_text()
    if not human_readable_definition:
        human_readable_definition = click.edit(extension=".txt")
    resolved_model = build_model_string(provider, model)
    click.echo(click.style(f"Using {provider} / {resolved_model}", fg="cyan"), err=True)
    try:
        machine_readable_definition = generate_machine_readable_format(
            human_readable_definition, model, language, provider
        )
    except InstructorRetryException as exception:
        _show_llm_error(exception, provider, model)
        return

    if enrich_ontology:
        click.echo(click.style("Enriching ontology IDs...", fg="cyan"), err=True)

        def _progress(name, curie):
            click.echo(
                click.style(f"  {name} → {curie}"),
                err=True,
            )

        machine_readable_definition = enrich_definition(
            machine_readable_definition,
            verbose_callback=_progress,
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
    help="Model to use. Defaults per provider: ollama=mistral, openai=gpt-4o, anthropic=claude-3-haiku-20240307, mistral=mistral-large-latest, deepseek=deepseek-chat, gemini=gemini-1.5-flash.",
    default=None,
    envvar="OPENSYNDROME_MODEL",
)
@click.option(
    "--language",
    type=str,
    help="Language used to generate the human-readable definition.",
    default="American English",
)
@click.option(
    "--provider",
    type=click.Choice(SUPPORTED_PROVIDERS),
    default=DEFAULT_PROVIDER,
    envvar="OPENSYNDROME_PROVIDER",
    help="LLM provider to use.",
)
@check_provider
def convert_to_text(json_file, model, language, provider):
    """Convert a machine-readable format (JSON) to a human-readable format (TEXT)."""
    resolved_model = build_model_string(provider, model)
    click.echo(click.style(f"Using {provider} / {resolved_model}", fg="cyan"), err=True)
    machine_readable_definition = json.loads(Path(json_file).read_text())
    try:
        text = generate_human_readable_format(
            machine_readable_definition, model, language, provider
        )
    except InstructorRetryException as exception:
        _show_llm_error(exception, provider, model)
        return
    click.echo(click.style(text, fg="green"))


@cli.command("download", help="Download an entity from OSI.")
@click.argument("entity")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force download even if already exists.",
)
def download_entity(entity, force):
    match entity:
        case "schema":
            result = get_schema_filepath(force=force)
        case "definitions":
            result = get_definition_dir(force=force)
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
