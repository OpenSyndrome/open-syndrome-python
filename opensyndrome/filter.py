from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import polars as pl


_VALID_CONCEPTS = frozenset(
    {
        "diagnosis",
        "demographic_criteria",
        "diagnostic_test",
        "symptom",
        "epidemiological_history",
    }
)

_DTYPE_MAP: dict[str, type[pl.DataType]] = {
    "integer": pl.Int64,
    "float": pl.Float64,
    "string": pl.String,
    "boolean": pl.Boolean,
    "date": pl.Date,
    "datetime": pl.Datetime,
}

_OPERATOR_MAP = {
    ">": lambda expr, val: expr > val,
    ">=": lambda expr, val: expr >= val,
    "<": lambda expr, val: expr < val,
    "<=": lambda expr, val: expr <= val,
    "==": lambda expr, val: expr == val,
    "!=": lambda expr, val: expr != val,
}


class InvalidOperator(Exception):
    pass


class UnresolvableCriterion(Exception):
    pass


@dataclass
class ColumnSpec:
    """Typed descriptor for a single dataset column.

    Attributes
    ----------
    col_name:
        Name of the column in the DataFrame.
    concept:
        OSD concept type this column represents.
    dtype:
        Logical data type used for comparisons. One of: ``integer``, ``float``,
        ``string``, ``boolean``, ``date``, ``datetime``. Defaults to ``string``.
    attribute:
        OSD attribute name (e.g. ``"age"``, ``"sex"``). Required for
        ``demographic_criteria`` and ``diagnostic_test`` columns.
    system:
        Coding system identifier (e.g. ``"ICD-10"``, ``"CID-10"``). Optional,
        reserved for future use (e.g. punctuation-tolerant matching per system).
        Not used for column selection — all ``diagnosis`` columns receive all
        code criteria regardless of system.
    """

    col_name: str
    concept: str
    dtype: str = "string"
    attribute: str | None = None
    system: str | None = None

    def __post_init__(self) -> None:
        if self.concept not in _VALID_CONCEPTS:
            raise ValueError(
                f"Column '{self.col_name}': unknown concept '{self.concept}'. "
                f"Valid options: {', '.join(sorted(_VALID_CONCEPTS))}."
            )
        if self.concept == "demographic_criteria" and not self.attribute:
            raise ValueError(
                f"Column '{self.col_name}' has concept 'demographic_criteria' "
                "but no 'attribute' was specified."
            )

    @classmethod
    def from_dict(cls, col_name: str, spec: dict[str, Any]) -> ColumnSpec:
        return cls(
            col_name=col_name,
            concept=spec["concept"],
            dtype=spec.get("dtype", "string"),
            attribute=spec.get("attribute"),
            system=spec.get("system"),
        )


@dataclass
class ProfileData:
    """Result of loading a mapping profile.

    Attributes
    ----------
    columns:
        Column descriptors for the profile.
    value_encodings:
        Maps attribute name → {canonical_value: dataset_value}.
        E.g. ``{"sex": {"male": "M", "female": "F"}}``.
    """

    columns: list[ColumnSpec]
    value_encodings: dict[str, dict[str, str]] = field(default_factory=dict)


def load_profile(yaml_data: dict, profile_name: str) -> ProfileData:
    """Load a named profile from parsed YAML data.

    Parameters
    ----------
    yaml_data:
        Parsed content of the mapping YAML file.
    profile_name:
        Name of the profile to load.

    Returns
    -------
    ProfileData
        Column specs and value encodings for the profile.

    Raises
    ------
    KeyError
        If the profile name is not found.
    """
    for profile in yaml_data.get("profiles", []):
        if profile["name"] == profile_name:
            columns = [
                ColumnSpec.from_dict(col_name, spec)
                for col_name, spec in profile.get("columns", {}).items()
            ]
            return ProfileData(
                columns=columns,
                value_encodings=profile.get("value_encodings", {}),
            )
    raise KeyError(f"Profile '{profile_name}' not found in mapping.")


def _cast(
    expr: pl.Expr, col_name: str, dtype_str: str, df_schema: dict[str, pl.DataType]
) -> pl.Expr:
    """Cast *expr* to the target dtype, skipping if the column is already compatible.

    Uses Polars dtype predicates (``.is_integer()``, ``.is_float()``) so that any
    integer width (Int8 … UInt64) is accepted for ``dtype: integer``, and any float
    width for ``dtype: float``, avoiding unnecessary widening casts.
    """
    target = _DTYPE_MAP.get(dtype_str)
    if target is None:
        return expr

    current = df_schema.get(col_name)
    if current is not None:
        if dtype_str == "integer" and current.is_integer():
            return expr
        if dtype_str == "float" and current.is_float():
            return expr
        if current == target:
            return expr

    return expr.cast(target)


def _code_to_regex(code: str) -> str:
    """Convert an OSD code to a regex pattern.

    - ``%`` wildcard → ``.*`` (e.g. ``J1%`` → ``^J1.*$``)
    - Exact code → anchored to avoid prefix collisions
      (e.g. ``A90`` matches ``A90`` and ``A90.1`` but not ``A900``)
    """
    if "%" in code:
        return f"^{code.replace('%', '.*')}$"
    # Allow optional sub-code suffix (dot-separated), e.g. A90.1
    return f"^{code}(\\..+)?$"


def _apply_flags(pattern: str, flags: str) -> str:
    """Prepend inline regex flags (e.g. ``(?i)``) to *pattern*."""
    inline = "".join(f"(?{f})" for f in flags if f in "imsxy")
    return f"{inline}{pattern}" if inline else pattern


def _build_code_expr(criterion: dict, columns: list[ColumnSpec]) -> pl.Expr:
    """Build a Polars expression matching a diagnosis criterion with a ``code`` object.

    Applies the code pattern to **all** ``diagnosis`` columns. The ``code.system``
    field in the definition is informational only and does not affect column selection.

    Values in the column are stripped of surrounding whitespace before matching,
    to handle data quality issues like ``"A90 "``.
    """
    raw_code = criterion["code"]["code"]
    pattern = _code_to_regex(raw_code)

    matching_cols = [c for c in columns if c.concept == "diagnosis"]
    if not matching_cols:
        raise UnresolvableCriterion("No column mapped to concept 'diagnosis'.")

    exprs = [
        pl.col(c.col_name).str.strip_chars().str.contains(pattern)
        for c in matching_cols
    ]
    return pl.any_horizontal(exprs)


def _build_text_expr(
    criterion: dict, columns: list[ColumnSpec], concept: str
) -> pl.Expr:
    """Build a Polars expression for free-text matching (symptom, epidemiological_history, etc.).

    Uses ``regex_pattern`` if present, otherwise falls back to ``name``.
    Supports ``regex_flags`` (e.g. ``"i"`` for case-insensitive).
    Searches all columns mapped to the given concept and combines with OR.
    """
    pattern = criterion.get("regex_pattern") or criterion.get("name", "")
    pattern = _apply_flags(pattern, criterion.get("regex_flags", ""))

    matching_cols = [c for c in columns if c.concept == concept]
    if not matching_cols:
        raise UnresolvableCriterion(f"No column mapped to concept '{concept}'.")

    exprs = [
        pl.col(c.col_name).str.contains(pattern, literal=False) for c in matching_cols
    ]
    return pl.any_horizontal(exprs)


def _build_attr_expr(
    criterion: dict,
    columns: list[ColumnSpec],
    value_encodings: dict[str, dict[str, str]] | None = None,
    df_schema: dict[str, pl.DataType] | None = None,
) -> pl.Expr:
    """Build a Polars expression for a demographic or diagnostic-test criterion.

    Looks up the column by ``criterion["attribute"]``, applies the operator, and
    optionally translates the value through *value_encodings*.
    """
    attribute = criterion.get("attribute")
    operator = criterion.get("operator")
    value = criterion.get("value")

    matching = [c for c in columns if c.attribute == attribute]
    if not matching:
        raise UnresolvableCriterion(f"No column mapped to attribute '{attribute}'.")
    spec = matching[0]

    if operator == "regex":
        pattern = _apply_flags(
            criterion.get("regex_pattern") or str(value),
            criterion.get("regex_flags", ""),
        )
        return pl.col(spec.col_name).str.contains(pattern, literal=False)

    if operator not in _OPERATOR_MAP:
        raise InvalidOperator(
            f"Unsupported operator '{operator}'. "
            f"Valid options: {', '.join(_OPERATOR_MAP)}, regex"
        )

    if value_encodings and attribute and isinstance(value, str):
        value = value_encodings.get(attribute, {}).get(value, value)

    expr = _cast(pl.col(spec.col_name), spec.col_name, spec.dtype, df_schema or {})
    return _OPERATOR_MAP[operator](expr, value)


def _combine(
    exprs: list[pl.Expr], logical_operator: str | None, n: int | None
) -> pl.Expr:
    if not exprs:
        raise UnresolvableCriterion("Cannot combine an empty list of expressions.")

    op = (logical_operator or "AND").upper().strip()

    if op == "AND":
        return pl.all_horizontal(exprs)
    if op == "OR":
        return pl.any_horizontal(exprs)
    if op == "AT_LEAST":
        if n is None:
            raise InvalidOperator(
                "AT_LEAST requires 'logical_operator_arguments' to specify n."
            )
        return pl.sum_horizontal(exprs) >= n
    raise InvalidOperator(
        f"Invalid operator '{logical_operator}'. Valid options are: AND, OR, AT_LEAST"
    )


def _parse_criterion(
    criterion: dict,
    columns: list[ColumnSpec],
    value_encodings: dict[str, dict[str, str]] | None = None,
    df_schema: dict[str, pl.DataType] | None = None,
) -> pl.Expr:
    ctype = criterion.get("type")

    if ctype is None:
        raise UnresolvableCriterion("Criterion is missing the required 'type' field.")

    if ctype == "criterion":
        sub_exprs = [
            _parse_criterion(c, columns, value_encodings, df_schema)
            for c in criterion.get("values", [])
        ]
        logical_operator = criterion.get("logical_operator", "AND")
        n_args = criterion.get("logical_operator_arguments")
        n = n_args[0] if n_args else None
        return _combine(sub_exprs, logical_operator, n)

    if ctype == "diagnosis":
        if "code" in criterion:
            return _build_code_expr(criterion, columns)
        return _build_text_expr(criterion, columns, "diagnosis")

    if ctype == "demographic_criteria":
        return _build_attr_expr(criterion, columns, value_encodings, df_schema)

    # symptom, diagnostic_test, epidemiological_history:
    # if the criterion carries attribute + operator, treat it as a measurable attribute
    # (e.g. body_temperature >= 39); otherwise match by name/regex against text columns.
    if ctype in ("symptom", "diagnostic_test", "epidemiological_history"):
        if "attribute" in criterion and "operator" in criterion:
            return _build_attr_expr(criterion, columns, value_encodings, df_schema)
        return _build_text_expr(criterion, columns, ctype)

    if ctype == "syndrome":
        raise UnresolvableCriterion(
            "Criterion type 'syndrome' (cross-definition reference) is not yet supported."
        )

    if ctype == "professional_judgment":
        raise UnresolvableCriterion(
            "Criterion type 'professional_judgment' cannot be evaluated against structured data."
        )

    raise UnresolvableCriterion(f"Unknown criterion type: '{ctype}'.")


class OSDEngine:
    """Compile an OSD definition into Polars filter expressions and apply them.

    Parameters
    ----------
    profile:
        A :class:`ProfileData` instance (from :func:`load_profile`), or a plain
        list of :class:`ColumnSpec` objects when no value encodings are needed.
    skip_unresolvable:
        When ``True``, criteria that cannot be evaluated against structured data
        (``professional_judgment``, ``syndrome``) are silently skipped instead of
        raising :exc:`UnresolvableCriterion`. Useful when definitions mix
        computational and non-computational criteria.
    """

    def __init__(
        self,
        profile: ProfileData | list[ColumnSpec],
        *,
        skip_unresolvable: bool = False,
    ) -> None:
        if isinstance(profile, ProfileData):
            self.columns = profile.columns
            self.value_encodings = profile.value_encodings
        else:
            self.columns = profile
            self.value_encodings = {}
        self.skip_unresolvable = skip_unresolvable

    def _safe_parse(
        self,
        criterion: dict,
        df_schema: dict[str, pl.DataType],
    ) -> pl.Expr | None:
        try:
            return _parse_criterion(
                criterion, self.columns, self.value_encodings, df_schema
            )
        except UnresolvableCriterion:
            if self.skip_unresolvable:
                return None
            raise

    def _compile(
        self,
        criteria: list[dict],
        df_schema: dict[str, pl.DataType],
    ) -> pl.Expr | None:
        """Compile a list of top-level criteria into a single AND expression."""
        exprs = [
            e for c in criteria if (e := self._safe_parse(c, df_schema)) is not None
        ]
        if not exprs:
            return None
        return pl.all_horizontal(exprs)

    @staticmethod
    def display_expression(exprs):
        """Display expression tree."""
        exprs.meta.tree_format()

    def run(self, df: pl.DataFrame, osd_definition: dict) -> pl.DataFrame:
        """Filter *df* according to *osd_definition* inclusion and exclusion criteria.

        Rows must satisfy all inclusion criteria AND fail all exclusion criteria.
        If only exclusion criteria are present, all non-excluded rows are returned.
        If neither is present, *df* is returned unchanged.

        Parameters
        ----------
        df:
            The dataset to filter.
        osd_definition:
            Parsed OSD JSON definition dict.

        Returns
        -------
        pl.DataFrame
            Filtered DataFrame.
        """
        schema = dict(df.schema)
        inclusion_expr = self._compile(
            osd_definition.get("inclusion_criteria", []), schema
        )
        exclusion_expr = self._compile(
            osd_definition.get("exclusion_criteria", []), schema
        )

        if inclusion_expr is None and exclusion_expr is None:
            return df

        final_expr = inclusion_expr
        if exclusion_expr is not None:
            negated = ~exclusion_expr
            final_expr = negated if final_expr is None else final_expr & negated

        return df.filter(final_expr)
