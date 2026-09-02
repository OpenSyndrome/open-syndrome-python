import json
import os
import warnings
from pathlib import Path

from dotenv import load_dotenv
import requests


OPEN_SYNDROME_VERSION = "v1"
OPEN_SYNDROME_DIR = Path.home() / ".open_syndrome" / OPEN_SYNDROME_VERSION
OPEN_SYNDROME_DIR.mkdir(parents=True, exist_ok=True)
SCHEMA_DIR = OPEN_SYNDROME_DIR / "schema.json"
DEFINITIONS_DIR = OPEN_SYNDROME_DIR / "definitions"
DEFINITIONS_DIR.mkdir(parents=True, exist_ok=True)
DEFINITIONS_DIR_ENV_VAR = "OPENSYNDROME_DEFINITIONS_DIR"
LOCAL_DEFINITIONS_ONLY_ENV_VAR = "OPENSYNDROME_LOCAL_DEFINITIONS_ONLY"
_TRUTHY_VALUES = {"1", "true", "yes", "on"}

load_dotenv()


def local_definitions_dir() -> Path | None:
    """Directory with the user's own definitions, from ``OPENSYNDROME_DEFINITIONS_DIR``.

    Returns ``None`` when the variable is unset or empty. The directory is owned
    by the user and never written to; it must already exist.
    """
    value = os.environ.get(DEFINITIONS_DIR_ENV_VAR, "").strip()
    if not value:
        return None
    directory = Path(value).expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(
            f"{DEFINITIONS_DIR_ENV_VAR} points to a directory that does not exist: "
            f"{directory}"
        )
    return directory


def local_definitions_only() -> bool:
    """Whether ``OPENSYNDROME_LOCAL_DEFINITIONS_ONLY`` asks to ignore the community definitions."""
    value = os.environ.get(LOCAL_DEFINITIONS_ONLY_ENV_VAR, "")
    return value.strip().lower() in _TRUTHY_VALUES


def download_schema():
    schema_response = requests.get(
        "https://raw.githubusercontent.com/OpenSyndrome/schema/refs/heads/main/schemas/"
        f"{OPEN_SYNDROME_VERSION}/schema.json"
    )
    SCHEMA_DIR.write_text(json.dumps(schema_response.json()))
    return SCHEMA_DIR


def download_definitions(
    url: str | None = None, current_path: Path | None = None
) -> None:
    """Download the community definitions from GitHub into ``DEFINITIONS_DIR``."""
    if url is None:
        url = "https://api.github.com/repos/OpenSyndrome/definitions/contents/definitions/v1?ref=main"
    if current_path is None:
        current_path = DEFINITIONS_DIR
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
            download_definitions(url=item["url"], current_path=local_dir)


def get_definition_dirs(
    force: bool = False,
    *,
    local_dir: str | Path | None = None,
    local_only: bool | None = None,
) -> list[Path]:
    """Return the directories holding definitions, in lookup order.

    - Neither environment variable set: ``[community]``, downloading the
      community definitions when the directory is empty or ``force`` is set.
    - ``OPENSYNDROME_DEFINITIONS_DIR`` set: ``[community, local]``.
    - ``OPENSYNDROME_LOCAL_DEFINITIONS_ONLY`` set: ``[local]``, never downloading.

    ``local_dir`` and ``local_only`` override the respective environment
    variables when given.
    """
    if local_dir is None:
        local_dir = local_definitions_dir()
    else:
        local_dir = Path(local_dir).expanduser().resolve()
    if local_only is None:
        local_only = local_definitions_only()

    if local_only:
        if local_dir is None:
            raise ValueError(
                f"{LOCAL_DEFINITIONS_ONLY_ENV_VAR} is set, so "
                f"{DEFINITIONS_DIR_ENV_VAR} must be set to a directory with your "
                "local definitions."
            )
        return [local_dir]

    community_dir = _community_definitions_dir(force)
    if local_dir is None:
        return [community_dir]
    return [community_dir, local_dir]


def _community_definitions_dir(force: bool) -> Path:
    """Return the community directory, downloading into it when empty or forced."""
    if force or not any(DEFINITIONS_DIR.iterdir()):
        download_definitions()
    return DEFINITIONS_DIR


def get_definition_dir(force: bool = False) -> Path:
    """Deprecated: return the community definitions directory only.

    Kept so existing callers keep working. It ignores the local definitions
    environment variables; use :func:`get_definition_dirs` to honour them.
    """
    warnings.warn(
        "get_definition_dir is deprecated and will be removed in a future version; "
        "use get_definition_dirs, which also returns your local definitions.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _community_definitions_dir(force)


def get_schema_filepath(force=False):
    if force or not SCHEMA_DIR.exists():
        download_schema()
    return SCHEMA_DIR
