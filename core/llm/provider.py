"""LLMProvider Protocol and the scripted MockProvider (hermetic tests, no network)."""

from typing import Protocol


class LLMProvider(Protocol):
    def complete_json(self, system: str, user: str) -> dict: ...


class MockProvider:
    """FIFO queue of scripted dict responses; records every call."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict:
        self.calls.append((system, user))
        return self._responses.pop(0)
