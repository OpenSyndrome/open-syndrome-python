from unittest.mock import MagicMock, patch

import requests

from opensyndrome.ontology import (
    OPENSYNDROME_CONTEXT_URL,
    _apply_mapping,
    _collect_enrichable,
    _pick_best,
    _search_ols,
    enrich_definition,
)


def _ols_response(label: str, short_form: str, score: float = 10.0) -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "response": {
            "docs": [{"label": label, "short_form": short_form, "score": score}]
        }
    }
    return mock


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


class TestPickBest:
    def test_exact_match_wins(self):
        docs = [{"label": "Fever", "short_form": "HP_0001945", "score": 1.0}]
        assert _pick_best(docs, "Fever") == "HP:0001945"

    def test_exact_match_case_insensitive(self):
        docs = [{"label": "Skin rash", "short_form": "HP_0000988", "score": 1.0}]
        assert _pick_best(docs, "SKIN RASH") == "HP:0000988"

    def test_score_threshold(self):
        docs = [{"label": "Febrile", "short_form": "HP_0001945", "score": 6.0}]
        assert _pick_best(docs, "other") == "HP:0001945"

    def test_below_threshold_returns_none(self):
        docs = [{"label": "Something", "short_form": "HP_0001945", "score": 1.0}]
        assert _pick_best(docs, "other") is None

    def test_none_score_is_accepted(self):
        docs = [{"label": "Skin rash", "short_form": "HP_0000988", "score": None}]
        assert _pick_best(docs, "other") == "HP:0000988"

    def test_empty_docs_returns_none(self):
        assert _pick_best([], "Fever") is None


class TestSearchOls:
    def test_returns_curie_on_exact_match(self):
        with patch("opensyndrome.ontology.requests.get") as mock_get:
            mock_get.return_value = _ols_response("Fever", "HP_0001945")
            result = _search_ols("Fever", ["hp"])
        assert result == "HP:0001945"

    def test_returns_curie_on_score_threshold(self):
        with patch("opensyndrome.ontology.requests.get") as mock_get:
            mock_get.return_value = _ols_response("Febrile", "HP_0001945", score=6.0)
            result = _search_ols("Febrile", ["hp"])
        assert result == "HP:0001945"

    def test_returns_none_below_threshold(self):
        with patch("opensyndrome.ontology.requests.get") as mock_get:
            mock_get.return_value = _ols_response("Unrelated", "HP_0001945", score=1.0)
            result = _search_ols("Something else", ["hp"])
        assert result is None

    def test_returns_none_on_empty_docs(self):
        with patch("opensyndrome.ontology.requests.get") as mock_get:
            mock = MagicMock()
            mock.raise_for_status = MagicMock()
            mock.json.return_value = {"response": {"docs": []}}
            mock_get.return_value = mock
            result = _search_ols("Unknown term", ["hp"])
        assert result is None

    def test_falls_back_to_synonym_search(self):
        no_match = MagicMock()
        no_match.raise_for_status = MagicMock()
        no_match.json.return_value = {"response": {"docs": []}}
        synonym_hit = _ols_response("Skin rash", "HP_0000988", score=8.0)
        with patch(
            "opensyndrome.ontology.requests.get", side_effect=[no_match, synonym_hit]
        ):
            result = _search_ols("rash", ["hp"])
        assert result == "HP:0000988"

    def test_returns_none_on_request_exception(self):
        with patch("opensyndrome.ontology.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("timeout")
            result = _search_ols("Fever", ["hp"])
        assert result is None

    def test_normalizes_short_form(self):
        with patch("opensyndrome.ontology.requests.get") as mock_get:
            mock_get.return_value = _ols_response("Dengue fever", "MONDO_0005148")
            result = _search_ols("Dengue fever", ["mondo"])
        assert result == "MONDO:0005148"


class TestEnrichDefinition:
    def test_sets_context(self, mocker):
        mocker.patch("opensyndrome.ontology._search_ols", return_value=None)
        definition = {"inclusion_criteria": [{"type": "symptom", "name": "Fever"}]}
        result = enrich_definition(definition)
        assert result["@context"] == OPENSYNDROME_CONTEXT_URL

    def test_applies_mapping_to_inclusion_criteria(self, mocker):
        mocker.patch("opensyndrome.ontology._search_ols", return_value="HP:0001945")
        criterion = {"type": "symptom", "name": "Fever"}
        enrich_definition({"inclusion_criteria": [criterion]})
        assert criterion["ontology_id"] == "HP:0001945"

    def test_applies_mapping_to_exclusion_criteria(self, mocker):
        mocker.patch("opensyndrome.ontology._search_ols", return_value="HP:0000988")
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
        mocker.patch("opensyndrome.ontology._search_ols", return_value="HP:0001945")
        definition = {
            "inclusion_criteria": [{"type": "symptom", "name": "Fever"}],
            "exclusion_criteria": None,
        }
        result = enrich_definition(definition)
        assert result["@context"] == OPENSYNDROME_CONTEXT_URL

    def test_calls_verbose_callback(self, mocker):
        mocker.patch("opensyndrome.ontology._search_ols", return_value="HP:0001945")
        calls = []
        definition = {"inclusion_criteria": [{"type": "symptom", "name": "Fever"}]}
        enrich_definition(
            definition,
            verbose_callback=lambda n, c: calls.append((n, c)),
        )
        assert calls == [("Fever", "HP:0001945")]

    def test_uses_correct_ontologies_per_type(self, mocker):
        mock_search = mocker.patch(
            "opensyndrome.ontology._search_ols", return_value=None
        )
        enrich_definition(
            {"inclusion_criteria": [{"type": "diagnosis", "name": "Dengue"}]}
        )
        _, ontologies = mock_search.call_args.args
        assert ontologies == ["mondo", "efo"]
