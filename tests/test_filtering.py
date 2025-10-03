from pathlib import Path
from unittest import mock
from unittest.mock import Mock, call

from opensyndrome.filtering import (
    download_definitions,
    filter_cases,
    find_cases_from,
    overlap_definitions,
    get_definition_dir,
    download_schema,
    get_schema_filepath,
)
import polars as pl


@mock.patch(
    "opensyndrome.filtering.get_definition_dir",
    return_value=Path("tests/definitions/v1"),
)
class TestFilterRecordsBasedOnDefinition:
    def test_filter_records_when_the_same_column_is_targeted(
        self, mock_definitions_dir
    ):
        df = pl.DataFrame(
            {
                "week": [1, 1, 1, 2, 2, 2, 1],
                "year": [
                    2025,
                    2025,
                    2025,
                    2024,
                    2024,
                    2024,
                    2024,
                ],
                "my_icd_code": [
                    "J109",
                    "J101",
                    "A929",
                    "A922",
                    "A929",
                    "U071",
                    "A929",
                ],
            }
        )
        mapping = [
            {"system": "ICD-10", "code": "my_icd_code"},
        ]
        assert df.shape == (7, 3)
        df = filter_cases(df, mapping, "arbovirosis_paraguay_sd")

        assert df.shape == (7, 4)
        assert "arbovirosis_paraguay_sd" in df.columns
        assert df["arbovirosis_paraguay_sd"].sum() == 3

    def test_filter_records_when_multiple_columns_are_targeted(
        self, mock_definitions_dir
    ):
        df = pl.DataFrame(
            {
                "week": [1, 1, 1, 2, 2, 2, 1],
                "year": [
                    2025,
                    2025,
                    2025,
                    2024,
                    2024,
                    2024,
                    2024,
                ],
                "my_icd_code": [
                    None,
                    "J101",
                    "A929",
                    "A922",
                    "A929",
                    "U071",
                    "A929",
                ],
                "ciap": [
                    "A77",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ],
            }
        )
        mapping = [
            {"system": "CID 10", "code": "my_icd_code"},
            {"system": "CID", "code": "my_icd_code"},
            {"system": "CIAP", "code": "ciap"},
        ]
        assert df.shape == (7, 4)
        df = filter_cases(df, mapping, "arbovirosis_aesop_brazil_sd")

        assert df.shape == (7, 5)
        assert "arbovirosis_aesop_brazil_sd" in df.columns
        assert df["arbovirosis_aesop_brazil_sd"].sum() == 4

    def test_filter_records_using_like_condition(self, mock_definitions_dir):
        df = pl.DataFrame(
            {
                "week": [1, 1, 1, 2, 2, 2, 1],
                "year": [
                    2025,
                    2025,
                    2025,
                    2024,
                    2024,
                    2024,
                    2024,
                ],
                "my_icd_code": [
                    None,
                    "J101",
                    "A972",
                    "A922",
                    "A929",
                    "U071",
                    "A979",
                ],
                "ciap": [
                    "A77",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ],
            }
        )
        mapping = [
            {"system": "CID 10", "code": "my_icd_code"},
        ]
        assert df.shape == (7, 4)
        df = filter_cases(df, mapping, "arbovirosis_aesop_brazil_sd_with_like")

        assert df.shape == (7, 5)
        assert "arbovirosis_aesop_brazil_sd_with_like" in df.columns
        assert df["arbovirosis_aesop_brazil_sd_with_like"].sum() == 2

    def test_filter_records_when_column_already_exists(self, mock_definitions_dir):
        df = pl.DataFrame(
            {
                "week": [1, 1, 1, 2, 2, 2, 1],
                "year": [
                    2025,
                    2025,
                    2025,
                    2024,
                    2024,
                    2024,
                    2024,
                ],
                "my_icd_code": [
                    "J109",
                    "J101",
                    "A929",
                    "A922",
                    "A929",
                    "U071",
                    "A929",
                ],
            }
        )
        mapping = [
            {"system": "ICD-10", "code": "my_icd_code"},
        ]
        assert df.shape == (7, 3)
        df_filtered = filter_cases(df, mapping, "arbovirosis_paraguay_sd")

        assert df_filtered.shape == (7, 4)
        assert "arbovirosis_paraguay_sd" in df_filtered.columns

        df_filtered_again = filter_cases(
            df_filtered, mapping, "arbovirosis_paraguay_sd"
        )

        assert df_filtered_again.shape == (7, 4)
        assert "arbovirosis_paraguay_sd" in df_filtered_again.columns


@mock.patch(
    "opensyndrome.filtering.get_definition_dir",
    return_value=Path("tests/definitions/v1"),
)
class TestCalculateOverlapAmongDefinitions:
    def test_calculate_overlap(self, mock_definitions_dir):
        definitions = find_cases_from("arbovirosis")
        assert len(definitions) == 3
        assert overlap_definitions(definitions) == {"A929"}

    def test_return_none_if_definitions_are_not_greater_than_two(
        self, mock_definitions_dir
    ):
        definitions = find_cases_from("covid")
        assert len(definitions) == 1
        assert overlap_definitions(definitions) is None


@mock.patch("opensyndrome.filtering.DEFINITIONS_DIR")
@mock.patch("opensyndrome.filtering.download_definitions")
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
    @mock.patch("opensyndrome.filtering.SCHEMA_DIR")
    @mock.patch("opensyndrome.filtering.requests")
    def test_download_schema_from_github_repo(self, mock_requests, mock_dir):
        response = Mock()
        response.json.return_value = {"version": "1.0.0"}  # fake schema
        mock_requests.get.return_value = response

        download_schema()

        assert mock_requests.get.called
        assert mock_dir.mock_calls == [call.write_text('{"version": "1.0.0"}')]


@mock.patch("opensyndrome.filtering.SCHEMA_DIR")
@mock.patch("opensyndrome.filtering.download_schema")
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


@mock.patch("opensyndrome.filtering.requests")
@mock.patch("opensyndrome.filtering.DEFINITIONS_DIR")
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
