from unittest.mock import Mock

from click.testing import CliRunner

from opensyndrome.cli import cli, is_ollama_available
import pytest
from ollama._types import ResponseError


class TestIsOllamaAvailable:
    @pytest.fixture
    def mock_ollama(self, mocker):
        _mock_ollama = mocker.patch("opensyndrome.cli.ollama")
        list_response = Mock(models=[Mock(model="mistral")])

        def make_mock(return_value=None, side_effect=None):
            if side_effect:
                _mock_ollama.list.side_effect = side_effect
            else:
                _mock_ollama.list.return_value = return_value or list_response
            return _mock_ollama

        return make_mock

    def test_is_ollama_available(self, mock_ollama):
        assert is_ollama_available() is True

    def test_show_error_when_the_model_is_not_available(self, mock_ollama):
        error_message = "model 'gemma3' not found (status code: 404)"
        mock_ollama(side_effect=ResponseError(error=error_message))
        assert is_ollama_available() is False

    def test_show_error_when_cannot_connect_to_ollama(self, mock_ollama):
        mock_ollama(side_effect=ConnectionError())
        assert is_ollama_available() is False


class TestConvertToJson:
    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def mock_convert(self, mocker):
        return mocker.patch(
            "opensyndrome.cli.generate_machine_readable_format",
            return_value={"name": "Pneumonia"},
        )

    @pytest.fixture
    def mock_ollama_available(self, mocker):
        mocker.patch("opensyndrome.cli.is_ollama_available", return_value=True)

    def test_convert_with_human_readable_text(
        self, runner, mock_convert, mock_ollama_available
    ):
        result = runner.invoke(cli, ["convert", "-hr", "Any person with pneumonia"])
        assert result.exit_code == 0
        mock_convert.assert_called_once_with(
            "Any person with pneumonia", "mistral", "American English"
        )

    def test_convert_with_human_readable_file(
        self, runner, mock_convert, mock_ollama_available, tmp_path
    ):
        definition_file = tmp_path / "definition.txt"
        definition_file.write_text("Any person with pneumonia")
        result = runner.invoke(cli, ["convert", "-hf", str(definition_file)])
        assert result.exit_code == 0
        mock_convert.assert_called_once_with(
            "Any person with pneumonia", "mistral", "American English"
        )

    def test_convert_with_hr_and_hf_raises_error(
        self, runner, mock_convert, mock_ollama_available, tmp_path
    ):
        definition_file = tmp_path / "definition.txt"
        definition_file.write_text("Any person with pneumonia")
        result = runner.invoke(
            cli,
            [
                "convert",
                "-hr",
                "Any person with pneumonia",
                "-hf",
                str(definition_file),
            ],
        )
        assert result.exit_code == 2
        assert "Cannot use -hr and -hf at the same time." in result.output

    def test_convert_with_hf_nonexistent_file(
        self, runner, mock_convert, mock_ollama_available
    ):
        result = runner.invoke(cli, ["convert", "-hf", "nonexistent.txt"])
        assert result.exit_code == 2
