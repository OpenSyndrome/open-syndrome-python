# load .env file
ifneq (,$(wildcard .env))
    include .env
    export
endif

ollama_schema:
	@echo "Generate JSON schema compatible with Ollama..."
	@ollama run mistral "Convert this JSON schema to the simplified version supported by Ollama. Only return the JSON: $$(cat $(SCHEMA_FILE))" --format json > ollama_schema.json
	@echo "Done!"
