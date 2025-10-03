import json
import logging
import os
from datetime import datetime
from pathlib import Path
import random

from dotenv import load_dotenv
from ollama import chat

from osi.schema import OpenSyndromeCaseDefinitionSchema

load_dotenv()
logger = logging.getLogger(__name__)


def load_examples(examples_dir, random_k=None):
    json_definitions = {}
    for raw_json in Path(examples_dir).glob("**/*"):
        if not raw_json.name.endswith(".json"):
            continue
        if raw_json.read_text() != "":
            content = json.loads(raw_json.read_text())
            if content:
                json_definitions[raw_json.stem] = content

    definitions = list(json_definitions.values())
    if random_k:
        definitions = random.sample(definitions, random_k)
    examples = "\n".join(
        f"- {json.dumps(_definition)}" for _definition in definitions if _definition
    )
    return examples


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
PROMPT_TO_MACHINE_READABLE_FORMAT = """
You are an expert in creating standardized case definition JSONs for medical syndromes.
Generate a JSON that strictly follows this JSON schema, using the provided example documents as reference.

Strict Rules:
- ONLY use symptoms explicitly mentioned in the input text
- ONLY use criteria explicitly mentioned in the schema
- Generate JSON matching the provided schema exactly
- Do not add any information not in the source text
- Use logical operators to capture text's precise meaning
- If text is ambiguous, minimize assumptions

Example documents to reference:
{examples}

Input: {human_readable_definition}

Expected Output Format:
- Use {language} language
- JSON matching provided schema only
- Criteria reflecting ONLY input text
- No additional professional judgment or external information
"""
PROMPT_TO_HUMAN_READABLE_FORMAT = """
You are an public health expert in creating standardized case definition.
Generate a human-readable definition from the provided JSON using only
the information provided there.

Expected output format:
- Text in narrative form
- Clear, concise, and easy to understand text
- No additional professional judgment or external information
- Write in {language}

{machine_readable_definition}
"""


def _add_first_level_required_fields(definition: dict):
    """Add mandatory fields and empty values as placeholders."""
    default_values = {
        "string": "",
        "array": [],
        "object": {},
        "integer": 0,
    }
    schema = json.loads(Path(os.getenv("SCHEMA_FILE")).read_text())
    missing_fields = set(schema["required"]) - set(definition.keys())
    for field in missing_fields:
        definition[field] = default_values.get(schema["properties"][field]["type"])
    return definition


def _fill_automatic_fields(
    machine_readable_definition: dict, human_readable_definition: str
):
    machine_readable_definition["human_readable_definition"] = human_readable_definition
    machine_readable_definition["published_in"] = (
        "https://opensyndrome.org/definitions/<replace-url>"
    )
    machine_readable_definition["published_at"] = str(
        datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    machine_readable_definition["published_by"] = []
    machine_readable_definition["status"] = "draft"
    machine_readable_definition["open_syndrome_version"] = (
        "1.0.0"  # TODO get this version from definition repo
    )
    machine_readable_definition["references"] = [
        {"citation": "", "url": ""}
    ]  # to be filled by the user
    machine_readable_definition = _add_first_level_required_fields(
        machine_readable_definition
    )
    return machine_readable_definition


def _drop_regex_pattern(node: dict):
    """Recursively drop 'pattern' keys from the schema since it is not supported.

    Issue: https://github.com/ollama/ollama-python/issues/541"""
    original_node = node.copy()
    dropped = node.pop("pattern", None)
    if dropped is not None:
        logger.warning(f"Dropped 'pattern' from {original_node}")
    for value in node.values():
        if isinstance(value, dict):
            _drop_regex_pattern(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _drop_regex_pattern(item)


def generate_machine_readable_format(
    human_readable_definition, model="mistral", language="American English"
):
    if not human_readable_definition:
        raise ValueError("Human-readable definition cannot be empty.")

    examples = load_examples(os.getenv("EXAMPLES_DIR"), 3)
    formatted_prompt = PROMPT_TO_MACHINE_READABLE_FORMAT.format(
        examples=examples,
        human_readable_definition=human_readable_definition,
        language=language,
    )

    json_schema = OpenSyndromeCaseDefinitionSchema.model_json_schema()
    _drop_regex_pattern(json_schema)
    response = chat(
        messages=[{"role": "user", "content": formatted_prompt}],
        model=model,
        format=json_schema,
        options={"temperature": 0},
        stream=False,
    )

    machine_readable_definition = json.loads(response.message.content)
    if isinstance(machine_readable_definition, list):
        if len(machine_readable_definition) > 1:
            logger.warning("More than one definition generated...")
        machine_readable_definition = machine_readable_definition[0]

    return _fill_automatic_fields(
        machine_readable_definition, human_readable_definition
    )


def _exclude_metadata_fields(definition: dict):
    """Exclude metadata fields from the definition."""
    definition_fields = [
        "inclusion_criteria",
        "exclusion_criteria",
        "target_public_health_threats",
    ]
    return {key: value for key, value in definition.items() if key in definition_fields}


def generate_human_readable_format(
    machine_readable_definition, model="mistral", language="American English"
):
    if not machine_readable_definition:
        raise ValueError("Machine-readable definition cannot be empty.")

    formatted_prompt = PROMPT_TO_HUMAN_READABLE_FORMAT.format(
        language=language,
        machine_readable_definition=_exclude_metadata_fields(
            machine_readable_definition
        ),
    )
    response = chat(
        messages=[{"role": "user", "content": formatted_prompt}],
        model=model,
        options={"temperature": 0},
        stream=False,
    )
    human_readable_definition = response.message.content
    return human_readable_definition
