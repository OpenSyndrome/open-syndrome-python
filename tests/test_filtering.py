from osi.filtering import filter_cases, find_cases_from, overlap_definitions
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
                    "A929",
                    "A922",
                    "A929",
                    "U071",
                    "J20",
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
            {"system": "ICD-10", "code": "my_icd_code"},
        ]
        assert df.shape == (7, 4)
        df = filter_cases(df, mapping, "sari_rki_germany_sd")

        assert df.shape == (7, 5)
        assert "sari_rki_germany_sd" in df.columns
        assert df["sari_rki_germany_sd"].sum() == 3

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
        definitions = find_cases_from("covid")
        assert overlap_definitions(definitions) == 0.25  # %
