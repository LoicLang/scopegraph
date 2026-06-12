"""Prompt templates live in prompts/*.txt (doctrine: never inline in Python)."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"unknown prompt: {path}")
    return path.read_text(encoding="utf-8")
