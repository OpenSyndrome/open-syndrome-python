from unittest.mock import Mock

from click.testing import CliRunner

from opensyndrome.cli import cli
import pytest


class TestCheckProviderAvailable:
    def test_ollama_available(self, mocker):
        mocker.patch(
            "opensyndrome.providers.ollama.list",
            return_value=Mock(models=[Mock(model="mistral")]),
        )

        from opensyndrome.providers import check_provider_available

        available, message = check_provider_available("ollama", "mistral")

        assert available is True
        assert message == ""

    def test_ollama_model_not_pulled(self, mocker):
        mocker.patch(
            "opensyndrome.providers.ollama.list",
            return_value=Mock(models=[Mock(model="llama3:latest")]),
        )

        from opensyndrome.providers import check_provider_available

        available, message = check_provider_available("ollama", "mistral")

        assert available is False
        assert "ollama pull mistral" in message

    def test_ollama_unavailable(self, mocker):
        mocker.patch(
            "opensyndrome.providers.ollama.list",
            side_effect=ConnectionError("Connection refused"),
        )

        from opensyndrome.providers import check_provider_available

        available, message = check_provider_available("ollama", "mistral")

        assert available is False
        assert "Ollama service is missing or unavailable" in message

    def test_cloud_provider_with_api_key(self, mocker):
        mocker.patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"})

        from opensyndrome.providers import check_provider_available

        available, message = check_provider_available("openai", "gpt-4o")

        assert available is True
        assert message == ""

    def test_cloud_provider_missing_api_key(self, mocker):
        mocker.patch.dict("os.environ", {}, clear=True)
        mocker.patch("os.environ.get", return_value=None)

        from opensyndrome.providers import check_provider_available

        available, message = check_provider_available("openai", "gpt-4o")

        assert available is False
        assert "OPENAI_API_KEY" in message


class TestConvertToJson:
    @pytest.fixture(autouse=True)
    def isolate_env(self, mocker):
        mocker.patch.dict(
            "os.environ", {"OPENSYNDROME_PROVIDER": "ollama"}, clear=False
        )

    @pytest.fixture
    def runner(self):
        return CliRunner(env={"OPENSYNDROME_PROVIDER": "ollama"})

    @pytest.fixture
    def mock_convert(self, mocker):
        return mocker.patch(
            "opensyndrome.cli.generate_machine_readable_format",
            return_value={"name": "Pneumonia"},
        )

    @pytest.fixture
    def mock_provider_available(self, mocker):
        mocker.patch(
            "opensyndrome.cli.check_provider_available", return_value=(True, "")
        )

    def test_convert_with_human_readable_text(
        self, runner, mock_convert, mock_provider_available
    ):
        result = runner.invoke(cli, ["convert", "-hr", "Any person with pneumonia"])
        assert result.exit_code == 0
        mock_convert.assert_called_once_with(
            "Any person with pneumonia", None, "American English", "ollama"
        )

    def test_convert_with_human_readable_file(
        self, runner, mock_convert, mock_provider_available, tmp_path
    ):
        definition_file = tmp_path / "definition.txt"
        definition_file.write_text("Any person with pneumonia")
        result = runner.invoke(cli, ["convert", "-hf", str(definition_file)])
        assert result.exit_code == 0
        mock_convert.assert_called_once_with(
            "Any person with pneumonia", None, "American English", "ollama"
        )

    def test_convert_with_hr_and_hf_raises_error(
        self, runner, mock_convert, mock_provider_available, tmp_path
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
        self, runner, mock_convert, mock_provider_available
    ):
        result = runner.invoke(cli, ["convert", "-hf", "nonexistent.txt"])
        assert result.exit_code == 2

    def test_convert_with_provider_option(
        self, runner, mock_convert, mock_provider_available
    ):
        result = runner.invoke(
            cli,
            [
                "convert",
                "-hr",
                "Any person with pneumonia",
                "--provider",
                "openai",
                "--model",
                "gpt-4o",
            ],
        )
        assert result.exit_code == 0
        mock_convert.assert_called_once_with(
            "Any person with pneumonia", "gpt-4o", "American English", "openai"
        )

    def test_convert_shows_error_when_provider_unavailable(
        self, runner, mock_convert, mocker
    ):
        mocker.patch(
            "opensyndrome.cli.check_provider_available",
            return_value=(False, "Ollama service is missing or unavailable."),
        )
        result = runner.invoke(cli, ["convert", "-hr", "Any person with pneumonia"])
        assert result.exit_code == 0
        assert "Ollama service is missing or unavailable." in result.output
        mock_convert.assert_not_called()
