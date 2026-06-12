"""DeepSeek provider via the openai SDK (DeepSeek's documented client) — dev/bench."""

import json

_BASE_URL = "https://api.deepseek.com"


class DeepSeekProvider:
    def __init__(self, api_key: str, model: str = "deepseek-chat") -> None:
        self.model = model
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai is not installed — run: pip install -e '.[llm]'"
            ) from exc
        self._client = OpenAI(api_key=api_key, base_url=_BASE_URL)

    def complete_json(self, system: str, user: str) -> dict:
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return json.loads(response.choices[0].message.content)
