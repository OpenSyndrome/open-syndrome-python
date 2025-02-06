import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import requests
load_dotenv()


def load_examples(examples_dir):
    json_definitions = {}
    for raw_json in Path(examples_dir).iterdir():
        json_definitions[raw_json.stem] = json.loads(raw_json.read_text())

    examples = '\n'.join(
        f'- {json.dumps(_definition)}'
        for _definition in json_definitions.values()
        if _definition
    )
    return examples


EXAMPLES = load_examples(os.getenv('EXAMPLES_DIR'))
OLLAMA_BASE_URL = os.getenv('', "http://localhost:11434/")
OLLAMA_JSON_SCHEMA = json.load(open("ollama_schema.json"))
PROMPT = """  # TODO update prompt with few-shot examples
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
- Use English language
- JSON matching provided schema
- Clinical criteria reflecting ONLY input text
- No additional professional judgment or external information
"""


def fill_automatic_fields(machine_readable_definition):
    machine_readable_definition = json.loads(machine_readable_definition)
    machine_readable_definition['published_in'] = "https://opensyndrome.org"  # TODO assemble url based on repo
    machine_readable_definition['published_at'] = str(datetime.now().isoformat())
    machine_readable_definition['open_syndrome_version'] = 1  # TODO get this version from definition repo
    return machine_readable_definition


def generate_human_readable_format(human_readable_definition, model="mistral"):
    if not human_readable_definition:
        raise ValueError("Human-readable definition cannot be empty.")

    formatted_prompt = PROMPT.format(
        examples=EXAMPLES,
        human_readable_definition=human_readable_definition
    )
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": model,
            "prompt": formatted_prompt,
            "format": OLLAMA_JSON_SCHEMA,
            "stream": False,
            "options": {
                "temperature": 0
            }
        })
    response.raise_for_status()
    machine_readable_definition = response.json()['response']
    return fill_automatic_fields(machine_readable_definition)

