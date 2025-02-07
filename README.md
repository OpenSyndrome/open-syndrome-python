# open-syndrome-python

## Usage

### Convert a human-readable syndrome definition to a machine-readable JSON

You need to have [Ollama](https://github.com/ollama/ollama) installed locally
to use this feature. Pull the models you want to use with `osi` before running the command.
We have tested llama3.2, mistral, and deepseek-r1 so far.

```bash
osi convert
osi convert --model mistral

# or include a validation step after conversion
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
