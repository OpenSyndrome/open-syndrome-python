import pytest

from opensyndrome.mappers.sql import MappingError, sql_to_osd
from opensyndrome.schema import Criterion


def _diagnosis_mapping(col: str = "icd_code", system: str = "ICD-10") -> dict:
    return {
        "profiles": [
            {
                "name": "test",
                "columns": {col: {"concept": "diagnosis", "system": system}},
            }
        ]
    }


class TestEquality:
    def test_single_diagnosis_equality_emits_code_object(self):
        osd = sql_to_osd("icd_code = 'F10.0'", _diagnosis_mapping())

        assert osd["inclusion_criteria"] == [
            {
                "type": "diagnosis",
                "name": "F10.0",
                "code": {"system": "ICD-10", "code": "F10.0"},
            }
        ]


class TestOrOfEqualities:
    def test_two_equalities_become_flat_or_criterion(self):
        osd = sql_to_osd(
            "icd_code = 'F10.0' OR icd_code = 'T51.9'", _diagnosis_mapping()
        )

        assert osd["inclusion_criteria"] == [
            {
                "type": "criterion",
                "logical_operator": "OR",
                "name": "OR",
                "values": [
                    {
                        "type": "diagnosis",
                        "name": "F10.0",
                        "code": {"system": "ICD-10", "code": "F10.0"},
                    },
                    {
                        "type": "diagnosis",
                        "name": "T51.9",
                        "code": {"system": "ICD-10", "code": "T51.9"},
                    },
                ],
            }
        ]

    def test_three_chained_ors_become_one_flat_criterion(self):
        osd = sql_to_osd(
            "icd_code = 'A' OR icd_code = 'B' OR icd_code = 'C'",
            _diagnosis_mapping(),
        )

        (criterion,) = osd["inclusion_criteria"]
        assert criterion["logical_operator"] == "OR"
        assert [v["code"]["code"] for v in criterion["values"]] == ["A", "B", "C"]


class TestIn:
    def test_in_clause_emits_flat_or_of_diagnoses(self):
        osd = sql_to_osd("icd_code IN ('A90', 'A91', 'A92')", _diagnosis_mapping())

        (criterion,) = osd["inclusion_criteria"]
        assert criterion["logical_operator"] == "OR"
        assert [v["code"]["code"] for v in criterion["values"]] == ["A90", "A91", "A92"]

    def test_in_is_equivalent_to_chained_or(self):
        from_in = sql_to_osd("icd_code IN ('A', 'B')", _diagnosis_mapping())
        from_or = sql_to_osd("icd_code = 'A' OR icd_code = 'B'", _diagnosis_mapping())
        assert from_in["inclusion_criteria"] == from_or["inclusion_criteria"]


def _demographic_mapping() -> dict:
    return {
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


class TestNumericComparison:
    def test_greater_than_emits_attribute_operator_value(self):
        osd = sql_to_osd("age > 18", _demographic_mapping())

        assert osd["inclusion_criteria"] == [
            {
                "type": "demographic_criteria",
                "name": "age > 18",
                "attribute": "age",
                "operator": ">",
                "value": 18,
            }
        ]

    @pytest.mark.parametrize(
        "sql_op, json_op",
        [(">=", ">="), ("<", "<"), ("<=", "<="), ("=", "==")],
    )
    def test_all_numeric_operators(self, sql_op, json_op):
        osd = sql_to_osd(f"age {sql_op} 18", _demographic_mapping())
        (criterion,) = osd["inclusion_criteria"]
        assert criterion["operator"] == json_op
        assert criterion["value"] == 18

    def test_integer_dtype_casts_value_to_int(self):
        osd = sql_to_osd("age > 18", _demographic_mapping())
        (criterion,) = osd["inclusion_criteria"]
        assert isinstance(criterion["value"], int)


def _mixed_mapping() -> dict:
    return {
        "profiles": [
            {
                "name": "test",
                "columns": {
                    "icd_code": {"concept": "diagnosis", "system": "ICD-10"},
                    "age": {
                        "concept": "demographic_criteria",
                        "attribute": "age",
                        "dtype": "integer",
                    },
                },
            }
        ]
    }


class TestTopLevelNot:
    def test_not_around_equality_moves_to_exclusion(self):
        osd = sql_to_osd("NOT (icd_code = 'A90')", _diagnosis_mapping())

        assert "inclusion_criteria" not in osd or osd["inclusion_criteria"] == []
        assert osd["exclusion_criteria"] == [
            {
                "type": "diagnosis",
                "name": "A90",
                "code": {"system": "ICD-10", "code": "A90"},
            }
        ]

    def test_not_around_or_moves_whole_group_to_exclusion(self):
        osd = sql_to_osd("NOT (icd_code = 'A' OR icd_code = 'B')", _diagnosis_mapping())

        (criterion,) = osd["exclusion_criteria"]
        assert criterion["logical_operator"] == "OR"
        assert len(criterion["values"]) == 2


class TestAdvancedSqlConstructs:
    def test_quoted_identifier_maps_to_same_column(self):
        osd = sql_to_osd("\"icd_code\" = 'F10.0'", _diagnosis_mapping())
        (criterion,) = osd["inclusion_criteria"]
        assert criterion["code"]["code"] == "F10.0"

    def test_qualified_column_uses_column_name_part(self):
        osd = sql_to_osd("visits.icd_code = 'F10.0'", _diagnosis_mapping())
        (criterion,) = osd["inclusion_criteria"]
        assert criterion["code"]["code"] == "F10.0"

    def test_double_negation_is_rejected_with_clear_message(self):
        with pytest.raises(MappingError, match="Double negation"):
            sql_to_osd("NOT (NOT (icd_code = 'A'))", _diagnosis_mapping())

    def test_exists_subquery_raises(self):
        with pytest.raises(MappingError):
            sql_to_osd(
                "EXISTS (SELECT 1 FROM other WHERE x = 'y')", _diagnosis_mapping()
            )

    def test_cast_expression_raises(self):
        with pytest.raises(MappingError):
            sql_to_osd("CAST(age AS INT) > 18", _mixed_mapping())

    def test_arithmetic_in_where_raises(self):
        with pytest.raises(MappingError):
            sql_to_osd("age + 1 > 18", _mixed_mapping())

    def test_numeric_literal_without_dtype_is_int(self):
        mapping = {
            "profiles": [
                {
                    "name": "t",
                    "columns": {
                        "score": {
                            "concept": "demographic_criteria",
                            "attribute": "score",
                        },
                    },
                }
            ]
        }
        osd = sql_to_osd("score > 18", mapping)
        (criterion,) = osd["inclusion_criteria"]
        assert criterion["value"] == 18
        assert isinstance(criterion["value"], int)

    def test_float_literal_without_dtype_is_float(self):
        mapping = {
            "profiles": [
                {
                    "name": "t",
                    "columns": {
                        "score": {
                            "concept": "demographic_criteria",
                            "attribute": "score",
                        },
                    },
                }
            ]
        }
        osd = sql_to_osd("score > 18.5", mapping)
        (criterion,) = osd["inclusion_criteria"]
        assert criterion["value"] == 18.5
        assert isinstance(criterion["value"], float)


class TestDialectFlag:
    @pytest.mark.parametrize("dialect", ["postgres", "mysql"])
    def test_simple_equality_works_across_dialects(self, dialect):
        osd = sql_to_osd("icd_code = 'F10.0'", _diagnosis_mapping(), dialect=dialect)
        (criterion,) = osd["inclusion_criteria"]
        assert criterion["code"]["code"] == "F10.0"

    def test_postgres_and_mysql_produce_equivalent_output(self):
        sql = "icd_code IN ('A90', 'A91') AND age > 18"
        pg = sql_to_osd(sql, _mixed_mapping(), dialect="postgres")
        my = sql_to_osd(sql, _mixed_mapping(), dialect="mysql")
        assert pg == my


class TestProfileSelection:
    @staticmethod
    def _multi_profile_mapping() -> dict:
        return {
            "profiles": [
                {
                    "name": "nokeda",
                    "columns": {
                        "nokeda_icd": {"concept": "diagnosis", "system": "ICD-10"},
                    },
                },
                {
                    "name": "essence",
                    "columns": {
                        "discharge_dx": {"concept": "diagnosis", "system": "ICD-10"},
                    },
                },
            ]
        }

    def test_explicit_profile_is_used(self):
        osd = sql_to_osd(
            "discharge_dx = 'A90'",
            self._multi_profile_mapping(),
            profile="essence",
        )
        (criterion,) = osd["inclusion_criteria"]
        assert criterion["code"]["code"] == "A90"

    def test_explicit_profile_rejects_other_profile_columns(self):
        with pytest.raises(MappingError, match="nokeda_icd"):
            sql_to_osd(
                "nokeda_icd = 'A90'",
                self._multi_profile_mapping(),
                profile="essence",
            )

    def test_default_profile_is_first(self):
        osd = sql_to_osd("nokeda_icd = 'A90'", self._multi_profile_mapping())
        (criterion,) = osd["inclusion_criteria"]
        assert criterion["code"]["code"] == "A90"

    def test_unknown_profile_raises_key_error(self):
        with pytest.raises(KeyError):
            sql_to_osd(
                "nokeda_icd = 'A90'",
                self._multi_profile_mapping(),
                profile="missing",
            )


class TestRoundtripThroughEngine:
    @pytest.fixture
    def dataset(self):
        import polars as pl

        return pl.DataFrame(
            {
                "icd_code": ["F10.0", "T51.9", "A90", "F10.0", "X99", "T51.9"],
                "age": [25, 17, 60, 70, 8, 45],
                "sex": ["M", "F", "M", "F", "M", "F"],
            }
        )

    @staticmethod
    def _engine_mapping() -> dict:
        return {
            "profiles": [
                {
                    "name": "test",
                    "value_encodings": {"sex": {"male": "M", "female": "F"}},
                    "columns": {
                        "icd_code": {"concept": "diagnosis", "system": "ICD-10"},
                        "age": {
                            "concept": "demographic_criteria",
                            "attribute": "age",
                            "dtype": "integer",
                        },
                        "sex": {
                            "concept": "demographic_criteria",
                            "attribute": "sex",
                        },
                    },
                }
            ]
        }

    def _apply(self, dataset, sql):
        from opensyndrome.filter import OSDEngine, load_profile

        mapping = self._engine_mapping()
        profile = load_profile(mapping, "test")
        osd = sql_to_osd(sql, mapping)
        engine = OSDEngine(profile)
        return engine.filter(dataset, osd)

    def test_or_of_equalities_matches_sql_semantics(self, dataset):
        result = self._apply(dataset, "icd_code = 'F10.0' OR icd_code = 'T51.9'")
        assert result.height == 4
        assert set(result["icd_code"].to_list()) == {"F10.0", "T51.9"}

    def test_in_matches_sql_semantics(self, dataset):
        result = self._apply(dataset, "icd_code IN ('F10.0', 'T51.9')")
        assert result.height == 4

    def test_like_prefix_matches_sql_semantics(self, dataset):
        result = self._apply(dataset, "icd_code LIKE 'F1%'")
        assert result.height == 2
        assert (result["icd_code"] == "F10.0").all()

    def test_and_combines_filters(self, dataset):
        result = self._apply(dataset, "icd_code = 'F10.0' AND age > 30")
        assert result.height == 1
        assert result["age"].item() == 70

    def test_value_encoding_resolves_dataset_value(self, dataset):
        result = self._apply(dataset, "sex = 'F'")
        assert result.height == 3
        assert (result["sex"] == "F").all()

    def test_top_level_not_excludes_matching_rows(self, dataset):
        result = self._apply(dataset, "NOT (icd_code = 'F10.0')")
        assert result.height == 4
        assert "F10.0" not in result["icd_code"].to_list()


class TestSchemaValidation:
    @pytest.fixture
    def metadata(self):
        return {
            "title": "Acute alcohol intoxication",
            "scope": "specific",
            "version": "1.0.0",
            "location": "Berlin, Germany",
            "language": "English",
            "organization": "Robert Koch Institut",
        }

    def test_result_passes_machine_readable_format_validator(self, metadata):
        from opensyndrome.validators import validate_machine_readable_format

        osd = sql_to_osd(
            "icd_code = 'F10.0' OR icd_code = 'T51.9'",
            _diagnosis_mapping(),
            metadata=metadata,
        )
        validate_machine_readable_format(osd)

    def test_top_level_metadata_is_carried_through(self, metadata):
        osd = sql_to_osd("icd_code = 'F10.0'", _diagnosis_mapping(), metadata=metadata)
        for key, value in metadata.items():
            assert osd[key] == value

    def test_automatic_fields_are_stamped(self, metadata):
        osd = sql_to_osd("icd_code = 'F10.0'", _diagnosis_mapping(), metadata=metadata)
        assert osd["published_at"].endswith("Z")
        assert osd["status"] == "draft"
        assert osd["open_syndrome_version"] == "1.0.0"


class TestPydanticValidation:
    @pytest.mark.parametrize(
        "sql",
        [
            "icd_code = 'F10.0'",
            "icd_code = 'A' OR icd_code = 'B' OR icd_code = 'C'",
            "icd_code IN ('A', 'B')",
            "icd_code LIKE 'J18%'",
            "(icd_code = 'A' OR icd_code = 'B') AND icd_code = 'C'",
        ],
    )
    def test_diagnosis_only_results_are_valid_criteria(self, sql):
        osd = sql_to_osd(sql, _diagnosis_mapping())
        for criterion in osd["inclusion_criteria"]:
            Criterion.model_validate(criterion)

    def test_mixed_results_validate(self):
        osd = sql_to_osd("icd_code = 'A90' AND age > 18", _mixed_mapping())
        for criterion in osd["inclusion_criteria"]:
            Criterion.model_validate(criterion)

    def test_exclusion_from_not_validates(self):
        osd = sql_to_osd("NOT (icd_code = 'A')", _diagnosis_mapping())
        for criterion in osd["exclusion_criteria"]:
            Criterion.model_validate(criterion)


class TestErrors:
    def test_unmapped_column_raises_with_column_name(self):
        with pytest.raises(MappingError, match="unknown_col"):
            sql_to_osd("unknown_col = 'X'", _diagnosis_mapping())

    def test_is_null_raises(self):
        with pytest.raises(MappingError):
            sql_to_osd("icd_code IS NULL", _diagnosis_mapping())

    def test_is_not_null_raises(self):
        with pytest.raises(MappingError):
            sql_to_osd("icd_code IS NOT NULL", _diagnosis_mapping())

    def test_not_in_routes_to_exclusion(self):
        osd = sql_to_osd("icd_code NOT IN ('A', 'B')", _diagnosis_mapping())
        (criterion,) = osd["exclusion_criteria"]
        assert criterion["logical_operator"] == "OR"
        assert [v["code"]["code"] for v in criterion["values"]] == ["A", "B"]

    def test_subquery_raises(self):
        with pytest.raises(MappingError):
            sql_to_osd("icd_code IN (SELECT code FROM forbidden)", _diagnosis_mapping())

    def test_malformed_sql_wraps_parse_error(self):
        with pytest.raises(MappingError, match="parse"):
            sql_to_osd("icd_code === 'oops'", _diagnosis_mapping())

    def test_diagnosis_with_inequality_raises(self):
        with pytest.raises(MappingError, match="equality"):
            sql_to_osd("icd_code > 'A90'", _diagnosis_mapping())

    def test_empty_mapping_profiles_raises(self):
        with pytest.raises(MappingError, match="profiles"):
            sql_to_osd("icd_code = 'A'", {"profiles": []})

    def test_join_raises(self):
        mapping = {
            "profiles": [
                {
                    "name": "t",
                    "columns": {
                        "icd_code": {"concept": "diagnosis", "system": "ICD-10"},
                    },
                }
            ]
        }
        with pytest.raises(MappingError):
            sql_to_osd(
                "SELECT * FROM visits JOIN labs ON visits.id = labs.visit_id "
                "WHERE icd_code = 'A'",
                mapping,
            )


class TestNestedNotRejected:
    def test_not_inside_and_raises(self):
        with pytest.raises(MappingError, match="NOT"):
            sql_to_osd("(NOT icd_code = 'A') AND icd_code = 'B'", _diagnosis_mapping())

    def test_not_inside_or_raises(self):
        with pytest.raises(MappingError, match="NOT"):
            sql_to_osd("icd_code = 'A' OR NOT icd_code = 'B'", _diagnosis_mapping())


class TestValueEncodings:
    @staticmethod
    def _sex_mapping() -> dict:
        return {
            "profiles": [
                {
                    "name": "test",
                    "value_encodings": {"sex": {"male": "M", "female": "F"}},
                    "columns": {
                        "sex": {
                            "concept": "demographic_criteria",
                            "attribute": "sex",
                        },
                    },
                }
            ]
        }

    def test_dataset_value_is_reversed_to_canonical(self):
        osd = sql_to_osd("sex = 'M'", self._sex_mapping())
        (criterion,) = osd["inclusion_criteria"]
        assert criterion["value"] == "male"

    def test_value_without_encoding_passes_through(self):
        osd = sql_to_osd("sex = 'X'", self._sex_mapping())
        (criterion,) = osd["inclusion_criteria"]
        assert criterion["value"] == "X"

    def test_attribute_without_encoding_passes_through(self):
        mapping = {
            "profiles": [
                {
                    "name": "test",
                    "columns": {
                        "country": {
                            "concept": "demographic_criteria",
                            "attribute": "country",
                        },
                    },
                }
            ]
        }
        osd = sql_to_osd("country = 'BR'", mapping)
        (criterion,) = osd["inclusion_criteria"]
        assert criterion["value"] == "BR"


class TestFullSelectEquivalentToWhere:
    def test_select_with_where_produces_same_criteria(self):
        bare = sql_to_osd("icd_code = 'F10.0'", _diagnosis_mapping())
        full = sql_to_osd(
            "SELECT * FROM visits WHERE icd_code = 'F10.0'", _diagnosis_mapping()
        )
        assert bare["inclusion_criteria"] == full["inclusion_criteria"]

    def test_select_with_nested_where_produces_same_criteria(self):
        bare = sql_to_osd("icd_code = 'A' OR icd_code = 'B'", _diagnosis_mapping())
        full = sql_to_osd(
            "SELECT * FROM visits WHERE icd_code = 'A' OR icd_code = 'B'",
            _diagnosis_mapping(),
        )
        assert bare["inclusion_criteria"] == full["inclusion_criteria"]

    def test_select_without_where_raises(self):
        with pytest.raises(MappingError, match="WHERE"):
            sql_to_osd("SELECT * FROM visits", _diagnosis_mapping())


class TestMixedConcepts:
    def test_diagnosis_and_demographic_combined(self):
        osd = sql_to_osd("icd_code = 'A90' AND age > 18", _mixed_mapping())

        (outer,) = osd["inclusion_criteria"]
        assert outer["logical_operator"] == "AND"
        diagnosis_child, age_child = outer["values"]
        assert diagnosis_child["type"] == "diagnosis"
        assert diagnosis_child["code"]["code"] == "A90"
        assert age_child["type"] == "demographic_criteria"
        assert age_child["attribute"] == "age"
        assert age_child["value"] == 18


class TestBooleanLiteral:
    @staticmethod
    def _bool_mapping() -> dict:
        return {
            "profiles": [
                {
                    "name": "test",
                    "columns": {
                        "ari_flag": {
                            "concept": "diagnostic_test",
                            "attribute": "ari_flag",
                            "dtype": "boolean",
                        },
                    },
                }
            ]
        }

    def test_true_literal_emits_boolean_value(self):
        osd = sql_to_osd("ari_flag = TRUE", self._bool_mapping())
        (criterion,) = osd["inclusion_criteria"]
        assert criterion["value"] is True
        assert criterion["operator"] == "=="

    def test_false_literal_emits_boolean_value(self):
        osd = sql_to_osd("ari_flag = FALSE", self._bool_mapping())
        (criterion,) = osd["inclusion_criteria"]
        assert criterion["value"] is False


class TestBetween:
    def test_between_becomes_and_of_two_comparisons(self):
        osd = sql_to_osd("age BETWEEN 18 AND 65", _demographic_mapping())

        (criterion,) = osd["inclusion_criteria"]
        assert criterion["logical_operator"] == "AND"
        assert len(criterion["values"]) == 2

        low, high = criterion["values"]
        assert (
            low["attribute"] == "age" and low["operator"] == ">=" and low["value"] == 18
        )
        assert (
            high["attribute"] == "age"
            and high["operator"] == "<="
            and high["value"] == 65
        )


class TestLikePrefix:
    def test_like_with_percent_passes_pattern_into_code(self):
        osd = sql_to_osd("icd_code LIKE 'J18%'", _diagnosis_mapping())

        assert osd["inclusion_criteria"] == [
            {
                "type": "diagnosis",
                "name": "J18%",
                "code": {"system": "ICD-10", "code": "J18%"},
            }
        ]

    def test_like_with_no_wildcard_is_still_emitted_as_code(self):
        osd = sql_to_osd("icd_code LIKE 'J18'", _diagnosis_mapping())
        (criterion,) = osd["inclusion_criteria"]
        assert criterion["code"]["code"] == "J18"


class TestAndOrNesting:
    def test_parens_wrap_or_inside_and(self):
        osd = sql_to_osd(
            "(icd_code = 'A' OR icd_code = 'B') AND icd_code = 'C'",
            _diagnosis_mapping(),
        )

        (outer,) = osd["inclusion_criteria"]
        assert outer["logical_operator"] == "AND"
        assert len(outer["values"]) == 2
        inner_or, c_leaf = outer["values"]
        assert inner_or["logical_operator"] == "OR"
        assert [v["code"]["code"] for v in inner_or["values"]] == ["A", "B"]
        assert c_leaf["code"]["code"] == "C"

    def test_sql_precedence_and_binds_tighter_than_or(self):
        osd = sql_to_osd(
            "icd_code = 'A' OR icd_code = 'B' AND icd_code = 'C'",
            _diagnosis_mapping(),
        )

        (outer,) = osd["inclusion_criteria"]
        assert outer["logical_operator"] == "OR"
        a_leaf, inner_and = outer["values"]
        assert a_leaf["code"]["code"] == "A"
        assert inner_and["logical_operator"] == "AND"
        assert [v["code"]["code"] for v in inner_and["values"]] == ["B", "C"]
