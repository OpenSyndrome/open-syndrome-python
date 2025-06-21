import pytest

from osi.converters import _add_first_level_required_fields, load_examples


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
        expected_break_lines = 4
        expected_start_lines = 5

        examples = load_examples(examples_dir)

        assert examples.count("\n") == expected_break_lines
        assert examples.count("- ") == expected_start_lines

    @pytest.mark.parametrize("k", [1, 2, 3])
    def test_load_examples_with_k_random_samples(self, k):
        examples_dir = "tests/definitions/"

        examples = load_examples(examples_dir, k)

        assert examples.count("- ") == k
