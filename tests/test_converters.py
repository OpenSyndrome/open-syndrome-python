from pathlib import Path
from unittest.mock import Mock, MagicMock

import pytest

from opensyndrome.converters import (
    _add_first_level_required_fields,
    load_examples,
    _fill_automatic_fields,
    generate_machine_readable_format,
)
from opensyndrome.schema import OpenSyndromeCaseDefinitionSchema


class TestAddFirstLevelRequiredFields:
    def test_add_first_level_required_fields(self, mocker):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "address": {"type": "string"},
            },
            "required": ["name"],
        }
        mocker.patch("opensyndrome.converters.json.loads", return_value=schema)
        instance = {"address": "Karl-Marx-Str. 1, 10178 Berlin, Germany"}
        expected = {
            "address": "Karl-Marx-Str. 1, 10178 Berlin, Germany",
            "name": "",
        }

        updated_instance = _add_first_level_required_fields(schema, instance)

        assert updated_instance == expected


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


class TestFillAutomaticFields:
    def test_check_required_fields(self, mocker):
        schema = {
            "type": "object",
            "properties": {
                "a-nice-name": {"type": "string"},
                "address": {"type": "string"},
            },
            "required": ["a-nice-name"],
        }
        mocker.patch("opensyndrome.converters.json.loads", return_value=schema)
        human_readable_definition = "Fiber and rash"
        machine_readable_definition = {
            "title": "Sarampo",
        }
        expected_keys = [
            "a-nice-name",
            "human_readable_definition",
            "open_syndrome_version",
            "published_at",
            "published_by",
            "published_in",
            "references",
            "status",
            "title",
        ]

        definition_with_automatic_fields = _fill_automatic_fields(
            machine_readable_definition, human_readable_definition
        )

        assert sorted(list(definition_with_automatic_fields.keys())) == sorted(
            expected_keys
        )

    def test_include_human_readable_definition(self):
        human_readable_definition = """
        Todo paciente que, independente da idade e da situação vacinal, apresentar febre e exantema
        maculopapular, acompanhados de um ou mais dos seguintes sinais e sintomas: tosse e/ou corizae/ou conjuntivite;
        ou todo indivíduo suspeito com história de viagem ao exterior nos últimos 30 dias ou de contato,
        no mesmo período, com alguém que viajou ao exterior.
        """
        machine_readable_definition = {
            "title": "Sarampo",
        }

        definition_with_automatic_fields = _fill_automatic_fields(
            machine_readable_definition, human_readable_definition
        )

        assert (
            definition_with_automatic_fields["human_readable_definition"]
            == human_readable_definition
        )


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
            "opensyndrome.converters._fill_automatic_fields",
            side_effect=lambda d, _: d,
        )
        return mock_client

    def test_prompt_requires_name_on_every_criterion(self, mock_instructor_client):
        generate_machine_readable_format("A case of pneumonia", provider="ollama")

        content = mock_instructor_client.chat.completions.create.call_args.kwargs[
            "messages"
        ][0]["content"].lower()
        assert "every criterion" in content
        assert "name" in content

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
