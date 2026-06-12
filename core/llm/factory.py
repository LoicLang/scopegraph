"""Provider resolution from env (SCOPEGRAPH_LLM_PROVIDER: mistral|deepseek|mock|none)."""

import os

from core.llm.provider import LLMProvider, MockProvider


def make_provider() -> LLMProvider | None:
    name = os.environ.get("SCOPEGRAPH_LLM_PROVIDER", "none").lower()
    if name == "none":
        return None  # template-only mode: every LLM step falls back deterministically
    if name == "mock":
        return MockProvider([])
    if name == "mistral":
        from core.llm.mistral import MistralProvider

        return MistralProvider(api_key=os.environ["MISTRAL_API_KEY"])
    if name == "deepseek":
        from core.llm.deepseek import DeepSeekProvider

        return DeepSeekProvider(api_key=os.environ["DEEPSEEK_API_KEY"])
    raise ValueError(f"unknown SCOPEGRAPH_LLM_PROVIDER: {name}")
