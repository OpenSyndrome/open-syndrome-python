from unittest.mock import Mock

from opensyndrome.cli import is_ollama_available
import pytest
from ollama._types import ResponseError


class TestIsOllamaAvailable:
    @pytest.fixture
    def mock_ollama(self, mocker):
        _mock_ollama = mocker.patch("opensyndrome.cli.ollama")
        list_response = Mock(models=[Mock(model="mistral")])

        def make_mock(return_value=None, side_effect=None):
            if side_effect:
                _mock_ollama.list.side_effect = side_effect
            else:
                _mock_ollama.list.return_value = return_value or list_response
            return _mock_ollama

        return make_mock

    def test_is_ollama_available(self, mock_ollama):
        assert is_ollama_available() is True

    def test_show_error_when_the_model_is_not_available(self, mock_ollama):
        error_message = "model 'gemma3' not found (status code: 404)"
        mock_ollama(side_effect=ResponseError(error=error_message))
        assert is_ollama_available() is False

    def test_show_error_when_cannot_connect_to_ollama(self, mock_ollama):
        mock_ollama(side_effect=ConnectionError())
        assert is_ollama_available() is False
