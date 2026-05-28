from unittest.mock import Mock

from click.testing import CliRunner
from instructor.core.exceptions import InstructorRetryException, FailedAttempt
import litellm

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


class TestConvertSql:
    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def mapping_file(self, tmp_path):
        path = tmp_path / "mapping.yaml"
        path.write_text(
            "profiles:\n"
            "  - name: test\n"
            "    columns:\n"
            "      icd_code:\n"
            "        concept: diagnosis\n"
            "        system: ICD-10\n"
        )
        return path

    def test_inline_sql_prints_json(self, runner, mapping_file):
        result = runner.invoke(
            cli,
            [
                "convert-sql",
                "-s",
                "icd_code = 'F10.0'",
                "--mapping",
                str(mapping_file),
            ],
        )
        assert result.exit_code == 0, result.output
        assert '"code": "F10.0"' in result.output
        assert '"system": "ICD-10"' in result.output

    def test_sql_file_is_read(self, runner, mapping_file, tmp_path):
        sql_path = tmp_path / "query.sql"
        sql_path.write_text("icd_code = 'A90'")
        result = runner.invoke(
            cli,
            [
                "convert-sql",
                "-sf",
                str(sql_path),
                "--mapping",
                str(mapping_file),
            ],
        )
        assert result.exit_code == 0, result.output
        assert '"code": "A90"' in result.output

    def test_mutual_exclusion_of_sql_and_sql_file(self, runner, mapping_file, tmp_path):
        sql_path = tmp_path / "query.sql"
        sql_path.write_text("icd_code = 'A90'")
        result = runner.invoke(
            cli,
            [
                "convert-sql",
                "-s",
                "icd_code = 'A90'",
                "-sf",
                str(sql_path),
                "--mapping",
                str(mapping_file),
            ],
        )
        assert result.exit_code == 2
        assert "Cannot use --sql and --sql-file at the same time" in result.output

    def test_missing_mapping_file_errors(self, runner):
        result = runner.invoke(
            cli,
            ["convert-sql", "-s", "icd_code = 'A'", "--mapping", "nonexistent.yaml"],
        )
        assert result.exit_code == 2

    def test_mapping_error_is_shown(self, runner, mapping_file):
        result = runner.invoke(
            cli,
            [
                "convert-sql",
                "-s",
                "unknown_col = 'X'",
                "--mapping",
                str(mapping_file),
            ],
        )
        assert result.exit_code == 1
        assert "unknown_col" in result.output

    def test_profile_flag_selects_profile(self, runner, tmp_path):
        mapping = tmp_path / "mapping.yaml"
        mapping.write_text(
            "profiles:\n"
            "  - name: a\n"
            "    columns:\n"
            "      col_a:\n"
            "        concept: diagnosis\n"
            "        system: ICD-10\n"
            "  - name: b\n"
            "    columns:\n"
            "      col_b:\n"
            "        concept: diagnosis\n"
            "        system: ICD-10\n"
        )
        result = runner.invoke(
            cli,
            [
                "convert-sql",
                "-s",
                "col_b = 'X'",
                "--mapping",
                str(mapping),
                "--profile",
                "b",
            ],
        )
        assert result.exit_code == 0, result.output
        assert '"code": "X"' in result.output

    def test_metadata_file_merges_into_definition(self, runner, mapping_file, tmp_path):
        metadata = tmp_path / "metadata.yaml"
        metadata.write_text(
            "title: My Definition\n"
            "scope: specific\n"
            "version: 1.0.0\n"
            "location: Berlin\n"
            "language: English\n"
            "organization: RKI\n"
        )
        result = runner.invoke(
            cli,
            [
                "convert-sql",
                "-s",
                "icd_code = 'A90'",
                "--mapping",
                str(mapping_file),
                "--metadata-file",
                str(metadata),
            ],
        )
        assert result.exit_code == 0, result.output
        assert '"title": "My Definition"' in result.output
        assert '"organization": "RKI"' in result.output

    def test_validate_flag_validates_output(self, runner, mapping_file, tmp_path):
        metadata = tmp_path / "metadata.yaml"
        metadata.write_text(
            "title: My Definition\n"
            "scope: specific\n"
            "version: 1.0.0\n"
            "location: Berlin\n"
            "language: English\n"
            "organization: RKI\n"
        )
        result = runner.invoke(
            cli,
            [
                "convert-sql",
                "-s",
                "icd_code = 'A90'",
                "--mapping",
                str(mapping_file),
                "--metadata-file",
                str(metadata),
                "--validate",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Validation successful" in result.output

    def test_enrich_ontology_calls_enrich(self, runner, mapping_file, mocker):
        mock_enrich = mocker.patch(
            "opensyndrome.cli.enrich_definition",
            side_effect=lambda d, mapper, verbose_callback=None: d,
        )
        result = runner.invoke(
            cli,
            [
                "convert-sql",
                "-s",
                "icd_code = 'A90'",
                "--mapping",
                str(mapping_file),
                "--enrich-ontology",
            ],
        )
        assert result.exit_code == 0, result.output
        mock_enrich.assert_called_once()

    def test_dialect_flag_is_passed(self, runner, mapping_file):
        result = runner.invoke(
            cli,
            [
                "convert-sql",
                "-s",
                "icd_code = 'A90'",
                "--mapping",
                str(mapping_file),
                "--dialect",
                "mysql",
            ],
        )
        assert result.exit_code == 0, result.output


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
