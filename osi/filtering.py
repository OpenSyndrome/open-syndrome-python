import json
from functools import reduce
from pathlib import Path
import polars as pl


def load_definition(definition_filename, version="v1"):
    return json.loads(
        Path(f"tests/definitions/{version}/a/{definition_filename}.json").read_text()
    )


def filter_cases(df, mapping, definition_filename, version="v1"):
    """Filter records in a DataFrame based on a definition file.

    The condition is not taking into account and it behaves as if the logical operator is 'OR'.
    """
    definition = load_definition(definition_filename, version)
    inclusion_criteria = definition.get("inclusion_criteria", [])
    if inclusion_criteria:
        criterion = inclusion_criteria[0]
        wanted_codes_per_system = {}
        for value in criterion["values"]:
            if value.get("code"):
                target_code = value["code"]["code"]
                system = value["code"]["system"]
                wanted_codes_per_system.setdefault(system, [])
                wanted_codes_per_system[system].append(target_code)

        all_filters = []
        for system, codes in wanted_codes_per_system.items():
            for column in mapping:
                if column["system"] == system:
                    print(column["code"], codes)
                    all_filters.append(pl.col(column["code"]).is_in(codes))

        combined_filter = reduce(lambda acc, cond: acc | cond, all_filters)
        return df.filter(combined_filter)
    return df
