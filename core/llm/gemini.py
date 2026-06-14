"""Gemini provider (official Google Gen AI SDK, lazy import)."""

import json


class GeminiProvider:
    def __init__(self, api_key: str, model: str = "gemini-3.5-flash") -> None:
        self.model = model
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "google-genai is not installed — run: pip install -e '.[llm]'"
            ) from exc
        self._client = genai.Client(api_key=api_key)

    def complete_json(self, system: str, user: str) -> dict:
        response = self._client.models.generate_content(
            model=self.model,
            contents=user,
            config={
                "system_instruction": system,
                "temperature": 0,
                "response_mime_type": "application/json",
            },
        )
        return json.loads(response.text)
