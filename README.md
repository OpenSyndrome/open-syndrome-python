# open-syndrome-python

## Usage

### Convert a human-readable syndrome definition to a machine-readable JSON

You need to have [Ollama](https://github.com/ollama/ollama) installed locally
to use this feature. Pull the models you want to use with `osi` before running the command.
We have tested llama3.2, mistral, and deepseek-r1 so far.

Don't go well with structured output: qwen2.5-coder

```bash
osi convert
osi convert --model mistral

# to have the JSON translated to a specific language and edit it just after conversion
osi convert --language "Português do Brasil" --model mistral --edit

# include a validation step after conversion
osi convert --validate
```

### Convert a machine-readable JSON syndrome definition to a human-readable format

```bash
osi humanize <path-to-json-file>
osi humanize <path-to-json-file> --model mistral
osi humanize <path-to-json-file> --model mistral --language "Português do Brasil"
```

### Validate a machine-readable JSON syndrome definition

```bash
osi validate
```

## Development

To get started with development, you need to have [Poetry](https://python-poetry.org/) installed.

### Install dependencies

```bash
poetry install
```

### Generate Ollama-compatible JSON

> You only need to do this if you are a maintainer adding a new OSI schema or updating an existing one.

Since Ollama requires a specific, more simple, JSON format, we need to generate an Ollama-compatible schema.
To do this, we use `datamodel-code-generator` to generate a Pydantic schema. Run the following command to update it:

```bash
make ollama_schema
```

It will create a `schema.py` file in the root of the project. Be careful when editing this file manually.
