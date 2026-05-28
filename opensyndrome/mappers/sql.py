from typing import Any

import sqlglot
from sqlglot import expressions as exp

from opensyndrome.filter import ColumnSpec, ProfileData, load_profile
from opensyndrome.metadata import fill_automatic_fields
from opensyndrome.schema import (
    Code,
    Criterion,
    LogicalOperator,
    Operator,
    Type,
)


class MappingError(Exception):
    """SQL fragment cannot be mapped to an OSD criterion."""


_LiteralValue = str | int | float | bool | None

_DTYPE_CASTS: dict[str, type] = {
    "integer": int,
    "float": float,
    "number": float,
}

_ATTRIBUTE_CONCEPTS: set[str] = {
    Type.demographic_criteria.value,
    Type.diagnostic_test.value,
}

_COMPARISON_OPERATORS: dict[type[exp.Expression], Operator] = {
    exp.EQ: Operator("=="),
    exp.GT: Operator(">"),
    exp.GTE: Operator(">="),
    exp.LT: Operator("<"),
    exp.LTE: Operator("<="),
    exp.NEQ: Operator("!="),
}


def _strip_parens(node: exp.Expression) -> exp.Expression:
    while isinstance(node, exp.Paren):
        node = node.this
    return node


def _resolve_profile(mapping: dict[str, Any], profile: str | None) -> ProfileData:
    profiles = mapping.get("profiles", [])
    if not profiles:
        raise MappingError("Mapping has no 'profiles' entries.")
    name = profile if profile is not None else profiles[0]["name"]
    return load_profile(mapping, name)


def _column_for(name: str, columns: list[ColumnSpec]) -> ColumnSpec:
    for col in columns:
        if col.col_name == name:
            return col
    raise MappingError(f"Column '{name}' is not mapped in the profile.")


def _literal_value(node: exp.Expression) -> _LiteralValue:
    if isinstance(node, exp.Boolean):
        return bool(node.this)
    if isinstance(node, exp.Null):
        return None
    if isinstance(node, exp.Literal):
        text = node.name
        if node.is_string:
            return text
        try:
            return int(text)
        except ValueError:
            return float(text)
    raise MappingError(f"Unsupported literal: {node.sql()}")


def _cast_value(value: _LiteralValue, dtype: str) -> _LiteralValue:
    cast = _DTYPE_CASTS.get(dtype)
    return cast(value) if cast and not isinstance(value, bool) else value


def _reverse_encode(
    value: _LiteralValue,
    attribute: str | None,
    value_encodings: dict[str, dict[str, str]],
) -> _LiteralValue:
    if attribute is None:
        return value
    for canonical, dataset_value in value_encodings.get(attribute, {}).items():
        if str(dataset_value) == str(value):
            return canonical
    return value


def _diagnosis_criterion(spec: ColumnSpec, code: str) -> Criterion:
    if not code:
        raise MappingError(
            f"Empty diagnosis code is not allowed for column '{spec.col_name}'."
        )
    return Criterion(
        type=Type.diagnosis,
        name=code,
        code=Code(system=spec.system or "", code=code),
    )


def _attribute_criterion(
    spec: ColumnSpec, operator: Operator, raw_value: _LiteralValue, profile: ProfileData
) -> Criterion:
    casted = _cast_value(raw_value, spec.dtype)
    value = _reverse_encode(casted, spec.attribute, profile.value_encodings)
    return Criterion(
        type=Type(spec.concept),
        name=f"{spec.attribute} {operator.value} {raw_value}",
        attribute=spec.attribute,
        operator=operator,
        value=value,
    )


def _comparison_to_criterion(
    left: exp.Expression,
    right: exp.Expression,
    operator: Operator,
    profile: ProfileData,
) -> Criterion:
    if not isinstance(left, exp.Column):
        raise MappingError(f"Left side must be a column: {left.sql()}")
    spec = _column_for(left.name, profile.columns)
    raw_value = _literal_value(right)

    if spec.concept == Type.diagnosis.value:
        if operator is not Operator("=="):
            raise MappingError(
                f"Diagnosis columns only support equality, got '{operator.value}' "
                f"in {left.sql()} {operator.value} {right.sql()}."
            )
        if not isinstance(raw_value, str):
            raise MappingError(
                f"Diagnosis code must be a string literal, got {raw_value!r} "
                f"in {left.sql()} = {right.sql()}."
            )
        return _diagnosis_criterion(spec, raw_value)

    if spec.concept in _ATTRIBUTE_CONCEPTS:
        return _attribute_criterion(spec, operator, raw_value, profile)

    raise MappingError(
        f"Concept '{spec.concept}' is not yet supported (column '{spec.col_name}')."
    )


def _criterion_group(operator: LogicalOperator, children: list[Criterion]) -> Criterion:
    return Criterion(
        type=Type.criterion,
        name=operator.value,
        logical_operator=operator,
        values=children,
    )


def _in_to_criterion(node: exp.In, profile: ProfileData) -> Criterion:
    left = node.this
    expressions = node.expressions
    if not expressions:
        raise MappingError(f"IN without literal values: {node.sql()}")
    non_literals = [
        e
        for e in expressions
        if not isinstance(e, (exp.Literal, exp.Boolean, exp.Null))
    ]
    if non_literals:
        raise MappingError(
            f"IN list must contain only literal values, got "
            f"{', '.join(e.sql() for e in non_literals)} in {node.sql()}."
        )
    children = [
        _comparison_to_criterion(left, lit, Operator("=="), profile)
        for lit in expressions
    ]
    if len(children) == 1:
        return children[0]
    return _criterion_group(LogicalOperator.OR, children)


def _like_to_criterion(node: exp.Like, profile: ProfileData) -> Criterion:
    left = node.this
    if not isinstance(left, exp.Column):
        raise MappingError(f"LIKE left side must be a column: {node.sql()}")
    spec = _column_for(left.name, profile.columns)
    if spec.concept != Type.diagnosis.value:
        raise MappingError(
            f"LIKE is only supported on 'diagnosis' columns, got "
            f"'{spec.concept}' in {node.sql()}."
        )
    pattern = _literal_value(node.expression)
    if not isinstance(pattern, str):
        raise MappingError(f"LIKE pattern must be a string literal: {node.sql()}")
    return _diagnosis_criterion(spec, pattern)


def _between_to_criterion(node: exp.Between, profile: ProfileData) -> Criterion:
    column = node.this
    low = _comparison_to_criterion(column, node.args["low"], Operator(">="), profile)
    high = _comparison_to_criterion(column, node.args["high"], Operator("<="), profile)
    return _criterion_group(LogicalOperator.AND, [low, high])


def _connector(
    node: exp.Connector, operator: LogicalOperator, profile: ProfileData
) -> Criterion:
    children = [_translate(child, profile) for child in node.flatten()]
    return _criterion_group(operator, children)


def _translate(node: exp.Expression, profile: ProfileData) -> Criterion:
    match node:
        case exp.EQ() | exp.GT() | exp.GTE() | exp.LT() | exp.LTE() | exp.NEQ():
            operator = _COMPARISON_OPERATORS[type(node)]
            return _comparison_to_criterion(
                node.this, node.expression, operator, profile
            )
        case exp.Or():
            return _connector(node, LogicalOperator.OR, profile)
        case exp.And():
            return _connector(node, LogicalOperator.AND, profile)
        case exp.In():
            return _in_to_criterion(node, profile)
        case exp.Like():
            return _like_to_criterion(node, profile)
        case exp.Between():
            return _between_to_criterion(node, profile)
        case exp.Not():
            raise MappingError(
                f"Nested NOT is not supported (only top-level NOT becomes "
                f"exclusion_criteria): {node.sql()}"
            )
        case exp.Is():
            raise MappingError(f"IS NULL / IS NOT NULL is not supported: {node.sql()}")
        case _:
            raise MappingError(
                f"Unsupported SQL construct {type(node).__name__}: {node.sql()}"
            )


def sql_to_osd(
    sql_text: str,
    mapping: dict[str, Any],
    *,
    profile: str | None = None,
    metadata: dict[str, Any] | None = None,
    dialect: str = "postgres",
) -> dict[str, Any]:
    """Convert a SQL fragment to an OSD JSON definition.

    The fragment may be a full ``SELECT ... WHERE ...`` query or a bare boolean
    expression (the WHERE body). Columns referenced in the SQL must be present
    in the chosen mapping profile. The result always carries placeholder values
    for every required top-level field; supply ``metadata`` with at least
    ``title``, ``scope``, ``version``, ``location``, ``language``, and
    ``organization`` to produce a definition that passes schema validation.
    """
    profile_data = _resolve_profile(mapping, profile)
    try:
        ast = sqlglot.parse_one(sql_text, dialect=dialect)
    except sqlglot.errors.ParseError as exc:
        raise MappingError(f"Could not parse SQL {sql_text!r}: {exc}") from exc

    if isinstance(ast, exp.Select):
        if ast.args.get("joins"):
            raise MappingError(f"JOIN clauses are not supported: {sql_text!r}")
        where = ast.args.get("where")
        if where is None:
            raise MappingError(f"SELECT statement has no WHERE clause: {sql_text!r}")
        ast = where.this

    ast = _strip_parens(ast)

    if isinstance(ast, exp.Not):
        inner = _strip_parens(ast.this)
        if isinstance(inner, exp.Not):
            raise MappingError(f"Double negation is not supported: {sql_text!r}")
        criterion = _translate(inner, profile_data)
        inclusion, exclusion = [], [criterion]
    else:
        inclusion, exclusion = [_translate(ast, profile_data)], []

    definition: dict[str, Any] = {
        "inclusion_criteria": [
            c.model_dump(by_alias=True, exclude_none=True, mode="json")
            for c in inclusion
        ]
    }
    if exclusion:
        definition["exclusion_criteria"] = [
            c.model_dump(by_alias=True, exclude_none=True, mode="json")
            for c in exclusion
        ]

    return fill_automatic_fields({**(metadata or {}), **definition}, sql_text)
