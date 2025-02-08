import json
import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import requests

load_dotenv()
logger = logging.getLogger(__name__)


def load_examples(examples_dir):
    json_definitions = {}
    for raw_json in Path(examples_dir).iterdir():
        json_definitions[raw_json.stem] = json.loads(raw_json.read_text())

    examples = "\n".join(
        f"- {json.dumps(_definition)}"
        for _definition in json_definitions.values()
        if _definition
    )
    return examples


EXAMPLES = load_examples(os.getenv("EXAMPLES_DIR"))
OLLAMA_BASE_URL = os.getenv("", "http://localhost:11434/")
OLLAMA_JSON_SCHEMA = json.load(open("ollama_schema.json"))
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
- JSON matching provided schema
- Clinical criteria reflecting ONLY input text
- No additional professional judgment or external information
"""
PROMPT_TO_HUMAN_READABLE_FORMAT = """
You are an expert in creating standardized case definition JSONs for medical syndromes.
Generate a human-readable definition from the provided machine-readable JSON using only
the criteria and symptoms mentioned in the JSON.

Expected Output Format:
- Use {language} language
- Clear, concise, and easy to understand text
- No additional professional judgment or external information

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


def _fill_automatic_fields(machine_readable_definition: dict):
    machine_readable_definition["published_in"] = (
        "https://opensyndrome.org"  # TODO assemble url based on repo
    )
    machine_readable_definition["published_at"] = str(datetime.now().isoformat())
    machine_readable_definition["published_by"] = []
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


def generate_machine_readable_format(
    human_readable_definition, model="mistral", language="American English"
):
    if not human_readable_definition:
        raise ValueError("Human-readable definition cannot be empty.")

    formatted_prompt = PROMPT_TO_MACHINE_READABLE_FORMAT.format(
        examples=EXAMPLES,
        human_readable_definition=human_readable_definition,
        language=language,
    )
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": model,
            "prompt": formatted_prompt,
            "format": OLLAMA_JSON_SCHEMA,
            "stream": False,
            "options": {"temperature": 0},
        },
    )
    response.raise_for_status()
    machine_readable_definition = response.json()["response"]

    machine_readable_definition = json.loads(machine_readable_definition)
    if isinstance(machine_readable_definition, list):
        if len(machine_readable_definition) > 1:
            logger.warning("More than one definition generated...")
        machine_readable_definition = machine_readable_definition[0]
    return _fill_automatic_fields(machine_readable_definition)


def generate_human_readable_format(
    machine_readable_definition, model="mistral", language="American English"
):
    if not machine_readable_definition:
        raise ValueError("Machine-readable definition cannot be empty.")

    formatted_prompt = PROMPT_TO_HUMAN_READABLE_FORMAT.format(
        language=language, machine_readable_definition=machine_readable_definition
    )
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": model,
            "prompt": formatted_prompt,
            "stream": False,
            "options": {"temperature": 0},
        },
    )
    response.raise_for_status()
    human_readable_definition = response.json()["response"]
    return human_readable_definition
