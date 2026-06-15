"""Tiny CLI to converse with a running scopegraph session over HTTP.

Usage:
  python say.py <host:port> new                 -> prints: SESSION <id>
  python say.py <host:port> <session_id> <text> -> sends <text>, prints the reply
"""
import json
import sys
import urllib.request


def _post(url: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode("utf-8") if data is not None else b""
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.load(resp)


host, sid = sys.argv[1], sys.argv[2]
if sid == "new":
    print("SESSION", _post(f"http://{host}/api/session")["session_id"])
    sys.exit(0)
r = _post(f"http://{host}/api/session/{sid}/message", {"text": sys.argv[3]})
print("STATE:", r.get("state"), "| CLOSE_REASON:", r.get("close_reason"))
print("ASSISTANT:", (r.get("message") or "").strip())
print("QUESTION:", (r.get("question") or "").strip())
cards = [(c.get("kind"), (c.get("text") or "")[:90]) for c in r.get("cards", [])]
if cards:
    print("CARDS:", cards)
print("STATEMENT_ISSUES:", r.get("statement_issues") or [])
