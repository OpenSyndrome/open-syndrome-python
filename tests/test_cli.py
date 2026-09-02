from unittest.mock import Mock

from click.testing import CliRunner
from instructor.core.exceptions import InstructorRetryException, FailedAttempt
import litellm

from opensyndrome.cli import cli
import pytest


class TestCheckProviderAvailable:
    def test_ollama_available(self, mocker):
        mocker.patch(
            "opensyndrome.providers.ollama.Client",
            return_value=Mock(
                list=Mock(return_value=Mock(models=[Mock(model="mistral")]))
            ),
        )

        from opensyndrome.providers import check_provider_available

        available, message = check_provider_available("ollama", "mistral")

        assert available is True
        assert message == ""

    def test_ollama_model_not_pulled(self, mocker):
        mocker.patch(
            "opensyndrome.providers.ollama.Client",
            return_value=Mock(
                list=Mock(return_value=Mock(models=[Mock(model="llama3:latest")]))
            ),
        )

        from opensyndrome.providers import check_provider_available

        available, message = check_provider_available("ollama", "mistral")

        assert available is False
        assert "ollama pull mistral" in message

    def test_ollama_unavailable(self, mocker):
        mocker.patch(
            "opensyndrome.providers.ollama.Client",
            return_value=Mock(
                list=Mock(side_effect=ConnectionError("Connection refused"))
            ),
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
    def isolate_env(self, mocker, monkeypatch):
        mocker.patch.dict(
            "os.environ", {"OPENSYNDROME_PROVIDER": "ollama"}, clear=False
        )
        monkeypatch.delenv("OPENSYNDROME_MODEL", raising=False)

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
        assert result.exit_code == 1
        assert "Ollama service is missing or unavailable." in result.output
        mock_convert.assert_not_called()

    def test_convert_shows_friendly_error_on_auth_failure(
        self, runner, mock_provider_available, mocker
    ):
        auth_error = litellm.AuthenticationError(
            message="Unauthorized", llm_provider="mistral", model="mistral-large-latest"
        )
        retry_exc = InstructorRetryException(
            n_attempts=3,
            total_usage=0,
            failed_attempts=[
                FailedAttempt(attempt_number=1, exception=auth_error),
                FailedAttempt(attempt_number=2, exception=auth_error),
                FailedAttempt(attempt_number=3, exception=auth_error),
            ],
        )
        mocker.patch(
            "opensyndrome.cli.generate_machine_readable_format",
            side_effect=retry_exc,
        )
        result = runner.invoke(cli, ["convert", "-hr", "Any person with pneumonia"])
        assert result.exit_code == 1

    def test_convert_with_enrich_ontology_calls_enrich(
        self, runner, mock_convert, mock_provider_available, mocker
    ):
        mock_enrich = mocker.patch(
            "opensyndrome.cli.enrich_definition",
            return_value={"name": "Pneumonia"},
        )
        result = runner.invoke(
            cli, ["convert", "-hr", "Any person with pneumonia", "--enrich-ontology"]
        )
        assert result.exit_code == 0
        mock_enrich.assert_called_once()

    def test_convert_without_enrich_ontology_skips_enrich(
        self, runner, mock_convert, mock_provider_available, mocker
    ):
        mock_enrich = mocker.patch("opensyndrome.cli.enrich_definition")
        result = runner.invoke(cli, ["convert", "-hr", "Any person with pneumonia"])
        assert result.exit_code == 0
        mock_enrich.assert_not_called()

    def test_convert_shows_friendly_error_on_rate_limit(
        self, runner, mock_provider_available, mocker
    ):
        mocker.patch(
            "opensyndrome.cli.generate_machine_readable_format",
            side_effect=litellm.RateLimitError(
                message="Rate limit", llm_provider="openai", model="gpt-4o"
            ),
        )
        result = runner.invoke(
            cli,
            ["convert", "-hr", "Any person with pneumonia", "--provider", "openai"],
        )
        assert result.exit_code == 1


class TestEnrichJson:
    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def json_file(self, tmp_path):
        f = tmp_path / "definition.json"
        f.write_text('{"inclusion_criteria": [{"type": "symptom", "name": "Fever"}]}')
        return f

    def test_enrich_calls_enrich_definition(self, runner, json_file, mocker):
        mock_enrich = mocker.patch(
            "opensyndrome.cli.enrich_definition",
            return_value={"inclusion_criteria": []},
        )
        result = runner.invoke(cli, ["enrich", str(json_file)])
        assert result.exit_code == 0
        mock_enrich.assert_called_once()

    def test_enrich_passes_definition_from_file(self, runner, json_file, mocker):
        mock_enrich = mocker.patch(
            "opensyndrome.cli.enrich_definition",
            return_value={"inclusion_criteria": []},
        )
        runner.invoke(cli, ["enrich", str(json_file)])
        passed = mock_enrich.call_args.args[0]
        assert passed == {"inclusion_criteria": [{"type": "symptom", "name": "Fever"}]}

    def test_enrich_nonexistent_file_exits_with_error(self, runner):
        result = runner.invoke(cli, ["enrich", "nonexistent.json"])
        assert result.exit_code == 2

    def test_enrich_outputs_json(self, runner, json_file, mocker):
        mocker.patch(
            "opensyndrome.cli.enrich_definition",
            return_value={"inclusion_criteria": [], "@context": "http://example.com"},
        )
        result = runner.invoke(cli, ["enrich", str(json_file)])
        assert result.exit_code == 0
        assert "@context" in result.output

    def test_enrich_passes_mapper_to_enrich_definition(self, runner, json_file, mocker):
        mock_enrich = mocker.patch(
            "opensyndrome.cli.enrich_definition",
            return_value={"inclusion_criteria": []},
        )
        runner.invoke(cli, ["enrich", str(json_file), "--mapper", "text2term"])
        assert mock_enrich.call_args.kwargs["mapper"] == "text2term"

    def test_enrich_default_mapper_is_ols(self, runner, json_file, mocker):
        mock_enrich = mocker.patch(
            "opensyndrome.cli.enrich_definition",
            return_value={"inclusion_criteria": []},
        )
        runner.invoke(cli, ["enrich", str(json_file)])
        assert mock_enrich.call_args.kwargs["mapper"] == "ols"


class TestConvertToText:
    @pytest.fixture(autouse=True)
    def isolate_env(self, mocker, monkeypatch):
        mocker.patch.dict(
            "os.environ", {"OPENSYNDROME_PROVIDER": "ollama"}, clear=False
        )
        monkeypatch.delenv("OPENSYNDROME_MODEL", raising=False)

    @pytest.fixture
    def runner(self):
        return CliRunner(env={"OPENSYNDROME_PROVIDER": "ollama"})

    @pytest.fixture
    def mock_provider_available(self, mocker):
        mocker.patch(
            "opensyndrome.cli.check_provider_available", return_value=(True, "")
        )

    def test_humanize_shows_friendly_error_on_auth_failure(
        self, runner, mock_provider_available, mocker, tmp_path
    ):
        json_file = tmp_path / "definition.json"
        json_file.write_text('{"name": "Pneumonia"}')
        auth_error = litellm.AuthenticationError(
            message="Unauthorized", llm_provider="mistral", model="mistral-large-latest"
        )
        mocker.patch(
            "opensyndrome.cli.generate_human_readable_format",
            side_effect=auth_error,
        )
        result = runner.invoke(cli, ["humanize", str(json_file)])
        assert result.exit_code == 1


class TestDownloadDefinitions:
    @pytest.fixture
    def dirs(self, tmp_path):
        return [tmp_path / "community", tmp_path / "local"]

    @pytest.fixture
    def mock_get_dirs(self, mocker, dirs):
        return mocker.patch("opensyndrome.cli.get_definition_dirs", return_value=dirs)

    @pytest.mark.parametrize("force", [True, False])
    @pytest.mark.parametrize("local_only", [True, False])
    def test_definitions_prints_every_dir_and_warns_when_local_only(
        self, mock_get_dirs, dirs, force, local_only
    ):
        env = {"OPENSYNDROME_LOCAL_DEFINITIONS_ONLY": "1" if local_only else None}
        args = ["download", "definitions"]
        if force:
            args.append("--force")

        result = CliRunner(env=env).invoke(cli, args)

        assert result.exit_code == 0
        mock_get_dirs.assert_called_once_with(force=force)
        assert ("OPENSYNDROME_LOCAL_DEFINITIONS_ONLY" in result.output) is local_only
        for directory in dirs:
            assert str(directory) in result.output

    def test_definitions_reports_missing_local_dir_as_error(self, mocker):
        mocker.patch(
            "opensyndrome.cli.get_definition_dirs",
            side_effect=ValueError("OPENSYNDROME_DEFINITIONS_DIR must be set"),
        )

        result = CliRunner().invoke(cli, ["download", "definitions"])

        assert result.exit_code == 1
        assert "OPENSYNDROME_DEFINITIONS_DIR must be set" in result.output

    def test_schema_ignores_local_only(self, mocker, tmp_path):
        mock_get_schema = mocker.patch(
            "opensyndrome.cli.get_schema_filepath", return_value=tmp_path
        )
        env = {"OPENSYNDROME_LOCAL_DEFINITIONS_ONLY": "1"}

        result = CliRunner(env=env).invoke(cli, ["download", "schema"])

        assert result.exit_code == 0
        mock_get_schema.assert_called_once_with(force=False)
        assert "OPENSYNDROME_LOCAL_DEFINITIONS_ONLY" not in result.output
