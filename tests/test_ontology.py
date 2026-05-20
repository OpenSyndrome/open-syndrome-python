import sys
from unittest.mock import MagicMock, patch

import pytest
import requests

from opensyndrome.ontology import (
    OPENSYNDROME_CONTEXT_URL,
    _apply_mapping,
    _collect_enrichable,
    _iri_to_curie,
    _pick_best,
    _search_ols,
    _search_text2term,
    enrich_definition,
)


def _ols_doc(label: str, obo_id: str) -> dict:
    return {"label": label, "obo_id": obo_id}


def _ols_payload(docs: list[dict]) -> dict:
    return {"response": {"docs": docs}}


class TestIriToCurie:
    @pytest.fixture(autouse=True)
    def _require_bioregistry(self):
        pytest.importorskip("bioregistry")

    def test_obo_iri(self):
        assert (
            _iri_to_curie("http://purl.obolibrary.org/obo/HP_0001945") == "HP:0001945"
        )

    def test_efo_iri(self):
        assert _iri_to_curie("http://www.ebi.ac.uk/efo/EFO_0003900") == "EFO:0003900"

    def test_mondo_iri(self):
        assert (
            _iri_to_curie("http://purl.obolibrary.org/obo/MONDO_0005148")
            == "MONDO:0005148"
        )

    def test_unparseable_iri_returns_none(self):
        assert _iri_to_curie("garbage://nonsense") is None

    def test_loinc_native_namespace_uppercased(self):
        assert _iri_to_curie("https://loinc.org/2345-7") == "LOINC:2345-7"

    def test_unknown_prefix_returns_none(self):
        assert _iri_to_curie("http://purl.obolibrary.org/obo/UNKNOWNXYZ_42") is None


def _make_text2term_module(map_terms_return=None, map_terms_side_effect=None):
    """Build a fake text2term module for injection into sys.modules.

    Uses spec=real text2term so attribute access fails fast on API drift.
    """
    import text2term as real_text2term

    fake = MagicMock(spec=real_text2term)
    if map_terms_side_effect is not None:
        fake.map_terms.side_effect = map_terms_side_effect
    else:
        fake.map_terms.return_value = map_terms_return
    return fake


class _FakeDF:
    """Minimal DataFrame stand-in for text2term output."""

    def __init__(self, rows):
        self._rows = rows

    @property
    def empty(self):
        return len(self._rows) == 0

    @property
    def iloc(self):
        return self._rows

    def iterrows(self):
        for index, row in enumerate(self._rows):
            yield index, row


_EMPTY_DF = _FakeDF([])


def _ols_df(iri: str, source_term: str = "", score: float = 0.9) -> _FakeDF:
    return _FakeDF(
        [{"Source Term": source_term, "Mapped Term IRI": iri, "Mapping Score": score}]
    )


def _text2term_map_fn(per_ontology):
    """Build a map_terms side_effect: returns rows for (src, iri) pairs registered per ontology."""

    def _map_terms(*, source_terms, target_ontology, **kwargs):
        pairs = per_ontology.get(target_ontology, [])
        rows = [
            {"Source Term": src, "Mapped Term IRI": iri, "Mapping Score": 0.9}
            for src, iri in pairs
            if src in source_terms
        ]
        return _FakeDF(rows)

    return _map_terms


class TestSearchText2term:
    @pytest.fixture(autouse=True)
    def _require_bioregistry(self):
        pytest.importorskip("bioregistry")

    @pytest.fixture(autouse=True)
    def inject_text2term(self, request):
        """Ensure text2term is removed from sys.modules between tests."""
        sys.modules.pop("text2term", None)
        yield
        sys.modules.pop("text2term", None)

    def test_returns_curie_on_match(self):
        sys.modules["text2term"] = _make_text2term_module(
            map_terms_side_effect=_text2term_map_fn(
                {"HP": [("Fever", "http://purl.obolibrary.org/obo/HP_0001945")]}
            )
        )
        assert _search_text2term({"Fever": ["hp"]}) == {"Fever": "HP:0001945"}

    def test_falls_back_to_next_ontology_on_empty(self):
        sys.modules["text2term"] = _make_text2term_module(
            map_terms_side_effect=_text2term_map_fn(
                {"MONDO": [("Dengue", "http://purl.obolibrary.org/obo/MONDO_0005148")]}
            )
        )
        assert _search_text2term({"Dengue": ["hp", "mondo"]}) == {
            "Dengue": "MONDO:0005148"
        }

    def test_returns_empty_when_no_match(self):
        sys.modules["text2term"] = _make_text2term_module(
            map_terms_side_effect=_text2term_map_fn({})
        )
        assert _search_text2term({"Unknown": ["hp"]}) == {}

    def test_skips_ontology_on_request_exception(self):
        sys.modules["text2term"] = _make_text2term_module(
            map_terms_side_effect=requests.RequestException("network error")
        )
        assert _search_text2term({"Fever": ["hp"]}) == {}

    def test_unexpected_exception_propagates(self):
        sys.modules["text2term"] = _make_text2term_module(
            map_terms_side_effect=AttributeError("bug in text2term")
        )
        with pytest.raises(AttributeError, match="bug in text2term"):
            _search_text2term({"Fever": ["hp"]})

    def test_unparseable_iri_falls_through_to_next_ontology(self):
        sys.modules["text2term"] = _make_text2term_module(
            map_terms_side_effect=_text2term_map_fn(
                {
                    "HP": [("Dengue", "garbage://nonsense")],
                    "MONDO": [
                        ("Dengue", "http://purl.obolibrary.org/obo/MONDO_0005148")
                    ],
                }
            )
        )
        assert _search_text2term({"Dengue": ["hp", "mondo"]}) == {
            "Dengue": "MONDO:0005148"
        }

    def test_priority_order_within_query_is_respected(self):
        sys.modules["text2term"] = _make_text2term_module(
            map_terms_side_effect=_text2term_map_fn(
                {
                    "HP": [("Fever", "http://purl.obolibrary.org/obo/HP_0001945")],
                    "MONDO": [
                        ("Fever", "http://purl.obolibrary.org/obo/MONDO_9999999")
                    ],
                }
            )
        )
        assert _search_text2term({"Fever": ["mondo", "hp"]}) == {
            "Fever": "MONDO:9999999"
        }

    def test_batch_loads_each_ontology_once(self):
        sys.modules["text2term"] = _make_text2term_module(
            map_terms_side_effect=_text2term_map_fn(
                {
                    "MONDO": [
                        ("Dengue", "http://purl.obolibrary.org/obo/MONDO_0005148"),
                        ("Malaria", "http://purl.obolibrary.org/obo/MONDO_0005136"),
                    ],
                }
            )
        )
        queries = {"Dengue": ["mondo"], "Malaria": ["mondo"]}
        result = _search_text2term(queries)
        assert result == {"Dengue": "MONDO:0005148", "Malaria": "MONDO:0005136"}
        assert sys.modules["text2term"].map_terms.call_count == 1

    def test_raises_on_missing_library(self):
        sys.modules["text2term"] = None
        with pytest.raises(ImportError, match="text2term is not installed"):
            _search_text2term({"Fever": ["hp"]})


class TestCollectEnrichable:
    def test_collects_enrichable_criterion(self):
        criteria = [{"type": "symptom", "name": "Fever"}]
        assert _collect_enrichable(criteria) == criteria

    def test_skips_criterion_type(self):
        assert _collect_enrichable([{"type": "criterion", "name": "Group"}]) == []

    def test_skips_demographic_criteria_type(self):
        assert (
            _collect_enrichable([{"type": "demographic_criteria", "name": "Age"}]) == []
        )

    def test_skips_existing_ontology_id(self):
        criteria = [{"type": "symptom", "name": "Fever", "ontology_id": "HP:0001945"}]
        assert _collect_enrichable(criteria) == []

    def test_skips_missing_type(self):
        assert _collect_enrichable([{"name": "Fever"}]) == []

    def test_skips_empty_name(self):
        assert _collect_enrichable([{"type": "symptom", "name": "   "}]) == []

    def test_recurses_into_values(self):
        child = {"type": "symptom", "name": "Fever"}
        criteria = [{"type": "criterion", "name": "Group", "values": [child]}]
        assert _collect_enrichable(criteria) == [child]

    def test_container_children_collected_despite_skip(self):
        child = {"type": "symptom", "name": "Rash"}
        criteria = [
            {"type": "demographic_criteria", "name": "Age group", "values": [child]}
        ]
        assert _collect_enrichable(criteria) == [child]

    def test_collects_multiple_types(self):
        criteria = [
            {"type": "symptom", "name": "Fever"},
            {"type": "diagnosis", "name": "Dengue"},
            {"type": "diagnostic_test", "name": "PCR"},
        ]
        assert _collect_enrichable(criteria) == criteria


class TestApplyMapping:
    def test_sets_ontology_id(self):
        criteria = [{"type": "symptom", "name": "Fever"}]
        _apply_mapping(criteria, {"Fever": "HP:0001945"})
        assert criteria[0]["ontology_id"] == "HP:0001945"

    def test_unmatched_criteria_unchanged(self):
        criteria = [{"type": "symptom", "name": "Rash"}]
        _apply_mapping(criteria, {"Fever": "HP:0001945"})
        assert "ontology_id" not in criteria[0]

    def test_calls_verbose_callback(self):
        calls = []
        criteria = [{"type": "symptom", "name": "Fever"}]
        _apply_mapping(
            criteria,
            {"Fever": "HP:0001945"},
            verbose_callback=lambda n, c: calls.append((n, c)),
        )
        assert calls == [("Fever", "HP:0001945")]

    def test_no_callback_when_no_match(self):
        calls = []
        criteria = [{"type": "symptom", "name": "Rash"}]
        _apply_mapping(
            criteria,
            {"Fever": "HP:0001945"},
            verbose_callback=lambda n, c: calls.append((n, c)),
        )
        assert calls == []

    def test_recurses_into_values(self):
        child = {"type": "symptom", "name": "Fever"}
        criteria = [{"type": "criterion", "name": "Group", "values": [child]}]
        _apply_mapping(criteria, {"Fever": "HP:0001945"})
        assert child["ontology_id"] == "HP:0001945"

    def test_skips_container_types(self):
        child = {"type": "symptom", "name": "Fever"}
        container = {"type": "criterion", "name": "Fever", "values": [child]}
        _apply_mapping([container], {"Fever": "HP:0001945"})
        assert "ontology_id" not in container
        assert child["ontology_id"] == "HP:0001945"


class TestPickBest:
    def test_exact_match_wins(self):
        docs = [_ols_doc("Fever", "HP:0001945")]
        assert _pick_best(docs, "Fever") == "HP:0001945"

    def test_exact_match_case_insensitive(self):
        docs = [_ols_doc("Skin rash", "HP:0000988")]
        assert _pick_best(docs, "SKIN RASH") == "HP:0000988"

    def test_no_match_returns_none(self):
        docs = [_ols_doc("Febrile", "HP:0001945")]
        assert _pick_best(docs, "other") is None

    def test_empty_docs_returns_none(self):
        assert _pick_best([], "Fever") is None


class TestSearchOls:
    def test_returns_curie_on_exact_match(self):
        with patch("opensyndrome.ontology.ols.get_json") as mock_get:
            mock_get.return_value = _ols_payload([_ols_doc("Fever", "HP:0001945")])
            result = _search_ols({"Fever": ["hp"]})
        assert result == {"Fever": "HP:0001945"}

    def test_returns_empty_when_no_match(self):
        with patch("opensyndrome.ontology.ols.get_json") as mock_get:
            mock_get.return_value = _ols_payload([])
            result = _search_ols({"Unknown term": ["hp"]})
        assert result == {}

    def test_falls_back_to_synonym_search(self):
        synonym_hit = _ols_payload([_ols_doc("rash", "HP:0000988")])
        with patch(
            "opensyndrome.ontology.ols.get_json",
            side_effect=[_ols_payload([]), synonym_hit],
        ) as mock_get:
            result = _search_ols({"rash": ["hp"]})
        assert result == {"rash": "HP:0000988"}
        assert mock_get.call_count == 2
        assert mock_get.call_args_list[1].kwargs["params"]["queryFields"] == (
            "label,synonym"
        )

    def test_skips_name_on_request_exception(self):
        with patch("opensyndrome.ontology.ols.get_json") as mock_get:
            mock_get.side_effect = requests.RequestException("timeout")
            result = _search_ols({"Fever": ["hp"]})
        assert result == {}

    def test_passes_ontology_filter_to_client(self):
        with patch("opensyndrome.ontology.ols.get_json") as mock_get:
            mock_get.return_value = _ols_payload([])
            _search_ols({"Fever": ["hp", "mondo"]})
        params = mock_get.call_args.kwargs["params"]
        assert params["ontology"] == "hp,mondo"
        assert params["type"] == "class"

    def test_passes_explicit_timeout_to_client(self):
        with patch("opensyndrome.ontology.ols.get_json") as mock_get:
            mock_get.return_value = _ols_payload([])
            _search_ols({"Fever": ["hp"]}, timeout=15)
        assert mock_get.call_args.kwargs["timeout"] == 15

    def test_resilient_when_one_name_fails(self):
        with patch("opensyndrome.ontology.ols.get_json") as mock_get:
            mock_get.side_effect = [
                requests.RequestException("timeout"),
                _ols_payload([_ols_doc("Rash", "HP:0000988")]),
            ]
            result = _search_ols({"Fever": ["hp"], "Rash": ["hp"]})
        assert result == {"Rash": "HP:0000988"}


class TestEnrichDefinition:
    def test_sets_context(self, mocker):
        mocker.patch("opensyndrome.ontology._search_ols", return_value={})
        definition = {"inclusion_criteria": [{"type": "symptom", "name": "Fever"}]}
        result = enrich_definition(definition)
        assert result["@context"] == OPENSYNDROME_CONTEXT_URL

    def test_applies_mapping_to_inclusion_criteria(self, mocker):
        mocker.patch(
            "opensyndrome.ontology._search_ols", return_value={"Fever": "HP:0001945"}
        )
        criterion = {"type": "symptom", "name": "Fever"}
        enrich_definition({"inclusion_criteria": [criterion]})
        assert criterion["ontology_id"] == "HP:0001945"

    def test_applies_mapping_to_exclusion_criteria(self, mocker):
        mocker.patch(
            "opensyndrome.ontology._search_ols", return_value={"Rash": "HP:0000988"}
        )
        criterion = {"type": "symptom", "name": "Rash"}
        enrich_definition({"inclusion_criteria": [], "exclusion_criteria": [criterion]})
        assert criterion["ontology_id"] == "HP:0000988"

    def test_no_enrichable_criteria_skips_search(self, mocker):
        mock_search = mocker.patch("opensyndrome.ontology._search_ols")
        enrich_definition({"inclusion_criteria": []})
        mock_search.assert_not_called()

    def test_sets_context_even_with_no_enrichable_criteria(self, mocker):
        mocker.patch("opensyndrome.ontology._search_ols")
        definition = {"inclusion_criteria": []}
        enrich_definition(definition)
        assert definition["@context"] == OPENSYNDROME_CONTEXT_URL

    def test_handles_none_exclusion_criteria(self, mocker):
        mocker.patch(
            "opensyndrome.ontology._search_ols", return_value={"Fever": "HP:0001945"}
        )
        definition = {
            "inclusion_criteria": [{"type": "symptom", "name": "Fever"}],
            "exclusion_criteria": None,
        }
        result = enrich_definition(definition)
        assert result["@context"] == OPENSYNDROME_CONTEXT_URL

    def test_calls_verbose_callback(self, mocker):
        mocker.patch(
            "opensyndrome.ontology._search_ols", return_value={"Fever": "HP:0001945"}
        )
        calls = []
        definition = {"inclusion_criteria": [{"type": "symptom", "name": "Fever"}]}
        enrich_definition(
            definition,
            verbose_callback=lambda n, c: calls.append((n, c)),
        )
        assert calls == [("Fever", "HP:0001945")]

    def test_uses_correct_ontologies_per_type(self, mocker):
        mock_search = mocker.patch("opensyndrome.ontology._search_ols", return_value={})
        enrich_definition(
            {"inclusion_criteria": [{"type": "diagnosis", "name": "Dengue"}]}
        )
        queries = mock_search.call_args.args[0]
        assert queries == {"Dengue": ["mondo", "efo"]}

    def test_uses_text2term_mapper(self, mocker):
        mock_search = mocker.patch(
            "opensyndrome.ontology._search_text2term",
            return_value={"Fever": "HP:0001945"},
        )
        criterion = {"type": "symptom", "name": "Fever"}
        enrich_definition({"inclusion_criteria": [criterion]}, mapper="text2term")
        mock_search.assert_called_once()
        assert criterion["ontology_id"] == "HP:0001945"

    def test_invalid_mapper_raises(self):
        with pytest.raises(ValueError, match="Unknown mapper"):
            enrich_definition({"inclusion_criteria": []}, mapper="unknown")

    def test_duplicate_names_last_criterion_type_wins(self, mocker):
        """Contract: when the same name appears under different criterion types,
        the LAST occurrence's ontology preference is queried, and the resulting
        CURIE is applied to every occurrence."""
        mock_search = mocker.patch(
            "opensyndrome.ontology._search_ols",
            return_value={"Fever": "EFO:0009088"},
        )
        inclusion = [
            {"type": "symptom", "name": "Fever"},
            {"type": "diagnosis", "name": "Fever"},
        ]
        enrich_definition({"inclusion_criteria": inclusion})

        queries = mock_search.call_args.args[0]
        assert queries == {"Fever": ["mondo", "efo"]}
        assert inclusion[0]["ontology_id"] == "EFO:0009088"
        assert inclusion[1]["ontology_id"] == "EFO:0009088"
