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
    import core.llm.mistral  # noqa: F401

    assert "mistralai" not in sys.modules
    assert "openai" not in sys.modules


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


def test_factory_resolves_provider_from_env(monkeypatch):
    from core.llm.factory import make_provider

    monkeypatch.setenv("SCOPEGRAPH_LLM_PROVIDER", "mock")
    assert type(make_provider()).__name__ == "MockProvider"
    monkeypatch.setenv("SCOPEGRAPH_LLM_PROVIDER", "none")
    assert make_provider() is None
    monkeypatch.setenv("SCOPEGRAPH_LLM_PROVIDER", "nope")
    with pytest.raises(ValueError, match="nope"):
        make_provider()
