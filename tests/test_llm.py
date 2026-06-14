"""LLMProvider Protocol, MockProvider, JSON contract retry, prompt loader."""

import pytest

from core.llm.json_contract import JsonContractError, complete_with_retry
from core.llm.prompts import load_prompt
from core.llm.provider import MockProvider


def test_mock_provider_returns_scripted_responses_in_order():
    mock = MockProvider([{"a": 1}, {"b": 2}])
    assert mock.complete_json("sys", "user one") == {"a": 1}
    assert mock.complete_json("sys", "user two") == {"b": 2}
    assert mock.calls == [("sys", "user one"), ("sys", "user two")]


def test_mock_provider_exhausted_raises():
    mock = MockProvider([])
    with pytest.raises(IndexError):
        mock.complete_json("s", "u")


def test_retry_passes_through_valid_response():
    mock = MockProvider([{"verdicts": []}])
    out = complete_with_retry(mock, "sys", "user", required_keys=("verdicts",))
    assert out == {"verdicts": []}
    assert len(mock.calls) == 1


def test_retry_reprompts_once_with_schema_then_succeeds():
    mock = MockProvider([{"wrong": True}, {"verdicts": []}])
    out = complete_with_retry(mock, "sys", "user", required_keys=("verdicts",))
    assert out == {"verdicts": []}
    assert len(mock.calls) == 2
    assert "verdicts" in mock.calls[1][1]  # the retry message restates the schema keys


def test_retry_fails_clean_after_second_miss():
    mock = MockProvider([{"wrong": True}, {"still": "wrong"}])
    with pytest.raises(JsonContractError, match="réponse du modèle invalide"):
        complete_with_retry(mock, "sys", "user", required_keys=("verdicts",))


def test_load_prompt_reads_french_template():
    text = load_prompt("enrich_brief")
    assert "synonymes" in text.lower()


def test_load_prompt_unknown_fails_loud():
    with pytest.raises(FileNotFoundError):
        load_prompt("does-not-exist")


def test_importing_provider_modules_does_not_import_sdks():
    import sys

    import core.llm.deepseek  # noqa: F401
    import core.llm.gemini  # noqa: F401
    import core.llm.mistral  # noqa: F401

    assert "google.genai" not in sys.modules
    assert "mistralai" not in sys.modules
    assert "openai" not in sys.modules


def test_gemini_calls_official_sdk_for_json(monkeypatch):
    import sys
    import types

    captured: dict = {}

    class _Models:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(text='{"ok": true}')

    class _Client:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.models = _Models()

    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = _Client
    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)

    from core.llm.gemini import GeminiProvider

    out = GeminiProvider(api_key="k").complete_json("sys", "user")
    assert out == {"ok": True}
    assert captured["api_key"] == "k"
    assert captured["model"] == "gemini-3.5-flash"
    assert captured["contents"] == "user"
    assert captured["config"]["system_instruction"] == "sys"
    assert captured["config"]["temperature"] == 0
    assert captured["config"]["response_mime_type"] == "application/json"


def test_mistral_missing_sdk_raises_clear_error(monkeypatch):
    import sys

    from core.llm.mistral import MistralProvider

    monkeypatch.setitem(sys.modules, "mistralai", None)
    with pytest.raises(RuntimeError, match="mistralai"):
        MistralProvider(api_key="k")


def test_deepseek_calls_openai_compatible_endpoint(monkeypatch):
    import sys
    import types

    captured: dict = {}

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            msg = types.SimpleNamespace(content='{"ok": true}')
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    class _Client:
        def __init__(self, api_key, base_url):
            captured["base_url"] = base_url
            self.chat = types.SimpleNamespace(completions=_Completions())

    fake = types.ModuleType("openai")
    fake.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", fake)

    from core.llm.deepseek import DeepSeekProvider

    out = DeepSeekProvider(api_key="k").complete_json("sys", "user")
    assert out == {"ok": True}
    assert captured["base_url"] == "https://api.deepseek.com"
    assert captured["temperature"] == 0
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["messages"][0] == {"role": "system", "content": "sys"}


def test_grok_calls_xai_endpoint(monkeypatch):
    import sys
    import types

    captured: dict = {}

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            msg = types.SimpleNamespace(content='{"ok": true}')
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    class _Client:
        def __init__(self, api_key, base_url):
            captured["base_url"] = base_url
            self.chat = types.SimpleNamespace(completions=_Completions())

    fake = types.ModuleType("openai")
    fake.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", fake)

    from core.llm.grok import GrokProvider

    out = GrokProvider(api_key="k").complete_json("sys", "user")
    assert out == {"ok": True}
    assert captured["base_url"] == "https://api.x.ai/v1"
    assert captured["temperature"] == 0
    assert captured["response_format"] == {"type": "json_object"}


def test_factory_resolves_grok(monkeypatch):
    import sys
    import types

    fake = types.ModuleType("openai")
    fake.OpenAI = lambda api_key, base_url: types.SimpleNamespace(chat=None)
    monkeypatch.setitem(sys.modules, "openai", fake)

    from core.llm.factory import make_provider

    monkeypatch.setenv("SCOPEGRAPH_LLM_PROVIDER", "grok")
    monkeypatch.setenv("GROK_API_KEY", "k")
    assert type(make_provider()).__name__ == "GrokProvider"


def test_factory_resolves_gemini(monkeypatch):
    import sys
    import types

    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = lambda api_key: types.SimpleNamespace(models=None)
    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)

    from core.llm.factory import make_provider

    monkeypatch.setenv("SCOPEGRAPH_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert type(make_provider()).__name__ == "GeminiProvider"


def test_load_dotenv_fills_missing_vars_without_overriding(monkeypatch, tmp_path):
    from core.llm.factory import load_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text(
        "# clés locales\nMISTRAL_API_KEY=from-file\n"
        'DEEPSEEK_API_KEY="quoted"\n\nexport EXTRA=ok\nmalformed line\n'
    )
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("EXTRA", "already-set")
    load_dotenv(env_file)
    import os

    assert os.environ["MISTRAL_API_KEY"] == "from-file"
    assert os.environ["DEEPSEEK_API_KEY"] == "quoted"
    assert os.environ["EXTRA"] == "already-set"  # real env always wins
    monkeypatch.delenv("MISTRAL_API_KEY")
    monkeypatch.delenv("DEEPSEEK_API_KEY")


def test_load_dotenv_missing_file_is_a_noop(tmp_path):
    from core.llm.factory import load_dotenv

    load_dotenv(tmp_path / "absent.env")  # must not raise


def test_caching_provider_memoizes_by_model_system_user(tmp_path):
    from core.llm.caching import CachingProvider

    inner = MockProvider([{"a": 1}, {"b": 2}])
    inner.model = "m1"
    cached = CachingProvider(inner, tmp_path)
    assert cached.complete_json("sys", "u") == {"a": 1}
    assert cached.complete_json("sys", "u") == {"a": 1}  # served from disk, not the queue
    assert len(inner.calls) == 1  # the inner provider was called only once
    assert cached.complete_json("sys", "other") == {"b": 2}  # different user → inner call
    assert len(inner.calls) == 2


def test_caching_provider_disabled_bypasses_cache(tmp_path):
    from core.llm.caching import CachingProvider

    inner = MockProvider([{"a": 1}, {"a": 1}])
    cached = CachingProvider(inner, tmp_path, enabled=False)
    cached.complete_json("s", "u")
    cached.complete_json("s", "u")
    assert len(inner.calls) == 2  # no cache read


def test_factory_resolves_provider_from_env(monkeypatch):
    from core.llm.factory import make_provider

    monkeypatch.setenv("SCOPEGRAPH_LLM_PROVIDER", "mock")
    assert type(make_provider()).__name__ == "MockProvider"
    monkeypatch.setenv("SCOPEGRAPH_LLM_PROVIDER", "none")
    assert make_provider() is None
    monkeypatch.setenv("SCOPEGRAPH_LLM_PROVIDER", "nope")
    with pytest.raises(ValueError, match="nope"):
        make_provider()
