import logging

import requests

logger = logging.getLogger(__name__)

OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"
OPENSYNDROME_CONTEXT_URL = "https://opensyndrome.org/schema/v1/context.jsonld"
SKIP_TYPES = {"criterion", "demographic_criteria"}
MIN_SCORE = 5.0
TEXT2TERM_MIN_SCORE = 0.5

CRITERION_TYPE_ONTOLOGIES = {
    "symptom": ["mondo", "hp"],
    "diagnosis": ["mondo", "efo"],
    "syndrome": ["mondo", "efo"],
    "diagnostic_test": ["loinc", "obi"],
    "epidemiological_history": ["hp", "efo"],
    "professional_judgment": ["hp", "efo"],
}

MAPPERS = ("ols", "text2term")


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


def _iri_to_curie(iri: str) -> str:
    """Convert an OBO IRI to a CURIE. e.g. http://purl.obolibrary.org/obo/HP_0001945 → HP:0001945"""
    local = iri.rstrip("/").rsplit("/", 1)[-1]
    return local.replace("_", ":", 1)


def _search_text2term(
    name: str, ontologies: list[str], min_score: float = TEXT2TERM_MIN_SCORE
) -> str | None:
    try:
        import text2term
    except ImportError:
        raise ImportError("text2term is not installed. Run: pip install text2term")

    for ontology in ontologies:
        try:
            use_cache = text2term.cache.is_ontology_in_cache(ontology.upper())
            df = text2term.map_terms(
                source_terms=[name],
                target_ontology=ontology.upper(),
                max_mappings=1,
                min_score=min_score,
                use_cache=use_cache,
                excl_deprecated=True,
            )
            if not df.empty:
                return _iri_to_curie(df.iloc[0]["Mapped Term IRI"])
        except Exception as exc:
            logger.warning(
                "text2term search failed for %r with %s: %s", name, ontology, exc
            )
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
    mapper: str = "ols",
    verbose_callback=None,
) -> dict:
    if mapper not in MAPPERS:
        raise ValueError(
            f"Unknown mapper {mapper!r}. Choose from: {', '.join(MAPPERS)}"
        )

    search_fn = _search_ols if mapper == "ols" else _search_text2term

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
        curie = search_fn(name, ontologies)
        if curie:
            mapping[name] = curie

    for criteria_list in [inclusion_criteria, exclusion_criteria]:
        _apply_mapping(criteria_list, mapping, verbose_callback)

    return definition
