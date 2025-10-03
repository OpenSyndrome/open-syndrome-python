from unittest import mock
from unittest.mock import Mock, call

from osi.filtering import (
    filter_cases,
    find_cases_from,
    overlap_definitions,
    get_definition_dir,
    download_schema,
    get_schema_filepath,
)
import polars as pl


class TestFilterRecordsBasedOnDefinition:
    def test_filter_records_when_the_same_column_is_targeted(self):
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

    def test_filter_records_when_multiple_columns_are_targeted(self):
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

    def test_filter_records_using_like_condition(self):
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

    def test_filter_records_when_column_already_exists(self):
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


class TestCalculateOverlapAmongDefinitions:
    def test_calculate_overlap(self):
        definitions = find_cases_from("arbovirosis")
        assert len(definitions) == 3
        assert overlap_definitions(definitions) == {"A929"}

    def test_return_none_if_definitions_are_not_greater_than_two(self):
        definitions = find_cases_from("covid")
        assert len(definitions) == 1
        assert overlap_definitions(definitions) is None


@mock.patch("osi.filtering.DEFINITIONS_DIR")
@mock.patch("osi.filtering.download_definitions")
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
    @mock.patch("osi.filtering.SCHEMA_DIR")
    @mock.patch("osi.filtering.requests")
    def test_download_schema_from_github_repo(self, mock_requests, mock_dir):
        response = Mock()
        response.json.return_value = {"version": "1.0.0"}  # fake schema
        mock_requests.get.return_value = response

        download_schema()

        assert mock_requests.get.called
        assert mock_dir.mock_calls == [call.write_text('{"version": "1.0.0"}')]


@mock.patch("osi.filtering.SCHEMA_DIR")
@mock.patch("osi.filtering.download_schema")
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
