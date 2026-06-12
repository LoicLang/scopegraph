"""Hermeticity guard: the suite must never see the developer's LLM env/.env.

A real provider in a test is a bug (hard rule 4) — force template mode unless a
test explicitly monkeypatches SCOPEGRAPH_LLM_PROVIDER.
"""

import pytest


@pytest.fixture(autouse=True)
def _force_template_mode(monkeypatch):
    monkeypatch.setenv("SCOPEGRAPH_LLM_PROVIDER", "none")
