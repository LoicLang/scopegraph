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
