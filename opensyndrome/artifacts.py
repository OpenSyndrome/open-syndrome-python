import json
from pathlib import Path
import requests


OPEN_SYNDROME_VERSION = "v1"
OPEN_SYNDROME_DIR = Path.home() / ".open_syndrome" / OPEN_SYNDROME_VERSION
OPEN_SYNDROME_DIR.mkdir(parents=True, exist_ok=True)
SCHEMA_DIR = OPEN_SYNDROME_DIR / "schema.json"
DEFINITIONS_DIR = OPEN_SYNDROME_DIR / "definitions"
DEFINITIONS_DIR.mkdir(parents=True, exist_ok=True)


def download_schema():
    schema_response = requests.get(
        "https://raw.githubusercontent.com/OpenSyndrome/schema/refs/heads/main/schemas/"
        f"{OPEN_SYNDROME_VERSION}/schema.json"
    )
    SCHEMA_DIR.write_text(json.dumps(schema_response.json()))
    return SCHEMA_DIR


def download_definitions(url=None, current_path=None):
    """Download definitions from GitHub repos."""
    if url is None:
        url = "https://api.github.com/repos/OpenSyndrome/definitions/contents/definitions/v1?ref=main"
    response = requests.get(url)
    response.raise_for_status()

    for item in response.json():
        if item["type"] == "file":
            response_file = requests.get(item["download_url"])
            definition_filepath = current_path / item["name"]
            definition_filepath.write_bytes(response_file.content)

        elif item["type"] == "dir":
            print(item["path"])
            local_dir = DEFINITIONS_DIR / Path(item["path"]).parts[-1]
            local_dir.mkdir(parents=True, exist_ok=True)
            download_definitions(item["url"], local_dir)


def get_definition_dir(force=False):
    if force or not any(DEFINITIONS_DIR.iterdir()):
        download_definitions()
    return DEFINITIONS_DIR


def get_schema_filepath(force=False):
    if force or not SCHEMA_DIR.exists():
        download_schema()
    return SCHEMA_DIR
