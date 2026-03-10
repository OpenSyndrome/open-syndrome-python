# open-syndrome-python

[![PyPI - Version](https://img.shields.io/pypi/v/opensyndrome)](https://pypi.org/project/opensyndrome/) [![Test](https://github.com/OpenSyndrome/open-syndrome-python/actions/workflows/ci.yml/badge.svg)](https://github.com/OpenSyndrome/open-syndrome-python/actions/workflows/ci.yml)

## Installation

You can install it from PyPI or Docker. To use the conversion features,
you will need to have [Ollama](https://github.com/ollama/ollama) installed.

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

### Convert a human-readable syndrome definition to a machine-readable JSON

You need to have [Ollama](https://github.com/ollama/ollama) installed locally
to use this feature. Pull the models you want to use with `opensyndrome` before running the command.
We have tested llama3.2, mistral, and deepseek-r1 so far.

Don't go well with structured output: qwen2.5-coder

> If you do not pass `-hr` or `-hf`, an editor will open for you to enter the definition.

```bash
# see some examples from ECDC: https://www.ecdc.europa.eu/en/all-topics/eu-case-definitions

# pass the definition as inline text
opensyndrome convert -hr "Any person with pneumonia"

# pass the definition from a TXT file
opensyndrome convert -hf definition.txt

opensyndrome convert --model mistral

# to have the JSON translated to a specific language and edit it just after conversion
opensyndrome convert --language "Português do Brasil" --model mistral --edit

# include a validation step after conversion
opensyndrome convert --validate
```

### Convert a machine-readable JSON syndrome definition to a human-readable format

```bash
opensyndrome humanize <path-to-json-file>
opensyndrome humanize <path-to-json-file> --model mistral
opensyndrome humanize <path-to-json-file> --model mistral --language "Português do Brasil"
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
