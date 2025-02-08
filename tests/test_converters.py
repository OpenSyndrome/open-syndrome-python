from osi.converters import _add_first_level_required_fields


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
