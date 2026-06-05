from unittest.mock import Mock

import instructor

from opensyndrome.providers import (
    build_model_string,
    check_provider_available,
    get_litellm_kwargs,
    PROVIDER_INSTRUCTOR_MODES,
    SUPPORTED_PROVIDERS,
)


class TestOllamaHostResolution:
    """A single ollama URL var should drive both litellm and the availability check."""

    def _clear(self, monkeypatch):
        for var in ("OLLAMA_HOST", "OLLAMA_BASE_URL", "OLLAMA_API_BASE"):
            monkeypatch.delenv(var, raising=False)

    def test_litellm_api_base_from_ollama_host_alone(self, monkeypatch):
        self._clear(monkeypatch)
        monkeypatch.setenv("OLLAMA_HOST", "http://host.docker.internal:11434")

        assert get_litellm_kwargs("ollama") == {
            "api_base": "http://host.docker.internal:11434"
        }

    def test_litellm_api_base_from_ollama_base_url_still_works(self, monkeypatch):
        self._clear(monkeypatch)
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://elsewhere:11434")

        assert get_litellm_kwargs("ollama") == {"api_base": "http://elsewhere:11434"}

    def test_no_kwargs_when_no_ollama_var_set(self, monkeypatch):
        self._clear(monkeypatch)

        assert get_litellm_kwargs("ollama") == {}

    def test_availability_check_uses_resolved_host(self, monkeypatch, mocker):
        self._clear(monkeypatch)
        monkeypatch.setenv("OLLAMA_HOST", "http://host.docker.internal:11434")
        client = mocker.patch("opensyndrome.providers.ollama.Client")
        client.return_value.list.return_value = Mock(
            models=[Mock(model="mistral:latest")]
        )

        check_provider_available("ollama", "mistral")

        client.assert_called_once_with(host="http://host.docker.internal:11434")


class TestHuggingFaceProvider:
    def test_routes_model_string_through_huggingface(self):
        model_string = build_model_string("huggingface", "google/gemma-2-9b-it")

        assert model_string == "huggingface/google/gemma-2-9b-it"

    def test_is_a_supported_provider(self):
        assert "huggingface" in SUPPORTED_PROVIDERS

    def test_unavailable_without_hf_token(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)

        available, message = check_provider_available(
            "huggingface", "google/gemma-2-9b-it"
        )

        assert available is False
        assert "HF_TOKEN" in message

    def test_available_with_hf_token(self, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "hf_xxx")

        available, message = check_provider_available(
            "huggingface", "google/gemma-2-9b-it"
        )

        assert available is True
        assert message == ""

    def test_uses_json_instructor_mode(self):
        assert PROVIDER_INSTRUCTOR_MODES["huggingface"] == instructor.Mode.JSON
