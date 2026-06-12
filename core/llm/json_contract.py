"""Content-level JSON contract: one schema-reminder retry, then a clean French error.

Transport retries (429, network) belong to the SDKs; THIS layer only handles a
syntactically valid but schema-miss response (MVP spec §6).
"""

from core.llm.provider import LLMProvider


class JsonContractError(RuntimeError):
    pass


def complete_with_retry(
    provider: LLMProvider, system: str, user: str, *, required_keys: tuple[str, ...]
) -> dict:
    out = provider.complete_json(system, user)
    if all(key in out for key in required_keys):
        return out
    reminder = (
        f"{user}\n\nTa réponse précédente ne respectait pas le schéma attendu. "
        f"Réponds UNIQUEMENT avec un objet JSON contenant les clés : "
        f"{', '.join(required_keys)}."
    )
    out = provider.complete_json(system, reminder)
    if all(key in out for key in required_keys):
        return out
    raise JsonContractError(
        "réponse du modèle invalide après relance — réessayez ou changez de provider"
    )
