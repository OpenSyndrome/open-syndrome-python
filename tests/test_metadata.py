import pytest

from opensyndrome.metadata import fill_automatic_fields


class TestFillAutomaticFields:
    @pytest.fixture
    def _stub_schema(self, mocker):
        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "address": {"type": "string"},
            },
            "required": ["title"],
        }
        mocker.patch("opensyndrome.metadata.json.loads", return_value=schema)
        return schema

    def test_stamps_published_at_in_iso_utc(self, _stub_schema):
        result = fill_automatic_fields({"title": "Pneumonia"}, "Any case of pneumonia")
        assert result["published_at"].endswith("Z")
        assert "T" in result["published_at"]

    def test_carries_human_readable_definition_through(self, _stub_schema):
        text = "Any patient with cough and fever for at least 3 days."
        result = fill_automatic_fields({"title": "ILI"}, text)
        assert result["human_readable_definition"] == text

    def test_does_not_clobber_preexisting_status(self, _stub_schema):
        result = fill_automatic_fields(
            {"title": "X", "status": "published"}, "anything"
        )
        assert result["status"] == "published"

    def test_fills_missing_required_top_level_fields(self, _stub_schema):
        result = fill_automatic_fields({}, "anything")
        assert "title" in result

    def test_published_at_is_utc_not_local_time(self, _stub_schema):
        from datetime import UTC, datetime, timedelta

        before = datetime.now(UTC) - timedelta(seconds=1)
        result = fill_automatic_fields({"title": "X"}, "anything")
        after = datetime.now(UTC) + timedelta(seconds=1)

        stamped = datetime.fromisoformat(result["published_at"].replace("Z", "+00:00"))
        assert before <= stamped <= after

    def test_default_references_is_empty_list_not_blank_url(self, _stub_schema):
        result = fill_automatic_fields({"title": "X"}, "anything")
        assert result["references"] == []

    def test_uses_schema_default_for_enum_required_fields(self, mocker):
        schema = {
            "type": "object",
            "properties": {
                "definition_type": {
                    "type": "string",
                    "enum": ["case_definition", "syndrome_definition"],
                    "default": "case_definition",
                },
            },
            "required": ["definition_type"],
        }
        mocker.patch("opensyndrome.metadata.json.loads", return_value=schema)

        result = fill_automatic_fields({}, "anything")

        assert result["definition_type"] == "case_definition"
