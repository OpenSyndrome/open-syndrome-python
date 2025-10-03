import pytest

from osi.converters import (
    _add_first_level_required_fields,
    load_examples,
    _fill_automatic_fields,
)


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
        mocker.patch("osi.converters.json.loads", return_value=schema)
        instance = {"address": "Karl-Marx-Str. 1, 10178 Berlin, Germany"}
        expected = {
            "address": "Karl-Marx-Str. 1, 10178 Berlin, Germany",
            "name": "",
        }

        updated_instance = _add_first_level_required_fields(instance)

        assert updated_instance == expected


class TestLoadExamples:
    def test_load_examples(self):
        examples_dir = "tests/definitions/"
        expected_number_of_definitions = 11

        examples = load_examples(examples_dir)

        assert examples.count('"inclusion_criteria"') == expected_number_of_definitions
        assert examples.count("- {") == expected_number_of_definitions

    @pytest.mark.parametrize("k", [1, 2, 4])
    def test_load_examples_with_k_random_samples(self, k):
        examples_dir = "tests/definitions/"

        examples = load_examples(examples_dir, k)

        assert examples.count("- {") == k


class TestFillAutomaticFields:
    def test_check_required_fields(self):
        human_readable_definition = "Fiber and rash"
        machine_readable_definition = {
            "title": "Sarampo",
        }
        expected_keys = [
            "category",
            "definition_type",
            "human_readable_definition",
            "inclusion_criteria",
            "language",
            "location",
            "open_syndrome_version",
            "organization",
            "published_at",
            "published_by",
            "published_in",
            "references",
            "scope",
            "status",
            "title",
            "version",
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
