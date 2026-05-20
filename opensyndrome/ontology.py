import logging
from typing import Literal, get_args

import requests
from ols_client import EBIClient

logger = logging.getLogger(__name__)

OPENSYNDROME_CONTEXT_URL = "https://opensyndrome.org/schema/v1/context.jsonld"
SKIP_TYPES = {"criterion", "demographic_criteria"}
TEXT2TERM_MIN_SCORE = 0.5

ols = EBIClient()

CRITERION_TYPE_ONTOLOGIES = {
    "symptom": ["mondo", "hp"],
    "diagnosis": ["mondo", "efo"],
    "syndrome": ["mondo", "efo"],
    "diagnostic_test": ["loinc", "obi"],
    "epidemiological_history": ["hp", "efo"],
    "professional_judgment": ["hp", "efo"],
}

type Mapper = Literal["ols", "text2term"]
MAPPERS: tuple[Mapper, ...] = get_args(Mapper.__value__)


def _pick_best(docs: list[dict], name: str) -> str | None:
    for doc in docs:
        if doc.get("label", "").lower() == name.lower():
            return doc["obo_id"]
    return None


def _search_ols(queries: dict[str, list[str]], timeout: int = 10) -> dict[str, str]:
    """Map names to CURIEs via OLS4 (one HTTP call per name; per-name failures are isolated)."""
    result: dict[str, str] = {}
    for name, ontologies in queries.items():
        base_params = {
            "q": name,
            "ontology": ",".join(ontologies),
            "rows": 5,
            "type": "class",
        }
        try:
            payload = ols.get_json("/search", params=base_params, timeout=timeout)
            docs = payload.get("response", {}).get("docs", [])
            curie = _pick_best(docs, name)
            if not curie:
                payload = ols.get_json(
                    "/search",
                    params={**base_params, "queryFields": "label,synonym"},
                    timeout=timeout,
                )
                docs = payload.get("response", {}).get("docs", [])
                curie = _pick_best(docs, name)
            if curie:
                result[name] = curie
        except requests.RequestException as exc:
            logger.warning("OLS4 search failed for %r: %s", name, exc)
    return result


def _iri_to_curie(iri: str) -> str | None:
    """Convert an ontology IRI to a CURIE. e.g. http://purl.obolibrary.org/obo/HP_0001945 → HP:0001945"""
    import bioregistry

    try:
        prefix, identifier = bioregistry.parse_iri(iri, use_preferred=True)
    except TypeError:
        # bioregistry v0.11.35 raises on unparseable IRIs instead of returning (None, None).
        return None
    if not prefix:
        return None
    # bioregistry uses "obo" as a generic fallback for unrecognized OBO PURLs
    # e.g. LOINC_2345-7, UNKNOWN_42
    # reject to avoid producing OBO:* CURIEs
    if prefix.lower() == "obo" and "_" in identifier:
        return None
    return f"{prefix.upper()}:{identifier}"


def _search_text2term(
    queries: dict[str, list[str]],
    min_score: float = TEXT2TERM_MIN_SCORE,
) -> dict[str, str]:
    """Batch-map names to CURIEs via text2term, loading each ontology at most once."""
    try:
        import text2term
    except ImportError:
        raise ImportError(
            "text2term is not installed. Run: pip install text2term"
        ) from None

    names_per_ontology: dict[str, set[str]] = {}
    for name, ontologies in queries.items():
        for ontology in ontologies:
            names_per_ontology.setdefault(ontology.upper(), set()).add(name)

    matches_per_ontology: dict[str, dict[str, str]] = {}
    for ontology, names in names_per_ontology.items():
        try:
            use_cache = text2term.cache_exists(ontology)
            df = text2term.map_terms(
                source_terms=sorted(names),
                target_ontology=ontology,
                max_mappings=1,
                min_score=min_score,
                use_cache=use_cache,
                excl_deprecated=True,
            )
            ontology_matches: dict[str, str] = {}
            for _, row in df.iterrows():
                curie = _iri_to_curie(row["Mapped Term IRI"])
                if curie:
                    ontology_matches[row["Source Term"]] = curie
            matches_per_ontology[ontology] = ontology_matches
        except (requests.RequestException, OSError, RuntimeError, ValueError) as exc:
            logger.warning(
                "text2term batch failed for %s (%d terms): %s",
                ontology,
                len(names),
                exc,
            )

    result: dict[str, str] = {}
    for name, ontologies in queries.items():
        for ontology in ontologies:
            curie = matches_per_ontology.get(ontology.upper(), {}).get(name)
            if curie:
                result[name] = curie
                break
    return result


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
    mapper: Mapper = "ols",
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

    queries: dict[str, list[str]] = {
        c["name"]: CRITERION_TYPE_ONTOLOGIES.get(c["type"], ["hp", "efo", "mondo"])
        for c in enrichable
    }
    mapping = search_fn(queries)

    for criteria_list in [inclusion_criteria, exclusion_criteria]:
        _apply_mapping(criteria_list, mapping, verbose_callback)

    return definition
