import instructor

from opensyndrome.providers import (
    build_model_string,
    check_provider_available,
    PROVIDER_INSTRUCTOR_MODES,
    SUPPORTED_PROVIDERS,
)


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
