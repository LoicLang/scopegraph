"""Provider resolution from env (SCOPEGRAPH_LLM_PROVIDER: mistral|deepseek|mock|none).

API keys may live in a project-root .env (gitignored) — loaded lazily, never
overriding the real environment. No python-dotenv dependency: KEY=VALUE lines,
optional quotes and `export` prefix, # comments.
"""

import os
from pathlib import Path

from core.llm.provider import LLMProvider, MockProvider

_DOTENV = Path(__file__).resolve().parent.parent.parent / ".env"


def load_dotenv(path: Path = _DOTENV) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip("'\"")


def make_provider() -> LLMProvider | None:
    load_dotenv()
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
