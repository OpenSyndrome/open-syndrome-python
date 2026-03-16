import os

import instructor
import litellm
import ollama

SUPPORTED_PROVIDERS = ["ollama", "openai", "anthropic", "mistral", "deepseek", "gemini"]
DEFAULT_PROVIDER = "ollama"
DEFAULT_MODEL = "mistral"

PROVIDER_DEFAULT_MODELS = {
    "ollama": "mistral",
    "openai": "gpt-4o",
    "anthropic": "claude-3-haiku-20240307",
    "mistral": "mistral-large-latest",
    "deepseek": "deepseek-chat",
    "gemini": "gemini-1.5-flash",
}

PROVIDER_MODEL_PREFIXES = {
    "ollama": "ollama/",
    "openai": "",
    "anthropic": "",
    "mistral": "mistral/",
    "deepseek": "deepseek/",
    "gemini": "gemini/",
}

PROVIDER_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

PROVIDER_INSTRUCTOR_MODES = {
    "ollama": instructor.Mode.JSON,
    "openai": instructor.Mode.TOOLS,
    "anthropic": instructor.Mode.ANTHROPIC_TOOLS,
    "mistral": instructor.Mode.JSON,
    "deepseek": instructor.Mode.JSON,
    "gemini": instructor.Mode.JSON,
}


def build_model_string(provider: str, model: str | None = None) -> str:
    resolved_model = model or PROVIDER_DEFAULT_MODELS.get(provider, DEFAULT_MODEL)
    prefix = PROVIDER_MODEL_PREFIXES.get(provider, "")
    return f"{prefix}{resolved_model}"


def get_litellm_kwargs(provider: str) -> dict:
    """Return extra kwargs to pass to litellm (e.g. api_base for ollama)."""
    if provider == "ollama":
        base_url = os.environ.get("OLLAMA_BASE_URL") or os.environ.get(
            "OLLAMA_API_BASE"
        )
        if base_url:
            return {"api_base": base_url}
    return {}


def get_instructor_client(provider: str = DEFAULT_PROVIDER):
    mode = PROVIDER_INSTRUCTOR_MODES.get(provider, instructor.Mode.JSON)
    return instructor.from_litellm(litellm.completion, mode=mode)


def _ollama_model_exists(model: str) -> bool:
    """Check if a model is available locally in ollama."""
    available_models = {m.model for m in ollama.list().models}
    # normalize: "mistral" matches "mistral:latest"
    normalized = model if ":" in model else f"{model}:latest"
    return normalized in available_models or model in available_models


def check_provider_available(provider: str, model: str) -> tuple[bool, str]:
    if provider == "ollama":
        try:
            resolved_model = model or PROVIDER_DEFAULT_MODELS["ollama"]
            if not _ollama_model_exists(resolved_model):
                return (
                    False,
                    f"Model '{resolved_model}' not found locally. Run: ollama pull {resolved_model}",
                )
            return True, ""
        except (ConnectionError, OSError) as e:
            return False, f"Ollama service is missing or unavailable: {e}"
    else:
        env_key = PROVIDER_ENV_KEYS.get(provider)
        if env_key and not os.environ.get(env_key):
            return False, f"Missing environment variable: {env_key}"
        return True, ""
