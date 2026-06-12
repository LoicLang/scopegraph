"""Mistral provider (official SDK, lazy import — demo default)."""

import json


class MistralProvider:
    def __init__(self, api_key: str, model: str = "mistral-small-latest") -> None:
        self.model = model
        try:
            from mistralai import Mistral
        except ImportError as exc:
            raise RuntimeError(
                "mistralai is not installed — run: pip install -e '.[llm]'"
            ) from exc
        self._client = Mistral(api_key=api_key)

    def complete_json(self, system: str, user: str) -> dict:
        response = self._client.chat.complete(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return json.loads(response.choices[0].message.content)
