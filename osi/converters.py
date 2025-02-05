import json
import os

import requests


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


def generate_human_readable_format(human_readable_definition, model="llama3.2"):
    if not human_readable_definition:
        raise ValueError("Human-readable definition cannot be empty.")

    formatted_prompt = PROMPT.format(
        examples="",
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
    return response.json()['response']
g