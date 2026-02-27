import pytest

from opensyndrome.filter import ColumnSpec, load_profile, ProfileData


class TestColumnSpec:
    def test_diagnosis_column_without_system(self):
        spec = ColumnSpec("icd_code", concept="diagnosis")
        assert spec.col_name == "icd_code"
        assert spec.concept == "diagnosis"
        assert spec.system is None
        assert spec.attribute is None
        assert spec.dtype == "string"

    def test_diagnosis_column_with_optional_system(self):
        spec = ColumnSpec("icd_code", concept="diagnosis", system="ICD-10")
        assert spec.system == "ICD-10"

    def test_demographic_column(self):
        spec = ColumnSpec(
            "age", concept="demographic_criteria", attribute="age", dtype="integer"
        )
        assert spec.attribute == "age"
        assert spec.system is None

    def test_dtype_defaults_to_string(self):
        spec = ColumnSpec("notes", concept="symptom")
        assert spec.dtype == "string"

    def test_from_dict(self):
        spec = ColumnSpec.from_dict("cid", {"concept": "diagnosis", "dtype": "string"})
        assert spec.col_name == "cid"
        assert spec.system is None

    def test_from_dict_preserves_optional_system(self):
        spec = ColumnSpec.from_dict("cid", {"concept": "diagnosis", "system": "CID-10"})
        assert spec.system == "CID-10"

    def test_raises_for_unknown_concept(self):
        with pytest.raises(ValueError, match="unknown concept"):
            ColumnSpec("col", concept="magic_concept")

    def test_raises_when_demographic_missing_attribute(self):
        with pytest.raises(ValueError, match="no 'attribute'"):
            ColumnSpec("col", concept="demographic_criteria")


class TestLoadProfile:
    def test_returns_profile_data_with_columns(self):
        yaml_data = {
            "profiles": [
                {
                    "name": "test",
                    "columns": {
                        "age": {
                            "concept": "demographic_criteria",
                            "attribute": "age",
                            "dtype": "integer",
                        },
                    },
                }
            ]
        }
        profile = load_profile(yaml_data, "test")
        assert isinstance(profile, ProfileData)
        assert len(profile.columns) == 1
        assert profile.columns[0].col_name == "age"
        assert profile.value_encodings == {}

    def test_returns_value_encodings_when_defined(self):
        yaml_data = {
            "profiles": [
                {
                    "name": "test",
                    "value_encodings": {"sex": {"male": "M", "female": "F"}},
                    "columns": {
                        "sex": {"concept": "demographic_criteria", "attribute": "sex"},
                    },
                }
            ]
        }
        profile = load_profile(yaml_data, "test")
        assert profile.value_encodings == {"sex": {"male": "M", "female": "F"}}

    def test_raises_for_unknown_profile(self):
        with pytest.raises(KeyError, match="missing"):
            load_profile({"profiles": []}, "missing")
