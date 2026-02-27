import re
import pytest
import polars as pl

from opensyndrome.filter import (
    ColumnSpec,
    load_profile,
    ProfileData,
    _code_to_regex,
    _apply_flags,
    _cast,
    InvalidOperator,
    _combine,
    UnresolvableCriterion,
    _build_code_expr,
    OSDEngine,
    _build_text_expr,
)

SEX_ENCODINGS = {"sex": {"male": "M", "female": "F"}}


@pytest.fixture
def fake_dataset():
    return pl.read_csv("tests/fixtures/fake_dataset.csv")


@pytest.fixture
def icd_columns():
    return [
        ColumnSpec("icd_code", concept="diagnosis"),
    ]


@pytest.fixture
def demographic_columns():
    return [
        ColumnSpec(
            "age", concept="demographic_criteria", attribute="age", dtype="integer"
        ),
        ColumnSpec("sex", concept="demographic_criteria", attribute="sex"),
    ]


@pytest.fixture
def epidemiological_history_columns():
    return [
        ColumnSpec("location", concept="epidemiological_history"),
    ]


@pytest.fixture
def all_columns(icd_columns, demographic_columns, epidemiological_history_columns):
    return icd_columns + demographic_columns + epidemiological_history_columns


@pytest.fixture
def profile(all_columns):
    return ProfileData(columns=all_columns, value_encodings=SEX_ENCODINGS)


@pytest.fixture
def engine(profile):
    return OSDEngine(profile)


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


class TestCodeToRegex:
    @pytest.mark.parametrize(
        "code, matching, non_matching",
        [
            ("A90", ["A90", "A90.1", "A90.12"], ["A900", "A901", "B90"]),
            ("J1%", ["J10", "J11", "J18", "J1X"], ["J20", "K10"]),
            ("A9%", ["A90", "A91", "A99"], ["B90", "A100"]),
        ],
    )
    def test_pattern_matches_and_rejects(self, code, matching, non_matching):
        pattern = _code_to_regex(code)
        for value in matching:
            assert re.match(
                pattern, value
            ), f"Expected '{value}' to match pattern for '{code}'"
        for value in non_matching:
            assert not re.match(
                pattern, value
            ), f"Expected '{value}' NOT to match pattern for '{code}'"

    def test_exact_code_does_not_match_extension(self):
        pattern = _code_to_regex("A90")
        assert not re.match(pattern, "A900")
        assert not re.match(pattern, "A901")

    def test_exact_code_matches_sub_code(self):
        pattern = _code_to_regex("A90")
        assert re.match(pattern, "A90.1")
        assert re.match(pattern, "A90.12")


class TestApplyFlags:
    def test_adds_case_insensitive_flag(self):
        assert _apply_flags("dengue", "i") == "(?i)dengue"

    def test_no_flags_returns_pattern_unchanged(self):
        assert _apply_flags("dengue", "") == "dengue"

    def test_ignores_unsupported_flags(self):
        assert _apply_flags("dengue", "z") == "dengue"


class TestCast:
    def test_skips_cast_when_column_is_any_integer_type(self):
        for dtype in (
            pl.Int8,
            pl.Int16,
            pl.Int32,
            pl.Int64,
            pl.UInt8,
            pl.UInt16,
            pl.UInt32,
            pl.UInt64,
        ):
            schema = {"age": dtype}
            expr = _cast(pl.col("age"), "age", "integer", schema)
            assert str(expr) == str(pl.col("age")), f"Expected no cast for {dtype}"

    def test_applies_cast_when_column_is_string_but_dtype_is_integer(self):
        schema = {"age": pl.String}
        expr = _cast(pl.col("age"), "age", "integer", schema)
        assert 'col("age").strict_cast(Int64)' in str(expr)

    def test_applies_cast_when_column_is_string_but_dtype_is_float(self):
        schema = {"body_temperature": pl.String}
        expr = _cast(pl.col("body_temperature"), "body_temperature", "float", schema)
        assert 'col("body_temperature").strict_cast(Float64)' in str(expr)

    def test_skips_cast_for_unknown_dtype(self):
        schema = {"col": pl.String}
        expr = _cast(pl.col("col"), "col", "unknown_type", schema)
        assert str(expr) == str(pl.col("col"))

    def test_skips_cast_when_float_column_matches_float_dtype(self):
        for dtype in (pl.Float32, pl.Float64):
            schema = {"val": dtype}
            expr = _cast(pl.col("val"), "val", "float", schema)
            assert str(expr) == str(pl.col("val")), f"Expected no cast for {dtype}"

    def test_applies_cast_when_schema_is_empty(self):
        expr = _cast(pl.col("age"), "age", "integer", {})
        assert str(expr) != str(pl.col("age"))


class TestCombine:
    def _bool_exprs(self, *values):
        return [pl.lit(value) for value in values]

    def test_and_requires_all_true(self):
        expr = _combine(self._bool_exprs(True, True), "AND", None)
        assert pl.select(expr).item() is True

        expr = _combine(self._bool_exprs(True, False), "AND", None)
        assert pl.select(expr).item() is False

    def test_or_requires_at_least_one_true(self):
        expr = _combine(self._bool_exprs(False, True), "OR", None)
        assert pl.select(expr).item() is True

        expr = _combine(self._bool_exprs(False, False), "OR", None)
        assert pl.select(expr).item() is False

    def test_at_least_counts_true_expressions(self):
        expr = _combine(self._bool_exprs(True, True, False), "AT_LEAST", 2)
        assert pl.select(expr).item() is True

        expr = _combine(self._bool_exprs(True, False, False), "AT_LEAST", 2)
        assert pl.select(expr).item() is False

    def test_defaults_to_and_when_operator_is_none(self):
        expr = _combine(self._bool_exprs(True, True), None, None)
        assert pl.select(expr).item() is True

    def test_at_least_without_n_raises(self):
        with pytest.raises(InvalidOperator, match="logical_operator_arguments"):
            _combine(self._bool_exprs(True, False), "AT_LEAST", None)

    def test_empty_list_raises(self):
        with pytest.raises(UnresolvableCriterion):
            _combine([], "AND", None)

    def test_unknown_operator_raises(self):
        with pytest.raises(InvalidOperator):
            _combine(self._bool_exprs(True), "NAND", None)


class TestBuildCodeExpr:
    def test_exact_code_matches_only_that_code(self, fake_dataset, icd_columns):
        criterion = {
            "type": "diagnosis",
            "name": "Dengue",
            "code": {"system": "ICD-10", "code": "A90"},
        }
        result = fake_dataset.filter(_build_code_expr(criterion, icd_columns))
        assert result.height == 52
        assert result["icd_code"].str.starts_with("A90").all()

    def test_exact_code_does_not_match_sibling_codes(self, fake_dataset, icd_columns):
        # A90 must not match A900 (which doesn't exist in this dataset, but the regex must be correct)
        assert fake_dataset.filter(
            pl.col("icd_code").str.strip_chars().eq("A900")
        ).is_empty()
        criterion = {
            "type": "diagnosis",
            "name": "Dengue",
            "code": {"system": "ICD-10", "code": "A90"},
        }
        result = fake_dataset.filter(_build_code_expr(criterion, icd_columns))
        assert result["icd_code"].is_in(["A90"]).all()

    def test_wildcard_matches_all_codes_in_range(self, fake_dataset, icd_columns):
        assert (
            fake_dataset.filter(pl.col("icd_code").str.starts_with("J1")).height == 38
        )
        criterion = {
            "type": "diagnosis",
            "name": "Influenza",
            "code": {"system": "ICD-10", "code": "J1%"},
        }
        result = fake_dataset.filter(_build_code_expr(criterion, icd_columns))
        assert result.height == 38
        assert result["icd_code"].str.starts_with("J1").all()

    def test_applies_to_all_diagnosis_columns_regardless_of_system(self, fake_dataset):
        # Two diagnosis columns might carry a different system name and both must be searched
        columns = [
            ColumnSpec("icd_code", concept="diagnosis", system="ICD-10"),
            ColumnSpec("icd_code", concept="diagnosis", system="CID-10"),
        ]
        criterion = {
            "type": "diagnosis",
            "name": "Dengue",
            "code": {"system": "SNOMED-CT", "code": "A90"},
        }
        result = fake_dataset.filter(_build_code_expr(criterion, columns))
        assert result.height == 52

    def test_strips_whitespace_from_column_values(self):
        df = pl.DataFrame({"icd_code": ["A90 ", " A90", "A90", "B00"]})
        columns = [ColumnSpec("icd_code", concept="diagnosis")]
        criterion = {
            "type": "diagnosis",
            "name": "Dengue",
            "code": {"system": "ICD-10", "code": "A90"},
        }
        result = df.filter(_build_code_expr(criterion, columns))
        assert result.height == 3

    def test_raises_when_no_diagnosis_column_exists(self):
        columns = [ColumnSpec("age", concept="demographic_criteria", attribute="age")]
        criterion = {
            "type": "diagnosis",
            "name": "X",
            "code": {"system": "ICD-10", "code": "A90"},
        }
        with pytest.raises(UnresolvableCriterion, match="diagnosis"):
            _build_code_expr(criterion, columns)


class TestBuildTextExpr:
    def test_matches_rows_containing_name_pattern(
        self, fake_dataset, epidemiological_history_columns
    ):
        criterion = {"type": "symptom", "name": "Frankfurt"}
        expr = _build_text_expr(
            criterion, epidemiological_history_columns, "epidemiological_history"
        )
        result = fake_dataset.filter(expr)
        assert result.height == 33
        assert result["location"].eq("Frankfurt").all()

    def test_regex_pattern_takes_precedence_over_name(
        self, fake_dataset, epidemiological_history_columns
    ):
        criterion = {"type": "symptom", "name": "NOMATCH", "regex_pattern": "Frankfurt"}
        expr = _build_text_expr(
            criterion, epidemiological_history_columns, "epidemiological_history"
        )
        result = fake_dataset.filter(expr)
        assert result.height == 33

    def test_flag_i_makes_match_case_insensitive(
        self, fake_dataset, epidemiological_history_columns
    ):
        sensitive = {"type": "symptom", "name": "frankfurt"}
        insensitive = {**sensitive, "regex_flags": "i"}
        sensitive_expr = _build_text_expr(
            sensitive, epidemiological_history_columns, "epidemiological_history"
        )
        sensitive_result = fake_dataset.filter(sensitive_expr)
        insensitive_expr = _build_text_expr(
            insensitive, epidemiological_history_columns, "epidemiological_history"
        )
        insensitive_result = fake_dataset.filter(insensitive_expr)
        assert insensitive_result.height == 33
        assert sensitive_result.height == 0

    def test_raises_when_no_column_mapped_to_concept(self, icd_columns):
        criterion = {"type": "epidemiological_history", "name": "fever"}
        with pytest.raises(UnresolvableCriterion, match="epidemiological_history"):
            _build_text_expr(criterion, icd_columns, "epidemiological_history")
