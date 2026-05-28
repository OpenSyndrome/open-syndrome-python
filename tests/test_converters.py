from pathlib import Path
from unittest.mock import Mock, MagicMock

import pytest

from opensyndrome.converters import (
    load_examples,
    generate_machine_readable_format,
)
from opensyndrome.schema import OpenSyndromeCaseDefinitionSchema


class TestLoadExamples:
    def test_load_examples(self):
        examples_dir = Path("tests/definitions/")
        expected_number_of_definitions = 11

        examples = load_examples(examples_dir)

        assert examples.count('"inclusion_criteria"') == expected_number_of_definitions
        assert examples.count("- {") == expected_number_of_definitions

    @pytest.mark.parametrize("k", range(1, 4))
    def test_load_examples_with_k_random_samples(self, k):
        examples_dir = Path("tests/definitions/")

        examples = load_examples(examples_dir, k)

        assert examples.count("- {") == k


class TestGenerateMachineReadableFormat:
    @pytest.fixture
    def mock_instructor_client(self, mocker):
        mock_instance = Mock()
        mock_instance.model_dump.return_value = {"title": "Pneumonia"}
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_instance
        mocker.patch(
            "opensyndrome.converters.get_instructor_client", return_value=mock_client
        )
        mocker.patch(
            "opensyndrome.converters.fill_automatic_fields",
            side_effect=lambda d, _: d,
        )
        return mock_client

    def test_uses_response_model(self, mock_instructor_client):
        generate_machine_readable_format("A case of pneumonia", provider="ollama")

        call_kwargs = mock_instructor_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_model"] is OpenSyndromeCaseDefinitionSchema

    def test_builds_ollama_model_string(self, mock_instructor_client):
        generate_machine_readable_format(
            "A case of pneumonia", model="mistral", provider="ollama"
        )

        call_kwargs = mock_instructor_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "ollama/mistral"

    def test_builds_openai_model_string(self, mock_instructor_client):
        generate_machine_readable_format(
            "A case of pneumonia", model="gpt-4o", provider="openai"
        )

        call_kwargs = mock_instructor_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o"

    def test_builds_mistral_model_string(self, mock_instructor_client):
        generate_machine_readable_format(
            "A case of pneumonia", model="mistral-large-latest", provider="mistral"
        )

        call_kwargs = mock_instructor_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "mistral/mistral-large-latest"

    def test_builds_deepseek_model_string(self, mock_instructor_client):
        generate_machine_readable_format(
            "A case of pneumonia", model="deepseek-chat", provider="deepseek"
        )

        call_kwargs = mock_instructor_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "deepseek/deepseek-chat"

    def test_builds_gemini_model_string(self, mock_instructor_client):
        generate_machine_readable_format(
            "A case of pneumonia", model="gemini-1.5-flash", provider="gemini"
        )

        call_kwargs = mock_instructor_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gemini/gemini-1.5-flash"

    def test_raises_on_empty_input(self):
        with pytest.raises(
            ValueError, match="Human-readable definition cannot be empty"
        ):
            generate_machine_readable_format("")
