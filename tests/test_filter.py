import re
import pytest
import polars as pl

from opensyndrome.filter import (
    ColumnSpec,
    load_profile,
    ProfileData,
    InvalidOperator,
    UnresolvableCriterion,
    OSDEngine,
    _code_to_regex,
    _apply_flags,
    _cast,
    _combine,
    _build_code_expr,
    _build_text_expr,
    _build_attr_expr,
    _parse_criterion,
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


class TestBuildAttrExpr:
    def test_numeric_greater_than(self, fake_dataset, demographic_columns):
        assert (fake_dataset["age"] > 60).sum() == 190  # expected value
        criterion = {
            "type": "demographic_criteria",
            "attribute": "age",
            "operator": ">",
            "value": 60,
        }
        result = fake_dataset.filter(_build_attr_expr(criterion, demographic_columns))
        assert result.height == 190
        assert (result["age"] > 60).all()

    def test_value_encoding_translates_canonical_value(
        self, fake_dataset, demographic_columns
    ):
        assert (fake_dataset["sex"].eq("F")).sum() == 167  # value in the dataset
        criterion = {
            "type": "demographic_criteria",
            "attribute": "sex",
            "operator": "==",
            "value": "female",
        }
        result = fake_dataset.filter(
            _build_attr_expr(criterion, demographic_columns, SEX_ENCODINGS)
        )
        assert result.height == 167
        assert result["sex"].eq("F").all()

    def test_without_encoding_uses_value_as_is(self, fake_dataset, demographic_columns):
        assert (fake_dataset["sex"].eq("F")).sum() == 167
        criterion = {
            "type": "demographic_criteria",
            "attribute": "sex",
            "operator": "==",
            "value": "F",
        }
        result = fake_dataset.filter(_build_attr_expr(criterion, demographic_columns))
        assert result.height == 167
        assert result["sex"].eq("F").all()

    def test_regex_operator_matches_pattern(self, fake_dataset, demographic_columns):
        assert fake_dataset["sex"].is_in(["F", "M"]).sum() == 338
        criterion = {
            "type": "demographic_criteria",
            "attribute": "sex",
            "operator": "regex",
            "regex_pattern": "^[MF]$",
        }
        result = fake_dataset.filter(_build_attr_expr(criterion, demographic_columns))
        assert result.height == 338
        assert result["sex"].is_in(["M", "F"]).all()

    def test_raises_when_attribute_not_mapped(self, demographic_columns):
        criterion = {
            "type": "demographic_criteria",
            "attribute": "weight",
            "operator": ">",
            "value": 70,
        }
        with pytest.raises(UnresolvableCriterion, match="weight"):
            _build_attr_expr(criterion, demographic_columns)

    def test_raises_for_unsupported_operator(self, demographic_columns):
        criterion = {
            "type": "demographic_criteria",
            "attribute": "age",
            "operator": "LIKE",
            "value": 30,
        }
        with pytest.raises(InvalidOperator):
            _build_attr_expr(criterion, demographic_columns)


# TODO
class TestParseCriterion:
    def test_and_operator_requires_all_conditions(self, fake_dataset, all_columns):
        criterion = {
            "type": "criterion",
            "logical_operator": "AND",
            "values": [
                {
                    "type": "demographic_criteria",
                    "attribute": "sex",
                    "operator": "==",
                    "value": "F",
                },
                {
                    "type": "demographic_criteria",
                    "attribute": "age",
                    "operator": ">",
                    "value": 60,
                },
            ],
        }
        result = fake_dataset.filter(_parse_criterion(criterion, all_columns))
        assert (result["sex"].eq("F")).all()
        assert (result["age"].gt(60)).all()

    def test_or_operator_result_is_superset_of_and(self, fake_dataset, all_columns):
        base = {
            "type": "criterion",
            "values": [
                {
                    "type": "demographic_criteria",
                    "attribute": "sex",
                    "operator": "==",
                    "value": "F",
                },
                {
                    "type": "demographic_criteria",
                    "attribute": "age",
                    "operator": ">",
                    "value": 60,
                },
            ],
        }
        result_or = fake_dataset.filter(
            _parse_criterion({**base, "logical_operator": "OR"}, all_columns)
        )
        result_and = fake_dataset.filter(
            _parse_criterion({**base, "logical_operator": "AND"}, all_columns)
        )
        # TODO
        assert result_or.height >= result_and.height

    def test_at_least_2_of_3_is_superset_of_and_all_3(self, fake_dataset, all_columns):
        criterion = {
            "type": "criterion",
            "logical_operator": "AT_LEAST",
            "logical_operator_arguments": [2],
            "values": [
                {
                    "type": "demographic_criteria",
                    "attribute": "sex",
                    "operator": "==",
                    "value": "F",
                },
                {
                    "type": "demographic_criteria",
                    "attribute": "age",
                    "operator": ">",
                    "value": 60,
                },
                {"type": "epidemiological_history", "name": "Frankfurt"},
            ],
        }
        result_at_least = fake_dataset.filter(_parse_criterion(criterion, all_columns))
        result_and = fake_dataset.filter(
            _parse_criterion({**criterion, "logical_operator": "AND"}, all_columns)
        )
        assert result_at_least.height >= result_and.height

    def test_at_least_without_arguments_raises(self, all_columns):
        criterion = {
            "type": "criterion",
            "logical_operator": "AT_LEAST",
            "values": [
                {
                    "type": "demographic_criteria",
                    "attribute": "age",
                    "operator": ">",
                    "value": 18,
                },
            ],
        }
        with pytest.raises(InvalidOperator, match="logical_operator_arguments"):
            _parse_criterion(criterion, all_columns)

    def test_missing_type_raises_with_clear_message(self, all_columns):
        with pytest.raises(UnresolvableCriterion, match="missing.*type"):
            _parse_criterion({"name": "no type here"}, all_columns)

    def test_unknown_type_raises_with_type_name(self, all_columns):
        with pytest.raises(UnresolvableCriterion, match="unknown_type"):
            _parse_criterion({"type": "unknown_type", "name": "x"}, all_columns)

    def test_symptom_with_attribute_and_operator_uses_attr_expr(
        self, fake_dataset, demographic_columns
    ):
        # body_temperature >= 39 on a numeric column is the same routing as demographic_criteria
        columns = [
            ColumnSpec(
                "age", concept="symptom", attribute="body_temperature", dtype="integer"
            )
        ]
        criterion = {
            "type": "symptom",
            "name": "High body temperature",
            "attribute": "body_temperature",
            "operator": ">=",
            "value": 60,
        }
        result = fake_dataset.filter(_parse_criterion(criterion, columns))
        assert (result["age"].ge(60)).all()

    def test_symptom_without_attribute_uses_text_expr(
        self, fake_dataset, epidemiological_history_columns
    ):
        criterion = {"type": "epidemiological_history", "name": "Frankfurt"}
        result = fake_dataset.filter(
            _parse_criterion(criterion, epidemiological_history_columns)
        )
        assert result.height > 0
        assert (result["location"].eq("Frankfurt")).all()

    def test_diagnostic_test_without_attribute_uses_text_expr(self, fake_dataset):
        # diagnostic_test with only a name falls back to text matching against diagnostic_test columns
        columns = [ColumnSpec("location", concept="diagnostic_test")]
        criterion = {"type": "diagnostic_test", "name": "Frankfurt"}
        result = fake_dataset.filter(_parse_criterion(criterion, columns))
        assert result.height > 0
        assert (result["location"].eq("Frankfurt")).all()

    def test_epidemiological_history_with_attribute_uses_attr_expr(self, fake_dataset):
        columns = [
            ColumnSpec(
                "age",
                concept="epidemiological_history",
                attribute="onset_days",
                dtype="integer",
            )
        ]
        criterion = {
            "type": "epidemiological_history",
            "name": "Recent exposure",
            "attribute": "onset_days",
            "operator": "<=",
            "value": 14,
        }
        result = fake_dataset.filter(_parse_criterion(criterion, columns))
        assert (result["age"].le(14)).all()

    def test_syndrome_type_raises(self, all_columns):
        with pytest.raises(UnresolvableCriterion, match="syndrome"):
            _parse_criterion({"type": "syndrome", "name": "Dengue"}, all_columns)

    def test_professional_judgment_raises(self, all_columns):
        with pytest.raises(UnresolvableCriterion, match="professional_judgment"):
            _parse_criterion(
                {"type": "professional_judgment", "name": "Clinical assessment"},
                all_columns,
            )


class TestOSDEngineLabel:
    _dengue_def = {
        "inclusion_criteria": [
            {"type": "diagnosis", "code": {"system": "ICD-10", "code": "A90"}}
        ]
    }
    _influenza_def = {
        "inclusion_criteria": [
            {"type": "diagnosis", "code": {"system": "ICD-10", "code": "J1%"}}
        ]
    }
    _exclusion_def = {
        "exclusion_criteria": [
            {"type": "diagnosis", "code": {"system": "ICD-10", "code": "A90"}}
        ]
    }
    _mixed_def = {
        "inclusion_criteria": [
            {"type": "diagnosis", "code": {"system": "ICD-10", "code": "J1%"}}
        ],
        "exclusion_criteria": [
            {
                "type": "demographic_criteria",
                "attribute": "age",
                "operator": ">",
                "value": 60,
            }
        ],
    }

    def test_adds_boolean_column(self, fake_dataset, engine):
        labeled = engine.label(fake_dataset, {"dengue": self._dengue_def})
        assert "dengue" in labeled.columns
        assert labeled["dengue"].dtype == pl.Boolean

    def test_preserves_all_original_rows(self, fake_dataset, engine):
        labeled = engine.label(fake_dataset, {"dengue": self._dengue_def})
        assert labeled.height == fake_dataset.height

    def test_adds_one_column_per_definition(self, fake_dataset, engine):
        labeled = engine.label(
            fake_dataset,
            {
                "dengue": self._dengue_def,
                "influenza": self._influenza_def,
            },
        )
        assert "dengue" in labeled.columns
        assert "influenza" in labeled.columns
        assert labeled.height == fake_dataset.height

    def test_empty_definitions_returns_original(self, fake_dataset, engine):
        labeled = engine.label(fake_dataset, {})
        assert labeled.equals(fake_dataset)

    def test_no_criteria_marks_all_rows_true(self, fake_dataset, engine):
        labeled = engine.label(fake_dataset, {"everything": {}})
        assert labeled["everything"].all()

    def test_true_rows_match_run_inclusion_only(self, fake_dataset, engine):
        labeled = engine.label(fake_dataset, {"dengue": self._dengue_def})
        via_label = labeled.filter(pl.col("dengue")).drop("dengue")
        via_run = engine.run(fake_dataset, self._dengue_def)
        assert via_label.equals(via_run)

    def test_true_rows_match_run_exclusion_only(self, fake_dataset, engine):
        labeled = engine.label(fake_dataset, {"not_dengue": self._exclusion_def})
        via_label = labeled.filter(pl.col("not_dengue")).drop("not_dengue")
        via_run = engine.run(fake_dataset, self._exclusion_def)
        assert via_label.equals(via_run)

    def test_true_rows_match_run_inclusion_and_exclusion(self, fake_dataset, engine):
        labeled = engine.label(fake_dataset, {"influenza_young": self._mixed_def})
        via_label = labeled.filter(pl.col("influenza_young")).drop("influenza_young")
        via_run = engine.run(fake_dataset, self._mixed_def)
        assert via_label.equals(via_run)


class TestOSDEngine:
    def test_accepts_profile_data(self, profile):
        engine = OSDEngine(profile)
        assert engine.value_encodings == SEX_ENCODINGS

    def test_accepts_plain_column_list(self, all_columns):
        engine = OSDEngine(all_columns)
        assert engine.value_encodings == {}

    def test_skip_unresolvable_defaults_to_false(self, profile):
        engine = OSDEngine(profile)
        assert engine.skip_unresolvable is False

    def test_filters_by_diagnosis_code(self, fake_dataset, engine):
        osd = {
            "inclusion_criteria": [
                {
                    "type": "criterion",
                    "logical_operator": "OR",
                    "values": [
                        {
                            "type": "diagnosis",
                            "name": "Dengue",
                            "code": {"system": "ICD-10", "code": "A90"},
                        },
                        {
                            "type": "diagnosis",
                            "name": "Dengue haemorrhagic",
                            "code": {"system": "ICD-10", "code": "A91"},
                        },
                    ],
                }
            ]
        }
        result = engine.run(fake_dataset, osd)
        assert result.height > 0
        assert result["icd_code"].is_in(["A90", "A91"]).all()

    def test_filters_by_demographic(self, fake_dataset, engine):
        osd = {
            "inclusion_criteria": [
                {
                    "type": "demographic_criteria",
                    "attribute": "age",
                    "operator": ">=",
                    "value": 18,
                },
            ]
        }
        result = engine.run(fake_dataset, osd)
        assert (result["age"] >= 18).all()

    def test_canonical_sex_value_resolved_via_profile_encodings(
        self, fake_dataset, engine
    ):
        osd = {
            "inclusion_criteria": [
                {
                    "type": "demographic_criteria",
                    "attribute": "sex",
                    "operator": "==",
                    "value": "female",
                },
            ]
        }
        result = engine.run(fake_dataset, osd)
        assert result.height > 0
        assert (result["sex"] == "F").all()

    def test_no_criteria_returns_full_dataframe(self, fake_dataset, engine):
        assert engine.run(fake_dataset, {}).height == fake_dataset.height

    def test_multiple_top_level_criteria_are_implicitly_anded(
        self, fake_dataset, engine
    ):
        osd = {
            "inclusion_criteria": [
                {
                    "type": "demographic_criteria",
                    "attribute": "sex",
                    "operator": "==",
                    "value": "female",
                },
                {
                    "type": "demographic_criteria",
                    "attribute": "age",
                    "operator": ">",
                    "value": 60,
                },
            ]
        }
        result = engine.run(fake_dataset, osd)
        assert (result["sex"] == "F").all()
        assert (result["age"] > 60).all()

    def test_exclusion_removes_matching_rows(self, fake_dataset, engine):
        osd = {
            "exclusion_criteria": [
                {
                    "type": "demographic_criteria",
                    "attribute": "sex",
                    "operator": "==",
                    "value": "female",
                },
            ],
        }
        result = engine.run(fake_dataset, osd)
        assert (result["sex"] != "F").all()

    def test_inclusion_and_exclusion_combined(self, fake_dataset, engine):
        osd = {
            "inclusion_criteria": [
                {
                    "type": "demographic_criteria",
                    "attribute": "age",
                    "operator": ">=",
                    "value": 18,
                },
            ],
            "exclusion_criteria": [
                {
                    "type": "demographic_criteria",
                    "attribute": "sex",
                    "operator": "==",
                    "value": "female",
                },
            ],
        }
        result = engine.run(fake_dataset, osd)
        assert (result["age"] >= 18).all()
        assert (result["sex"] != "F").all()

    def test_only_exclusion_returns_subset_of_full_dataset(self, fake_dataset, engine):
        osd = {
            "exclusion_criteria": [
                {
                    "type": "demographic_criteria",
                    "attribute": "age",
                    "operator": "<",
                    "value": 18,
                },
            ]
        }
        result = engine.run(fake_dataset, osd)
        assert result.height < fake_dataset.height
        assert (result["age"] >= 18).all()

    # skip un-resolvable
    def test_skips_professional_judgment_and_applies_remaining(
        self, fake_dataset, profile
    ):
        engine = OSDEngine(profile, skip_unresolvable=True)
        osd = {
            "inclusion_criteria": [
                {"type": "professional_judgment", "name": "Clinical assessment"},
                {
                    "type": "demographic_criteria",
                    "attribute": "age",
                    "operator": ">",
                    "value": 60,
                },
            ]
        }
        result = engine.run(fake_dataset, osd)
        assert (result["age"] > 60).all()

    def test_all_skipped_criteria_returns_full_dataframe(self, fake_dataset, profile):
        engine = OSDEngine(profile, skip_unresolvable=True)
        osd = {
            "inclusion_criteria": [
                {"type": "professional_judgment", "name": "Clinical assessment"},
            ]
        }
        result = engine.run(fake_dataset, osd)
        assert result.height == fake_dataset.height

    def test_raises_by_default(self, fake_dataset, profile):
        engine = OSDEngine(profile)
        osd = {
            "inclusion_criteria": [
                {"type": "professional_judgment", "name": "Clinical assessment"},
            ]
        }
        with pytest.raises(UnresolvableCriterion):
            engine.run(fake_dataset, osd)
