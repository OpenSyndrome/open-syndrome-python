import json
from functools import reduce
from pathlib import Path
import polars as pl


DEFINITIONS_DIR = Path("tests/definitions/")


def load_definition(definition_filename, version="v1"):
    letter_dir = definition_filename[0].lower()
    return json.loads(
        (
            DEFINITIONS_DIR / f"{version}/{letter_dir}/{definition_filename}.json"
        ).read_text()
    )


def overlap_definitions(definitions):
    if len(definitions) < 2:
        return
    definition_codes = {}
    for definition in definitions:
        json_definition = load_definition(definition)
        inclusion_criteria = json_definition.get("inclusion_criteria", [])
        if inclusion_criteria:
            criterion = inclusion_criteria[0]
            definition_codes[definition] = set()
            for value in criterion["values"]:
                if value.get("code"):
                    definition_codes[definition].add(
                        value["code"]["code"].replace(".", "").upper()
                    )
    in_common_codes = reduce(lambda acc, cond: acc & cond, definition_codes.values())
    return in_common_codes


def filter_cases_per_definitions(df, mapping, definitions):
    _df_filtered = df
    for definition in definitions:
        _df_filtered = filter_cases(_df_filtered, mapping, definition)
    return _df_filtered


def find_cases_from(term, version="v1"):  # TODO rename
    definitions = []
    for file_ in (DEFINITIONS_DIR / version).glob("**/*.json"):
        if term.lower() in file_.name.lower():
            definitions.append(file_.name.replace(".json", ""))
    return definitions


def filter_cases(df, mapping, definition_filename, version="v1"):
    """Filter records in a DataFrame based on a definition file.

    The logical operator is not taking into account because the rows are seeing as independent.
    A new column is added to the DataFrame with the name of the definition file.
    """
    definition = load_definition(definition_filename, version)
    inclusion_criteria = definition.get("inclusion_criteria", [])
    # TODO add exclusion criteria
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
        print("Filtering records based on the following codes:")
        for system, codes in wanted_codes_per_system.items():
            for column in mapping:
                if column["system"] == system:
                    print(column["system"], codes)
                    regex_code = []
                    for code in codes:
                        if "%" in code:
                            # handle LIKE wildcard
                            regex_code.append(code.replace("%", ".*"))
                        else:
                            regex_code.append(f"{code}$")  # mark the end of the string
                    regex_code = "|".join(regex_code)
                    all_filters.append(pl.col(column["code"]).str.contains(regex_code))

        # FIXME show error if no filters are created all_filters == []
        combined_filter = reduce(lambda acc, cond: acc | cond, all_filters)
        return df.with_columns(combined_filter.alias(definition_filename))
    return df
