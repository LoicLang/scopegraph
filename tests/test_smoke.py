"""Smoke test: the package imports and the test runner works."""

import core


def test_smoke() -> None:
    assert core is not None
    assert True
