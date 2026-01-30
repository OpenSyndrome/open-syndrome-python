from unittest import mock
from unittest.mock import Mock, call

from opensyndrome.artifacts import (
    download_definitions,
    get_definition_dir,
    download_schema,
    get_schema_filepath,
)


@mock.patch("opensyndrome.artifacts.DEFINITIONS_DIR")
@mock.patch("opensyndrome.artifacts.download_definitions")
class TestGetDefinitionsDir:
    def test_return_definitions_dir_if_not_empty(self, mock_download, mock_dir):
        mock_dir.iterdir.return_value = ["schema.json", "v1/"]

        get_definition_dir()

        assert mock_dir.iterdir.called
        assert mock_download.called is False

    def test_download_definitions_from_repo_if_dir_is_empty(
        self, mock_download, mock_dir
    ):
        mock_dir.iterdir.return_value = []

        get_definition_dir()

        assert mock_dir.iterdir.called
        assert mock_download.called is True


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


@mock.patch("opensyndrome.artifacts.requests")
@mock.patch("opensyndrome.artifacts.DEFINITIONS_DIR")
class TestDownloadDefinitions:
    def test_download_definitions_recursively(self, mock_path, mock_requests):
        mock_response_v1 = Mock()
        mock_response_v1.json.return_value = [
            # some keys were omitted from the response due to its size
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

        mock_requests.get.side_effect = [
            mock_response_v1,
            mock_response_a,
            mock_response_file,
        ]

        mock_path.return_value.write_bytes.return_value = None
        mock_path.return_value.mkdir.return_value = None

        download_definitions()

        assert mock_requests.get.call_count == 3
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
        mock_requests.get.assert_has_calls(calls, any_order=True)

        assert (
            call.__truediv__().mkdir(parents=True, exist_ok=True)
            in mock_path.mock_calls
        )
        assert (
            call.__truediv__().__truediv__().write_bytes(b'{"key": "value"}')
            in mock_path.mock_calls
        )
