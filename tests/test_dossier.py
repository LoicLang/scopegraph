"""EDB template v1: sections, owners, entry sources, statuses, completeness."""

import pytest

from core.dossier.template import (
    CLAIM_SECTIONS,
    EDB_TEMPLATE_V1,
    EdbEntry,
    EdbState,
)


def test_template_has_the_12_frozen_sections_in_order():
    ids = [section.id for section in EDB_TEMPLATE_V1]
    assert ids == [
        "contexte", "besoin", "utilisateurs", "objectifs", "perimetre", "exigences",
        "dependances", "contraintes", "risques", "jalons", "challenge", "carte",
    ]
    assert all(section.title_fr and section.prompt_hint_fr for section in EDB_TEMPLATE_V1[:10])


def test_claim_sections_enum():
    assert CLAIM_SECTIONS == ("dependances", "contraintes", "risques", "perimetre", "jalons")


def test_state_starts_empty_and_fills():
    state = EdbState.new()
    assert state.status("besoin") == "empty"
    state.add_entry("besoin", EdbEntry(source="user", text="Un programme de cash-back."))
    assert state.status("besoin") == "filled"
    assert state.sections["besoin"][0].source == "user"


def test_unknown_section_fails_loud():
    state = EdbState.new()
    with pytest.raises(KeyError):
        state.add_entry("budget", EdbEntry(source="user", text="x"))


def test_completeness_lists_missing_user_facing_sections():
    state = EdbState.new()
    state.add_entry("besoin", EdbEntry(source="user", text="t"))
    missing = state.missing_sections()
    assert "besoin" not in missing
    assert "objectifs" in missing
    assert "carte" not in missing  # runtime-owned, never asked
    assert "challenge" not in missing  # llm-owned, never asked


def test_state_round_trips_through_dict():
    state = EdbState.new()
    state.add_entry("risques", EdbEntry(source="claim:c1", text="r", node_refs=["risk-x"]))
    clone = EdbState.from_dict(state.to_dict())
    assert clone.sections["risques"][0].node_refs == ["risk-x"]
    assert clone.status("risques") == "filled"


def test_every_askable_section_has_a_sufficiency_criterion():
    from core.dossier.template import ASKABLE_SECTIONS, section_spec
    for sid in ASKABLE_SECTIONS:
        assert section_spec(sid).sufficiency_fr.strip()


def test_incomplete_sections_includes_empty_and_judged_insufficient():
    state = EdbState.new()
    state.add_entry("besoin", EdbEntry(source="user", text="un cash-back"))
    # besoin filled but judged insufficient → still incomplete; objectifs empty → incomplete
    incomplete = state.incomplete_sections(insufficient={"besoin"})
    assert "besoin" in incomplete
    assert "objectifs" in incomplete
    # filled AND judged sufficient → not incomplete
    assert "besoin" not in state.incomplete_sections(insufficient=set())


def test_incomplete_sections_no_arg_equals_missing_sections():
    state = EdbState.new()
    state.add_entry("besoin", EdbEntry(source="user", text="t"))
    assert state.incomplete_sections() == state.missing_sections()
