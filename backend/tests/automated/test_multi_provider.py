"""
S13 — Multi-provider LLM (OpenAI / Ollama)
    Métriques : détection de provider, configuration base_url, api_key distinction,
                fallback model par défaut, compatibilité noms de modèles connus
"""
import os
import pytest


# ── Fixture : clé OpenAI factice pour les tests sans appel réseau ─────────────

@pytest.fixture(autouse=True)
def fake_openai_key(monkeypatch):
    """Injecte OPENAI_API_KEY=test-key si absent — évite OpenAIError sans API réelle."""
    if not os.environ.get("OPENAI_API_KEY"):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-for-unit-tests")


# ── Helper métrique ───────────────────────────────────────────────────────────

def _metric(name: str, value: str, threshold: str, passed: bool) -> None:
    icon = "✅" if passed else "❌"
    print(f"OTAI_METRIC | {name:<36} | {value:<22} | seuil {threshold:<16} | {icon}")


# ── Helper: extraire base_url d'un ChatOpenAI ─────────────────────────────────

def _get_base_url(llm) -> str:
    """Retourne la base_url du client ChatOpenAI, quelle que soit la version langchain."""
    for attr in ("openai_api_base", "base_url"):
        val = getattr(llm, attr, None)
        if val:
            return str(val)
    # Accès via le client httpx sous-jacent (langchain-openai >= 0.2)
    client = getattr(llm, "client", None) or getattr(llm, "_client", None)
    if client:
        base = getattr(client, "base_url", None)
        if base:
            return str(base)
    return ""


def _get_api_key(llm) -> str:
    """Retourne la valeur de l'api_key du client ChatOpenAI."""
    raw = getattr(llm, "openai_api_key", None)
    if raw is None:
        return ""
    try:
        return raw.get_secret_value()
    except AttributeError:
        return str(raw)


# ═══════════════════════════════════════════════════════════════════════════════
# Détection de provider (_is_openai_model)
# ═══════════════════════════════════════════════════════════════════════════════

def test_openai_prefixes_detected():
    from open_tutorai.agents.langgraph.llm_factory import _is_openai_model
    openai_models = [
        "gpt-4o-mini", "gpt-4o", "gpt-4", "gpt-3.5-turbo",
        "o1-mini", "o3-turbo", "o4-preview",
        "text-embedding-ada-002",
    ]
    all_ok = True
    for model in openai_models:
        result = _is_openai_model(model)
        ok = result is True
        if not ok:
            all_ok = False
        _metric(f"OpenAI détecté [{model}]", str(result), "= True", ok)
    assert all_ok, "Certains modèles OpenAI ne sont pas détectés correctement"


def test_ollama_models_not_detected_as_openai():
    from open_tutorai.agents.langgraph.llm_factory import _is_openai_model
    ollama_models = [
        "llama3:8b", "llama3.1", "llama3.2",
        "mistral", "mistral:7b",
        "qwen2:7b", "qwen2.5",
        "deepseek-r1", "phi3", "gemma2",
    ]
    all_ok = True
    for model in ollama_models:
        result = _is_openai_model(model)
        ok = result is False
        if not ok:
            all_ok = False
        _metric(f"Ollama non-OpenAI [{model}]", str(result), "= False", ok)
    assert all_ok, "Certains modèles Ollama sont détectés à tort comme OpenAI"


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration get_llm — model_name
# ═══════════════════════════════════════════════════════════════════════════════

def test_get_llm_openai_model_name():
    from open_tutorai.agents.langgraph.llm_factory import get_llm
    llm = get_llm("gpt-4o-mini")
    model = getattr(llm, "model_name", None) or getattr(llm, "model", None)
    ok = model == "gpt-4o-mini"
    _metric("OpenAI model_name", str(model), "= gpt-4o-mini", ok)
    assert ok, f"model_name inattendu : {model!r}"


def test_get_llm_ollama_model_name():
    from open_tutorai.agents.langgraph.llm_factory import get_llm
    llm = get_llm("llama3:8b")
    model = getattr(llm, "model_name", None) or getattr(llm, "model", None)
    ok = model == "llama3:8b"
    _metric("Ollama model_name", str(model), "= llama3:8b", ok)
    assert ok, f"model_name inattendu : {model!r}"


def test_get_llm_mistral_model_name():
    from open_tutorai.agents.langgraph.llm_factory import get_llm
    llm = get_llm("mistral")
    model = getattr(llm, "model_name", None) or getattr(llm, "model", None)
    ok = model == "mistral"
    _metric("Ollama mistral model_name", str(model), "= mistral", ok)
    assert ok, f"model_name inattendu : {model!r}"


def test_get_llm_default_returns_valid_model():
    from open_tutorai.agents.langgraph.llm_factory import get_llm
    llm = get_llm(None)
    model = getattr(llm, "model_name", None) or getattr(llm, "model", None)
    ok = bool(model)
    _metric("get_llm(None) modèle non vide", str(model), "≠ None/vide", ok)
    assert ok, "get_llm(None) doit retourner un client avec un nom de modèle"


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration get_llm — base_url / api_key
# ═══════════════════════════════════════════════════════════════════════════════

def test_ollama_uses_local_base_url():
    from open_tutorai.agents.langgraph.llm_factory import get_llm
    ollama_host = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    # Extraire le port (ex: "11434")
    port = ollama_host.rstrip("/").rsplit(":", 1)[-1].split("/")[0]

    llm = get_llm("llama3:8b")
    base = _get_base_url(llm)
    ok = port in base
    _metric("Ollama base_url locale", base[:50], f"contient :{port}", ok)
    assert ok, f"base_url Ollama inattendu : {base!r} (attendu port {port})"


def test_openai_does_not_use_ollama_url():
    from open_tutorai.agents.langgraph.llm_factory import get_llm
    llm = get_llm("gpt-4o-mini")
    base = _get_base_url(llm)
    ok = "11434" not in base
    _metric("OpenAI ≠ Ollama base_url", base[:50] or "(default OpenAI)", "sans 11434", ok)
    assert ok, f"Client OpenAI pointe sur l'URL Ollama : {base!r}"


def test_ollama_api_key_is_fixed_string():
    from open_tutorai.agents.langgraph.llm_factory import get_llm
    llm = get_llm("mistral")
    key = _get_api_key(llm)
    ok = key == "ollama"
    _metric("Ollama api_key = 'ollama'", key, "= ollama", ok)
    assert ok, f"api_key Ollama inattendu : {key!r}"


def test_openai_api_key_not_ollama_placeholder():
    from open_tutorai.agents.langgraph.llm_factory import get_llm
    llm = get_llm("gpt-4o-mini")
    key = _get_api_key(llm)
    ok = key != "ollama"
    display = (key[:12] + "...") if len(key) > 12 else (key or "(vide)")
    _metric("OpenAI api_key ≠ 'ollama'", display, "≠ ollama", ok)
    assert ok, "Le client OpenAI utilise 'ollama' comme api_key — mauvaise branche"


# ═══════════════════════════════════════════════════════════════════════════════
# Parité de comportement — même température appliquée aux deux providers
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("model", ["gpt-4o-mini", "llama3:8b"])
def test_temperature_applied(model):
    from open_tutorai.agents.langgraph.llm_factory import get_llm
    for temp in (0.0, 0.5, 1.0):
        llm = get_llm(model, temperature=temp)
        actual = getattr(llm, "temperature", None)
        ok = actual == temp
        _metric(f"temperature [{model}] t={temp}", str(actual), f"= {temp}", ok)
        assert ok, f"temperature={temp} non appliquée pour {model!r}: {actual}"


@pytest.mark.parametrize("model,expected_provider", [
    ("gpt-4o-mini",    "openai"),
    ("gpt-4o",         "openai"),
    ("llama3:8b",      "ollama"),
    ("mistral",        "ollama"),
    ("qwen2:7b",       "ollama"),
])
def test_provider_routing_matrix(model, expected_provider):
    from open_tutorai.agents.langgraph.llm_factory import get_llm, _is_openai_model
    is_openai = _is_openai_model(model)
    detected  = "openai" if is_openai else "ollama"
    ok = detected == expected_provider

    llm = get_llm(model)
    key = _get_api_key(llm)
    key_ok = (key != "ollama") if expected_provider == "openai" else (key == "ollama")

    _metric(f"Provider [{model}]",  detected, f"= {expected_provider}", ok)
    _metric(f"api_key  [{model}]",  key[:10] + "..." if len(key) > 10 else key,
            "openai≠ollama / ollama=ollama", key_ok)
    assert ok,     f"Provider incorrect pour {model!r} : {detected}"
    assert key_ok, f"api_key incorrect pour {model!r} : {key!r}"
