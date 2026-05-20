# open-syndrome-python

[![PyPI - Version](https://img.shields.io/pypi/v/opensyndrome)](https://pypi.org/project/opensyndrome/) [![Test](https://github.com/OpenSyndrome/open-syndrome-python/actions/workflows/ci.yml/badge.svg)](https://github.com/OpenSyndrome/open-syndrome-python/actions/workflows/ci.yml)

## Installation

You can install it from PyPI or Docker. By default, the conversion features use [Ollama](https://github.com/ollama/ollama) running locally.
Cloud providers (OpenAI, Anthropic, Mistral, DeepSeek, Gemini) are also supported and require only an API key.

From PyPi, install the package with `pip install opensyndrome`. Then run it with `opensyndrome --help`.

From Docker, you can run the following command to build the image, tagged `opensyndrome`:

```bash
docker build -t opensyndrome .
```

Run the container interactively, removing it when it exits

```bash
docker run --rm -it opensyndrome
```

To read a `.env` file, mount it:

```bash
docker run --rm -it \
  -v "$(pwd)/.env:/app/.env:ro" \
  opensyndrome
```

To name the container and keep it around:

```bash
docker run --name opensyndrome-cli -it opensyndrome
```

## Usage

First, download the schema and definitions in order to work with the CLI locally.

```bash
opensyndrome download schema
opensyndrome download definitions
```

The files will be placed in the folder `.open_syndrome` in `$HOME`.

### Providers and configuration

The provider and model can be set via environment variables so you don't have to pass them on every command:

```bash
OPENSYNDROME_PROVIDER=ollama   # ollama (default), openai, anthropic, mistral, deepseek, gemini
OPENSYNDROME_MODEL=mistral     # overrides the provider's default model
```

Copy `.env.example` to `.env` and fill in the relevant values:

| Provider | Required env var | Default model |
|----------|-----------------|---------------|
| `ollama` | — (runs locally) | `mistral` |
| `openai` | `OPENAI_API_KEY` | `gpt-4o` |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-3-haiku-20240307` |
| `mistral` | `MISTRAL_API_KEY` | `mistral-large-latest` |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| `gemini` | `GEMINI_API_KEY` | `gemini-1.5-flash` |

For Ollama, the model must be pulled before use: `ollama pull mistral`. You can also override the Ollama base URL with `OLLAMA_BASE_URL`
(default: `http://localhost:11434`).

Ollama models tested: `llama3.2`, `mistral`, `deepseek-r1`. Known to not work well with structured output: `qwen2.5-coder`.

### Convert a human-readable syndrome definition to a machine-readable JSON

> If you do not pass `-hr` or `-hf`, an editor will open for you to enter the definition.

```bash
# see some examples from ECDC: https://www.ecdc.europa.eu/en/all-topics/eu-case-definitions

# pass the definition as inline text
opensyndrome convert -hr "Any person with pneumonia"

# pass the definition from a TXT file
opensyndrome convert -hf definition.txt

# use a specific provider and model
opensyndrome convert -hr "Any person with pneumonia" --provider openai --model gpt-4o

# to have the JSON translated to a specific language and edit it just after conversion
opensyndrome convert --language "Português do Brasil" --edit

# include a validation step after conversion
opensyndrome convert --validate
```

### Enrich ontology IDs on a JSON definition

The `enrich` command populates `ontology_id` fields on criteria nodes and sets the `@context` to the OpenSyndrome JSON-LD context URL. It queries [EBI OLS4](https://www.ebi.ac.uk/ols4) by default, or [text2term](https://ccb-hms.github.io/ontology-mapper/) as an alternative mapper.

```bash
# enrich an existing JSON definition (uses OLS4 by default)
opensyndrome enrich definition.json

# use text2term instead (requires: pip install opensyndrome[text2term])
opensyndrome enrich definition.json --mapper text2term

# review and adjust the result in an editor before printing
opensyndrome enrich definition.json --edit

# enrich and validate in one step
opensyndrome enrich definition.json --validate
```

You can also enrich directly after conversion:

```bash
opensyndrome convert -hr "Any person with fever and rash" --enrich-ontology
opensyndrome convert -hr "Any person with fever and rash" --enrich-ontology --mapper text2term
```

### Convert a machine-readable JSON syndrome definition to a human-readable format

```bash
opensyndrome humanize <path-to-json-file>
opensyndrome humanize <path-to-json-file> --provider anthropic
opensyndrome humanize <path-to-json-file> --model mistral-large-latest --language "Português do Brasil"
```

### Validate a machine-readable JSON syndrome definition

```bash
opensyndrome validate <path-to-json-file>
```

## Development

To get started with development, you need to have [uv](https://docs.astral.sh/uv/) installed.

### Install dependencies

```bash
uv sync
```

To include the optional `text2term` mapper (and its `bioregistry` dependency) so the full test suite runs without skips:

```bash
uv sync --all-extras
```

### Generate Ollama-compatible JSON

> You only need to do this if you are a maintainer adding a new OSI schema or updating an existing one.

Since Ollama requires a specific, more simple, JSON format, we need to generate an Ollama-compatible schema.
To do this, we use `datamodel-code-generator` to generate a Pydantic schema. Run the following command to update it:

```bash
make ollama_schema
```

It will create a `schema.py` file in the root of the project. Be careful when editing this file manually.

## Citing & Authors

If you find this repository helpful, feel free to cite our publication: The Open Syndrome Definition

```
@misc{ferreira2025opensyndromedefinition,
      title={The Open Syndrome Definition},
      author={Ana Paula Gomes Ferreira and Aleksandar Anžel and Izabel Oliva Marcilio de Souza and Helen Hughes and Alex J Elliot and Jude Dzevela Kong and Madlen Schranz and Alexander Ullrich and Georges Hattab},
      year={2025},
      eprint={2509.25434},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2509.25434},
}
```
