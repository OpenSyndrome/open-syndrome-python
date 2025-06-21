from osi.filtering import filter_cases
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
                    "J10.9",
                    "J10.1",
                    "A92.9",
                    "A92.2",
                    "A92.9",
                    "U07.1",
                    "A92.9",
                ],
            }
        )
        mapping = [
            {"system": "ICD-10", "code": "my_icd_code"},
        ]
        assert df.shape == (7, 3)
        df = filter_cases(df, mapping, "arbovirosis_paraguay_sd")

        assert df.shape == (3, 3)

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

        assert df.shape == (4, 4)
