import pytest

from opensyndrome.filter import ColumnSpec


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
