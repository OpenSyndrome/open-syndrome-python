import logging

import requests

logger = logging.getLogger(__name__)

OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"
OPENSYNDROME_CONTEXT_URL = "https://opensyndrome.org/schema/v1/context.jsonld"
SKIP_TYPES = {"criterion", "demographic_criteria"}
MIN_SCORE = 5.0

CRITERION_TYPE_ONTOLOGIES = {
    "symptom": ["mondo", "hp"],
    "diagnosis": ["mondo", "efo"],
    "syndrome": ["mondo", "efo"],
    "diagnostic_test": ["loinc", "obi"],
    "epidemiological_history": ["hp", "efo"],
    "professional_judgment": ["hp", "efo"],
}


def _pick_best(docs: list[dict], name: str) -> str | None:
    for doc in docs:
        if doc.get("label", "").lower() == name.lower():
            return doc["short_form"].replace("_", ":", 1)
    for doc in docs:
        score = doc.get("score")
        if score is not None and float(score) >= MIN_SCORE:
            return doc["short_form"].replace("_", ":", 1)
    return None


def _search_ols(name: str, ontologies: list[str], timeout: int = 10) -> str | None:
    base_params = {"ontology": ",".join(ontologies), "rows": 5, "type": "class"}
    try:
        response = requests.get(
            OLS4_SEARCH_URL,
            params={"q": name, **base_params},
            timeout=timeout,
        )
        response.raise_for_status()
        docs = response.json().get("response", {}).get("docs", [])
        result = _pick_best(docs, name)
        if result:
            return result

        # Fallback: search synonyms
        response = requests.get(
            OLS4_SEARCH_URL,
            params={"q": name, "queryFields": "label,synonym", **base_params},
            timeout=timeout,
        )
        response.raise_for_status()
        docs = response.json().get("response", {}).get("docs", [])
        return _pick_best(docs, name)
    except requests.RequestException as exc:
        logger.warning("OLS4 search failed for %r: %s", name, exc)
        return None


def _collect_enrichable(criteria: list[dict]) -> list[dict]:
    result = []
    for criterion in criteria:
        result.extend(_collect_enrichable(criterion.get("values") or []))
        type_ = criterion.get("type")
        if not type_ or type_ in SKIP_TYPES:
            continue
        if criterion.get("ontology_id"):
            continue
        if not (criterion.get("name") or "").strip():
            continue
        result.append(criterion)
    return result


def _apply_mapping(
    criteria: list[dict],
    mapping: dict[str, str],
    verbose_callback=None,
) -> None:
    for criterion in criteria:
        _apply_mapping(criterion.get("values", []), mapping, verbose_callback)
        if criterion.get("type") in SKIP_TYPES:
            continue
        name = criterion.get("name", "")
        if name in mapping:
            criterion["ontology_id"] = mapping[name]
            if verbose_callback:
                verbose_callback(name, mapping[name])


def enrich_definition(
    definition: dict,
    *,
    verbose_callback=None,
) -> dict:
    inclusion_criteria = definition.get("inclusion_criteria") or []
    exclusion_criteria = definition.get("exclusion_criteria") or []
    definition["@context"] = OPENSYNDROME_CONTEXT_URL
    enrichable = _collect_enrichable(inclusion_criteria + exclusion_criteria)
    if not enrichable:
        return definition

    mapping: dict[str, str] = {}
    for criterion in enrichable:
        name = criterion["name"]
        type_ = criterion["type"]
        ontologies = CRITERION_TYPE_ONTOLOGIES.get(type_, ["hp", "efo", "mondo"])
        curie = _search_ols(name, ontologies)
        if curie:
            mapping[name] = curie

    for criteria_list in [inclusion_criteria, exclusion_criteria]:
        _apply_mapping(criteria_list, mapping, verbose_callback)

    return definition
