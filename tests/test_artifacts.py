from pathlib import Path
from unittest import mock
from unittest.mock import Mock, call

import pytest

from opensyndrome.artifacts import (
    DEFINITIONS_DIR_ENV_VAR,
    LOCAL_DEFINITIONS_ONLY_ENV_VAR,
    download_definitions,
    download_schema,
    get_definition_dir,
    get_definition_dirs,
    get_schema_filepath,
    local_definitions_dir,
    local_definitions_only,
)


def _add_definition(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "dengue.json").write_text("{}", encoding="utf-8")


@pytest.fixture
def community_dir(monkeypatch, tmp_path) -> Path:
    directory = tmp_path / "community"
    directory.mkdir()
    monkeypatch.setattr("opensyndrome.artifacts.DEFINITIONS_DIR", directory)
    return directory


@pytest.fixture
def clean_env(monkeypatch) -> None:
    monkeypatch.delenv(DEFINITIONS_DIR_ENV_VAR, raising=False)
    monkeypatch.delenv(LOCAL_DEFINITIONS_ONLY_ENV_VAR, raising=False)


class TestDownloadSchema:
    @mock.patch("opensyndrome.artifacts.SCHEMA_DIR")
    @mock.patch("opensyndrome.artifacts.requests")
    def test_download_schema_from_github_repo(self, mock_requests, mock_dir):
        response = Mock()
        response.json.return_value = {"version": "1.0.0"}  # fake schema
        mock_requests.get.return_value = response

        download_schema()

        assert mock_requests.get.called
        assert mock_dir.mock_calls == [call.write_text('{"version": "1.0.0"}')]


@mock.patch("opensyndrome.artifacts.SCHEMA_DIR")
@mock.patch("opensyndrome.artifacts.download_schema")
class TestGetSchemaFilepath:
    def test_return_schema_filepath_if_exists(self, mock_download, mock_dir):
        mock_dir.exists.return_value = True

        get_schema_filepath()

        assert mock_dir.exists.called
        assert mock_download.called is False

    def test_download_schema_from_repo_if_dir_does_not_exist(
        self, mock_download, mock_dir
    ):
        mock_dir.exists.return_value = False

        get_schema_filepath()

        assert mock_dir.exists.called
        assert mock_download.called is True


class TestLocalDefinitionsDir:
    def test_returns_none_when_env_var_is_unset(self, clean_env):
        assert local_definitions_dir() is None

    def test_returns_none_when_env_var_is_empty(self, clean_env, monkeypatch):
        monkeypatch.setenv(DEFINITIONS_DIR_ENV_VAR, "")

        assert local_definitions_dir() is None

    def test_returns_existing_directory_from_env_var(
        self, clean_env, monkeypatch, tmp_path
    ):
        _add_definition(tmp_path / "local")
        monkeypatch.setenv(DEFINITIONS_DIR_ENV_VAR, str(tmp_path / "local"))

        assert local_definitions_dir() == tmp_path / "local"

    def test_expands_user_in_env_var(self, clean_env, monkeypatch, tmp_path):
        _add_definition(tmp_path / "local")
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv(DEFINITIONS_DIR_ENV_VAR, "~/local")

        assert local_definitions_dir() == tmp_path / "local"

    def test_relative_env_var_is_returned_as_absolute_path(
        self, clean_env, monkeypatch, tmp_path
    ):
        _add_definition(tmp_path / "my-definitions")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(DEFINITIONS_DIR_ENV_VAR, "./my-definitions")

        result = local_definitions_dir()

        assert result.is_absolute()
        assert result == tmp_path / "my-definitions"

    def test_raises_when_directory_does_not_exist(
        self, clean_env, monkeypatch, tmp_path
    ):
        monkeypatch.setenv(DEFINITIONS_DIR_ENV_VAR, str(tmp_path / "missing"))

        with pytest.raises(FileNotFoundError, match=DEFINITIONS_DIR_ENV_VAR):
            local_definitions_dir()


class TestLocalDefinitionsOnly:
    def test_defaults_to_false_when_env_var_is_unset(self, clean_env):
        assert local_definitions_only() is False

    @pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "on", " 1 "])
    def test_truthy_env_var_values(self, clean_env, monkeypatch, value):
        monkeypatch.setenv(LOCAL_DEFINITIONS_ONLY_ENV_VAR, value)

        assert local_definitions_only() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "anything"])
    def test_falsy_env_var_values(self, clean_env, monkeypatch, value):
        monkeypatch.setenv(LOCAL_DEFINITIONS_ONLY_ENV_VAR, value)

        assert local_definitions_only() is False


@mock.patch("opensyndrome.artifacts.download_definitions")
class TestGetDefinitionDirs:
    """Every combination of the two environment variables, the community
    directory state and ``force``."""

    @pytest.mark.parametrize("force", [False, True])
    @pytest.mark.parametrize("community_is_empty", [False, True])
    def test_without_env_vars_returns_community_only(
        self, mock_download, clean_env, community_dir, community_is_empty, force
    ):
        if not community_is_empty:
            _add_definition(community_dir)

        result = get_definition_dirs(force=force)

        assert result == [community_dir]
        assert mock_download.called is (community_is_empty or force)

    @pytest.mark.parametrize("force", [False, True])
    @pytest.mark.parametrize("community_is_empty", [False, True])
    def test_with_local_dir_returns_community_then_local(
        self,
        mock_download,
        clean_env,
        monkeypatch,
        tmp_path,
        community_dir,
        community_is_empty,
        force,
    ):
        _add_definition(tmp_path / "local")
        monkeypatch.setenv(DEFINITIONS_DIR_ENV_VAR, str(tmp_path / "local"))
        if not community_is_empty:
            _add_definition(community_dir)

        result = get_definition_dirs(force=force)

        assert result == [community_dir, tmp_path / "local"]
        assert mock_download.called is (community_is_empty or force)

    @pytest.mark.parametrize("force", [False, True])
    @pytest.mark.parametrize("community_is_empty", [False, True])
    def test_with_local_only_returns_local_and_never_downloads(
        self,
        mock_download,
        clean_env,
        monkeypatch,
        tmp_path,
        community_dir,
        community_is_empty,
        force,
    ):
        _add_definition(tmp_path / "local")
        monkeypatch.setenv(DEFINITIONS_DIR_ENV_VAR, str(tmp_path / "local"))
        monkeypatch.setenv(LOCAL_DEFINITIONS_ONLY_ENV_VAR, "1")
        if not community_is_empty:
            _add_definition(community_dir)

        result = get_definition_dirs(force=force)

        assert result == [tmp_path / "local"]
        assert mock_download.called is False

    @pytest.mark.parametrize("force", [False, True])
    def test_local_only_without_local_dir_raises(
        self, mock_download, clean_env, monkeypatch, community_dir, force
    ):
        monkeypatch.setenv(LOCAL_DEFINITIONS_ONLY_ENV_VAR, "1")

        with pytest.raises(ValueError, match=DEFINITIONS_DIR_ENV_VAR):
            get_definition_dirs(force=force)

        assert mock_download.called is False

    def test_local_only_falsy_value_behaves_as_unset(
        self, mock_download, clean_env, monkeypatch, tmp_path, community_dir
    ):
        _add_definition(tmp_path / "local")
        monkeypatch.setenv(DEFINITIONS_DIR_ENV_VAR, str(tmp_path / "local"))
        monkeypatch.setenv(LOCAL_DEFINITIONS_ONLY_ENV_VAR, "0")

        assert get_definition_dirs() == [community_dir, tmp_path / "local"]

    @pytest.mark.parametrize(
        ("local_only", "env_value", "expected_local_only"),
        [
            (None, None, False),
            (None, "1", True),
            (None, "0", False),
            (True, None, True),
            (True, "1", True),
            (True, "0", True),
            (False, None, False),
            (False, "1", False),
            (False, "0", False),
        ],
    )
    def test_local_only_argument_takes_precedence_over_env_var(
        self,
        mock_download,
        clean_env,
        monkeypatch,
        tmp_path,
        community_dir,
        local_only,
        env_value,
        expected_local_only,
    ):
        _add_definition(tmp_path / "local")
        monkeypatch.setenv(DEFINITIONS_DIR_ENV_VAR, str(tmp_path / "local"))
        if env_value is not None:
            monkeypatch.setenv(LOCAL_DEFINITIONS_ONLY_ENV_VAR, env_value)

        result = get_definition_dirs(local_only=local_only)

        if expected_local_only:
            assert result == [tmp_path / "local"]
        else:
            assert result == [community_dir, tmp_path / "local"]

    @pytest.mark.parametrize(
        ("pass_argument", "set_env_var", "expected"),
        [
            (True, True, "from-arg"),
            (True, False, "from-arg"),
            (False, True, "from-env"),
            (False, False, None),
        ],
    )
    def test_local_dir_argument_takes_precedence_over_env_var(
        self,
        mock_download,
        clean_env,
        monkeypatch,
        tmp_path,
        community_dir,
        pass_argument,
        set_env_var,
        expected,
    ):
        _add_definition(tmp_path / "from-arg")
        _add_definition(tmp_path / "from-env")
        if set_env_var:
            monkeypatch.setenv(DEFINITIONS_DIR_ENV_VAR, str(tmp_path / "from-env"))
        argument = tmp_path / "from-arg" if pass_argument else None

        result = get_definition_dirs(local_dir=argument)

        expected_dirs = [community_dir]
        if expected:
            expected_dirs.append(tmp_path / expected)
        assert result == expected_dirs

    def test_local_dir_argument_accepts_a_string(
        self, mock_download, clean_env, tmp_path, community_dir
    ):
        _add_definition(tmp_path / "local")

        result = get_definition_dirs(local_dir=str(tmp_path / "local"))

        assert result == [community_dir, tmp_path / "local"]

    def test_relative_local_dir_argument_is_returned_as_absolute_path(
        self, mock_download, clean_env, monkeypatch, tmp_path, community_dir
    ):
        _add_definition(tmp_path / "my-definitions")
        monkeypatch.chdir(tmp_path)

        result = get_definition_dirs(local_dir="my-definitions")

        assert result == [community_dir, tmp_path / "my-definitions"]
        assert result[1].is_absolute()


@mock.patch("opensyndrome.artifacts.download_definitions")
class TestGetDefinitionDirDeprecated:
    """Kept for callers that expect a single community path; scheduled for removal."""

    @pytest.mark.parametrize("force", [False, True])
    @pytest.mark.parametrize("community_is_empty", [False, True])
    def test_returns_community_path_and_downloads_as_before(
        self, mock_download, clean_env, community_dir, community_is_empty, force
    ):
        if not community_is_empty:
            _add_definition(community_dir)

        with pytest.warns(DeprecationWarning, match="get_definition_dirs"):
            result = get_definition_dir(force=force)

        assert result == community_dir
        assert mock_download.called is (community_is_empty or force)

    def test_ignores_local_definitions_env_vars(
        self, mock_download, clean_env, monkeypatch, tmp_path, community_dir
    ):
        _add_definition(community_dir)
        _add_definition(tmp_path / "local")
        monkeypatch.setenv(DEFINITIONS_DIR_ENV_VAR, str(tmp_path / "local"))
        monkeypatch.setenv(LOCAL_DEFINITIONS_ONLY_ENV_VAR, "1")

        with pytest.warns(DeprecationWarning, match="removed"):
            result = get_definition_dir()

        assert result == community_dir
        assert mock_download.called is False


@mock.patch("opensyndrome.artifacts.requests")
class TestDownloadDefinitions:
    @staticmethod
    def _github_responses() -> list[Mock]:
        mock_response_v1 = Mock()
        mock_response_v1.json.return_value = [
            {
                "name": "a",
                "path": "definitions/v1/a",
                "url": "https://api.github.com/repos/OpenSyndrome/definitions/contents/definitions/v1/a?ref=main",
                "type": "dir",
            }
        ]
        mock_response_a = Mock()
        mock_response_a.json.return_value = [
            {
                "name": "acuteflaccidparalysis_kenya.json",
                "path": "definitions/v1/a/acuteflaccidparalysis_kenya.json",
                "url": "https://api.github.com/repos/OpenSyndrome/definitions/contents/definitions/v1/a/acuteflaccidparalysis_kenya.json?ref=main",
                "download_url": "https://raw.githubusercontent.com/OpenSyndrome/definitions/main/definitions/v1/a/acuteflaccidparalysis_kenya.json",
                "type": "file",
            }
        ]
        mock_response_file = Mock()
        mock_response_file.content = b'{"key": "value"}'
        return [mock_response_v1, mock_response_a, mock_response_file]

    def test_download_definitions_recursively_into_community_dir(
        self, mock_requests, community_dir
    ):
        mock_requests.get.side_effect = self._github_responses()

        download_definitions()

        calls = [
            call(
                "https://api.github.com/repos/OpenSyndrome/definitions/contents/definitions/v1?ref=main"
            ),
            call(
                "https://api.github.com/repos/OpenSyndrome/definitions/contents/definitions/v1/a?ref=main"
            ),
            call(
                "https://raw.githubusercontent.com/OpenSyndrome/definitions/main/definitions/v1/a/acuteflaccidparalysis_kenya.json"
            ),
        ]
        mock_requests.get.assert_has_calls(calls)
        downloaded = community_dir / "a" / "acuteflaccidparalysis_kenya.json"
        assert downloaded.read_bytes() == b'{"key": "value"}'

    def test_download_ignores_local_definitions_dir(
        self, mock_requests, clean_env, monkeypatch, tmp_path, community_dir
    ):
        _add_definition(tmp_path / "local")
        monkeypatch.setenv(DEFINITIONS_DIR_ENV_VAR, str(tmp_path / "local"))
        mock_requests.get.side_effect = self._github_responses()

        download_definitions()

        assert (community_dir / "a" / "acuteflaccidparalysis_kenya.json").exists()
        assert not (tmp_path / "local" / "a").exists()
