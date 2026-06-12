from core.benchdata.scenarios import SCENARIOS


def test_scenarios_shape():
    assert len(SCENARIOS) == 11
    names = [s[0] for s in SCENARIOS]
    assert len(set(names)) == 11
    assert all(s[2] for s in SCENARIOS)
