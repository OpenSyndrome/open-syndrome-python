# load .env file
ifneq (,$(wildcard .env))
    include .env
    export
endif

SCHEMA_FILE := $(HOME)/.open_syndrome/v1/schema.json

ask_ollama_schema:
	@echo "Generate JSON schema compatible with Ollama..."
	@ollama run mistral "Convert this JSON schema to the simplified version supported by Ollama. Do not include description or examples. Do not create new fields. Only work with the JSON: $$(cat $(SCHEMA_FILE))" --format json > ollama_schema.json
	@echo "Done!"

ollama_schema:
	@datamodel-codegen --input-file-type jsonschema \
					   --output-model-type pydantic_v2.BaseModel \
					   --use-unique-items-as-set \
					   --use-default \
					   --input $(SCHEMA_FILE) \
					   --output opensyndrome/to_be_updated__schema.py
