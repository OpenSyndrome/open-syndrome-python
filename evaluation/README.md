# Evaluating prompts

This directory contains prompt evaluation tools using [promptfoo](https://promptfoo.dev/) to test and compare different prompts for
converting human-readable syndrome definitions to machine-readable JSON format.

## Prerequisites

You need to have the following installed:

- [promptfoo](https://promptfoo.dev/) - Prompt testing framework
- [Ollama](https://github.com/ollama/ollama) - To run local LLM models

Install promptfoo:

```bash
brew install promptfoo  # see instructions for other OS in their website
```

Pull the Ollama models you want to test:

```bash
ollama pull mistral
ollama pull llama3.2
```

## Setup

Set the path to your Ollama-compatible JSON schema in a `.env` file or run:

```bash
export SCHEMA_FILE=/path/to/your/schema.json
```

## Generate test dataset

The evaluation uses test cases from the Hugging Face dataset. Generate the CSV file with:

```bash
uv run python evaluation/hf_dataset_to_csv.py
```

This creates `evaluation/dataset_txt_json.csv` containing paired text and JSON definitions from the [opensyndrome/case-definitions](https://huggingface.co/datasets/opensyndrome/case-definitions) dataset.

## Run evaluation

From the evaluation directory, run:

```bash
promptfoo eval
```

To view the results in an interactive UI:

```bash
promptfoo view
```

## Configuration

The `promptfooconfig.yaml` file defines:

- **providers**: Ollama models to test (mistral, llama3.2, etc.)
- **prompts**: Different prompt versions in `prompts/` directory
- **tests**: Test cases from `dataset_txt_json.csv`
- **assertions**: Validation checks including JSON validation and LLM-based logic evaluation
