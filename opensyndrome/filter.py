from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


_VALID_CONCEPTS = frozenset(
    {
        "diagnosis",
        "demographic_criteria",
        "diagnostic_test",
        "symptom",
        "epidemiological_history",
    }
)


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
