import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_script_generates_standalone_html(tmp_path):
    out = tmp_path / "graph.html"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "graph-viz"), "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    html = out.read_text(encoding="utf-8")
    assert "__GRAPH_DATA__" not in html
    assert '"nodes"' in html
    assert "feat-mobile-ajout-benef" in html
    assert str(out) in result.stdout


def test_script_focus_and_highlight(tmp_path):
    out = tmp_path / "sub.html"
    result = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "graph-viz"),
            "--focus", "feat-mobile-ajout-benef", "--k", "2",
            "--highlight", "con-carence-beneficiaire-48h,obj-beneficiaire",
            "--out", str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    html = out.read_text(encoding="utf-8")
    assert "con-carence-beneficiaire-48h" in html
    assert "sys-core-banking" not in html  # outside the 2-hop subgraph
